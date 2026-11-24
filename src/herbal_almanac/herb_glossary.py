"""Herbal Almanac — Multilingual Herb Glossary Loader and Resolver.

Loads multilingual herb names from herb_names.csv (English + 14 Indian languages),
provides tolerant transliteration matching, resolves CCRAS plant IDs, and
enables multilingual search across Indic languages.
"""

from __future__ import annotations

import csv
import importlib.resources as pkg_resources
import re
import unicodedata
from functools import lru_cache
from typing import Any


# ISO 639-1 / standard language codes and column headers
HERB_LANGUAGE_COLUMNS: dict[str, str] = {
    "en": "English",
    "as": "Assamese",
    "bn": "Bengali",
    "gu": "Gujarati",
    "hi": "Hindi",
    "kn": "Kannada",
    "ml": "Malayalam",
    "mr": "Marathi",
    "ne": "Nepali",
    "or": "Odia",
    "pa": "Punjabi",
    "sa": "Sanskrit",
    "ta": "Tamil",
    "te": "Telugu",
    "ur": "Urdu",
}

# Reverse lookup: Column name (case-insensitive) -> language code
COLUMN_TO_LANG_CODE: dict[str, str] = {
    col.lower(): code for code, col in HERB_LANGUAGE_COLUMNS.items()
}

CCRAS_SOURCE: str = "CCRAS DRAVYA"


def is_ccras_source(source: str | None) -> bool:
    """Return True if source matches CCRAS DRAVYA (case-insensitive, tolerating variants)."""
    if not source:
        return False
    s = str(source).strip().lower()
    return s in {"ccras dravya", "ccras", "dravya", "ccras_dravya", "ccras-dravya"}



def tolerant_herb_key(term: str | None) -> str:
    """Normalize a herb name for fault-tolerant matching.

    Performs:
    1. Unicode decomposition (NFKD) and diacritic removal.
    2. Lowercasing and strip whitespace.
    3. Replacement of common phonetic variants:
       - 'w' -> 'v'
       - 'sh' -> 's', 'z' -> 's'
       - 'cch' -> 'c', 'chh' -> 'c', 'ch' -> 'c'
    4. Collapse doubled consonants.
    5. Stripping of non-alphanumeric characters (keeping Devanagari & Indic chars intact).
    """
    if not term:
        return ""
    stripped = str(term).strip()
    if not stripped:
        return ""

    # Decompose and remove combining marks
    text = unicodedata.normalize("NFKD", stripped)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()

    # Transliteration tolerances
    text = text.replace("w", "v")
    text = text.replace("sh", "s").replace("z", "s")
    text = text.replace("cch", "c").replace("chh", "c").replace("ch", "c")
    text = re.sub(r"([b-df-hj-np-tv-z])\1+", r"\1", text)
    # Remove punctuation and non-alphanumeric except word characters and Indic Unicode ranges
    text = re.sub(r"[^\w\s]", "", text)
    return " ".join(text.split())


def normalize_binomial(botanical_name: str | None) -> str:
    """Normalize a botanical name to its lowercase 'genus species' binomial.

    Strips diacritics, parenthetical authority citations (e.g. '(Schum.)'),
    punctuation, and trailing authority/variety suffixes (e.g. 'Muell', 'Buch',
    'Linn.', 'var. ...', 'Stapf', 'Wall').
    """
    if not botanical_name:
        return ""
    text = unicodedata.normalize("NFKD", str(botanical_name))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = text.split()
    if len(tokens) >= 2:
        return f"{tokens[0]} {tokens[1]}"
    return " ".join(tokens)


class ResolvedHerb(dict):
    """Holds a resolved herb entry with multilingual names and metadata.

    Note:
        ``id`` is the internal glossary row number (1..347) and is NOT stable
        across scrapes — never compare it with ``source_record_id`` or ``herbs.id``.
        Use ``ccras_id`` to match CCRAS DRAVYA ``source_record_id``.
    """

    def __init__(
        self,
        herb_id: int,
        original_name: str,
        botanical_name: str,
        english_name: str,
        vernacular_names: dict[str, str],
        ccras_id: int | None = None,
    ) -> None:
        super().__init__(
            id=herb_id,
            ccras_id=ccras_id,
            original_name=original_name,
            botanical_name=botanical_name,
            english_name=english_name,
            vernacular_names=vernacular_names,
        )
        self.id = herb_id
        self.ccras_id = ccras_id
        self.original_name = original_name
        self.botanical_name = botanical_name
        self.english_name = english_name
        self.vernacular_names = vernacular_names

    def get_name(self, lang: str) -> str | None:
        """Get the name in a specific language code ('hi', 'ta', 'en', etc.)."""
        col = HERB_LANGUAGE_COLUMNS.get(lang.lower())
        if col and col in self.vernacular_names:
            val = self.vernacular_names[col]
            return val if val != "N/A" else None
        # Check by code directly or case-insensitive match
        for k, v in self.vernacular_names.items():
            if k.lower() == lang.lower() or COLUMN_TO_LANG_CODE.get(k.lower()) == lang.lower():
                return v if v != "N/A" else None
        return None

    def all_names(self) -> list[str]:
        """Return all distinct non-empty names across all languages."""
        names = [self.original_name, self.botanical_name, self.english_name]
        for v in self.vernacular_names.values():
            if v and v != "N/A" and v not in names:
                names.append(v)
        return [n for n in names if n]


class HerbGlossaryStore:
    """In-memory indexing and resolution engine for herb_names.csv."""

    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.by_id: dict[int, ResolvedHerb] = {}
        self.by_ccras_id: dict[int, ResolvedHerb] = {}
        self.by_binomial: dict[str, list[ResolvedHerb]] = {}
        self.by_botanical: dict[str, ResolvedHerb] = {}
        self.by_original: dict[str, ResolvedHerb] = {}
        self.by_english: dict[str, ResolvedHerb] = {}
        self.by_name_key: dict[str, list[ResolvedHerb]] = {}
        self.all_herbs: list[ResolvedHerb] = []

        for row in rows:
            try:
                h_id = int(row["id"].strip())
            except (ValueError, KeyError):
                continue

            raw_ccras = (row.get("ccras_id") or "").strip()
            ccras_id: int | None = None
            if raw_ccras:
                try:
                    ccras_id = int(raw_ccras)
                except ValueError:
                    ccras_id = None

            orig = row.get("original_name", "").strip()
            bot = row.get("botanical_name", "").strip()
            eng = row.get("English", "").strip()

            # Vernacular mapping: column name -> name
            vernacular: dict[str, str] = {}
            for col, val in row.items():
                if col not in ("id", "ccras_id", "original_name", "botanical_name") and val:
                    vernacular[col] = val.strip()

            resolved = ResolvedHerb(
                herb_id=h_id,
                original_name=orig,
                botanical_name=bot,
                english_name=eng,
                vernacular_names=vernacular,
                ccras_id=ccras_id,
            )

            self.by_id[h_id] = resolved
            if ccras_id is not None:
                self.by_ccras_id[ccras_id] = resolved
            self.all_herbs.append(resolved)

            if bot:
                self.by_botanical[tolerant_herb_key(bot)] = resolved
                norm_bin = normalize_binomial(bot)
                if norm_bin:
                    self.by_binomial.setdefault(norm_bin, []).append(resolved)
            if orig:
                self.by_original[tolerant_herb_key(orig)] = resolved
            if eng:
                self.by_english[tolerant_herb_key(eng)] = resolved

            # Index all available names for general text search
            for name in resolved.all_names():
                key = tolerant_herb_key(name)
                if key:
                    self.by_name_key.setdefault(key, []).append(resolved)

    def resolve_by_id(self, herb_id: int) -> ResolvedHerb | None:
        """Resolve a herb directly by its internal glossary row ID (1..347)."""
        return self.by_id.get(herb_id)

    def resolve_herb(self, query: dict[str, Any] | str | int | None) -> ResolvedHerb | None:
        """Resolve a herb dict or query string/ID to a ResolvedHerb.

        When given a herb dictionary:
        1. If ``is_ccras_source(herb['source'])`` and ``source_record_id`` is an int,
           look up ``by_ccras_id[source_record_id]`` (never use it as glossary row id).
        2. Botanical name: match on normalized binomial (genus + species). If multiple
           glossary rows share the binomial, prefer one whose ``original_name`` matches
           the herb's ``original_name`` or ``english_name``, else the first.
        3. Fallback to ``original_name``, then ``english_name`` via tolerant matching.
        """
        if query is None:
            return None

        if isinstance(query, dict):
            # 1. CCRAS source_record_id -> by_ccras_id (NEVER by_id)
            if is_ccras_source(query.get("source")):
                src_id = query.get("source_record_id")
                if src_id is not None:
                    try:
                        val = int(src_id)
                        if val > 0 and val in self.by_ccras_id:
                            return self.by_ccras_id[val]
                    except (ValueError, TypeError):
                        pass

            # 2. Botanical name -> normalized binomial
            bot = query.get("botanical_name")
            if bot:
                norm_bin = normalize_binomial(bot)
                if norm_bin and norm_bin in self.by_binomial:
                    candidates = self.by_binomial[norm_bin]
                    if len(candidates) == 1:
                        return candidates[0]
                    orig_key = tolerant_herb_key(query.get("original_name"))
                    eng_key = tolerant_herb_key(query.get("english_name"))
                    for cand in candidates:
                        c_orig = tolerant_herb_key(cand.original_name)
                        if c_orig and (c_orig == orig_key or c_orig == eng_key):
                            return cand
                    return candidates[0]
                resolved = self.by_botanical.get(tolerant_herb_key(bot))
                if resolved:
                    return resolved

            # 3. Original name, then English name
            orig = query.get("original_name")
            if orig:
                resolved = self.by_original.get(tolerant_herb_key(orig))
                if resolved:
                    return resolved

            eng = query.get("english_name")
            if eng:
                resolved = self.by_english.get(tolerant_herb_key(eng))
                if resolved:
                    return resolved

            return None

        if isinstance(query, int):
            return self.resolve_by_id(query)

        clean = str(query).strip()
        if not clean:
            return None

        if clean.isdigit():
            found = self.resolve_by_id(int(clean))
            if found:
                return found

        key = tolerant_herb_key(clean)
        if not key:
            return None

        # Check exact key matches in priority order
        if key in self.by_botanical:
            return self.by_botanical[key]
        norm_bin = normalize_binomial(clean)
        if norm_bin and norm_bin in self.by_binomial:
            return self.by_binomial[norm_bin][0]
        if key in self.by_original:
            return self.by_original[key]
        if key in self.by_english:
            return self.by_english[key]
        if key in self.by_name_key and self.by_name_key[key]:
            return self.by_name_key[key][0]

        # Partial / substring match
        for candidate_key, items in self.by_name_key.items():
            if key in candidate_key or candidate_key in key:
                return items[0]

        return None

    def search_herb_glossary(
        self,
        query: str,
        language: str | None = None,
        limit: int = 50,
    ) -> list[ResolvedHerb]:
        """Search for herbs matching query in all or a specific language."""
        clean = query.strip()
        if not clean:
            return self.all_herbs[:limit]

        key = tolerant_herb_key(clean)
        clean_lower = clean.lower()
        matched: list[ResolvedHerb] = []
        seen_ids: set[int] = set()

        def _add(h: ResolvedHerb) -> None:
            if h.id not in seen_ids:
                seen_ids.add(h.id)
                matched.append(h)

        col_filter = HERB_LANGUAGE_COLUMNS.get(language.lower()) if language else None

        for herb in self.all_herbs:
            if len(matched) >= limit:
                break

            if col_filter:
                val = herb.vernacular_names.get(col_filter)
                if val and val != "N/A":
                    val_key = tolerant_herb_key(val)
                    if key and (key in val_key or val_key in key or clean_lower in val.lower()):
                        _add(herb)
            else:
                # Search all names
                for name in herb.all_names():
                    n_key = tolerant_herb_key(name)
                    if key and (key in n_key or n_key in key or clean_lower in name.lower()):
                        _add(herb)
                        break

        return matched

    def get_plant_id(self, herb: dict[str, Any]) -> int | None:
        """Resolve the internal glossary row ID (`ResolvedHerb.id`) for a herb dictionary.

        Note:
            The returned ID is the internal glossary row number (1..347), NEVER
            ``source_record_id`` or ``herbs.id``. Prefer ``resolve_herb(herb)``
            for new code.
        """
        resolved = self.resolve_herb(herb)
        return resolved.id if resolved else None


@lru_cache(maxsize=1)
def get_herb_glossary_store() -> HerbGlossaryStore:
    """Loads and caches the singleton HerbGlossaryStore from packaged CSV."""
    data_pkg = "herbal_almanac.data"
    filename = "herb_names.csv"

    try:
        data_file = pkg_resources.files(data_pkg).joinpath(filename)
        with data_file.open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except Exception:
        # Fallback to local filesystem path
        from pathlib import Path
        local_path = Path(__file__).resolve().parent / "data" / filename
        if local_path.is_file():
            with local_path.open("r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        else:
            rows = []

    return HerbGlossaryStore(rows)


def resolve_herb(query: str | int | None) -> ResolvedHerb | None:
    """Convenience helper to resolve a herb by query."""
    return get_herb_glossary_store().resolve_herb(query)


def search_herb_glossary(
    query: str,
    language: str | None = None,
    limit: int = 50,
) -> list[ResolvedHerb]:
    """Convenience helper to search the herb glossary."""
    return get_herb_glossary_store().search_herb_glossary(query, language=language, limit=limit)
