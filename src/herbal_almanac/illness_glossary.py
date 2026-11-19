"""Herbal Almanac — Machine-Generated Multilingual Illness Glossary Loader and Resolver.

Loads machine-generated multilingual translations from illness_glossary.csv,
resolves CCRAS transliterated illness names with fault tolerance, applies
curated Stage C concept catalog precedence, and provides multilingual search.
"""

from __future__ import annotations

import csv
import importlib.resources as pkg_resources
import re
import unicodedata
from functools import lru_cache
from typing import Any

from .concept_catalog import CANONICAL_CONCEPTS
from .database_operator import canonical_illness_key


# ============================================================================
# 1. Supported Languages and Metadata
# ============================================================================

SUPPORTED_LANGUAGES: dict[str, dict[str, str]] = {
    "en": {"code": "en", "name": "English", "native_name": "English", "column": "English"},
    "hi": {"code": "hi", "name": "Hindi", "native_name": "हिन्दी", "column": "Hindi"},
    "sa": {"code": "sa", "name": "Sanskrit", "native_name": "संस्कृतम्", "column": "Sanskrit"},
    "bn": {"code": "bn", "name": "Bengali", "native_name": "বাংলা", "column": "Bengali"},
    "gu": {"code": "gu", "name": "Gujarati", "native_name": "ગુજરાતી", "column": "Gujarati"},
    "kn": {"code": "kn", "name": "Kannada", "native_name": "ಕನ್ನಡ", "column": "Kannada"},
    "ml": {"code": "ml", "name": "Malayalam", "native_name": "മലയാളം", "column": "Malayalam"},
    "mr": {"code": "mr", "name": "Marathi", "native_name": "मराठी", "column": "Marathi"},
    "ne": {"code": "ne", "name": "Nepali", "native_name": "नेपाली", "column": "Nepali"},
    "or": {"code": "or", "name": "Odia", "native_name": "ଓଡ଼ିଆ", "column": "Odia"},
    "pa": {"code": "pa", "name": "Punjabi", "native_name": "ਪੰਜਾਬੀ", "column": "Punjabi"},
    "ta": {"code": "ta", "name": "Tamil", "native_name": "தமிழ்", "column": "Tamil"},
    "te": {"code": "te", "name": "Telugu", "native_name": "తెలుగు", "column": "Telugu"},
    "ur": {"code": "ur", "name": "Urdu", "native_name": "اردو", "column": "Urdu"},
    "as": {"code": "as", "name": "Assamese", "native_name": "অসমীয়া", "column": "Assamese"},
}

ORDERED_LANGUAGE_CODES: list[str] = [
    "en", "hi", "sa", "bn", "gu", "kn", "ml", "mr", "ne", "or", "pa", "ta", "te", "ur", "as"
]

NON_DISEASE_OR_PROCEDURE_TERMS: dict[str, str] = {
    "yonipuran": "procedure",
    "garbhanirodha": "non-disease concept",
    "medhya": "non-disease concept",
    "rasayana": "non-disease concept",
}

# Mapping of Stage C 24 IND_* concepts to canonical match keys
CATALOG_INDICATION_KEYS: dict[str, list[str]] = {
    "IND_JVARA": ["jvara", "jvarah", "jwara"],
    "IND_KASA": ["kasa", "kasah"],
    "IND_SHWASA": ["shwasa", "svasa", "swasa"],
    "IND_PRAMEHA": ["prameha", "pramehah"],
    "IND_ARSHA": ["arsha", "arsas", "arshah", "arza"],
    "IND_ATISARA": ["atisara", "atisarah"],
    "IND_GRAHANI": ["grahani", "grahni"],
    "IND_KAMALA": ["kamala", "kamla"],
    "IND_PANDU": ["pandu", "panduroga", "pandurogah"],
    "IND_KUSHTHA": ["kushtha", "kustha", "kustham", "kusthah"],
    "IND_SHOTHA": ["shotha", "sotha", "zotha", "shothah"],
    "IND_AMAVATA": ["amavata", "amavatah"],
    "IND_VATARAKTA": ["vatarakta", "vataraktam"],
    "IND_AMLAPITTA": ["amlapitta", "amlapittam"],
    "IND_KRIMI": ["krimi", "krimiroga"],
    "IND_MUTRAKRICCHRA": ["mutrakricchra", "mutrakrichha", "mutrakrcchram"],
    "IND_ASHMARI": ["ashmari", "asmari"],
    "IND_VRANA": ["vrana", "vranah"],
    "IND_DAHA": ["daha", "daham"],
    "IND_CHARDI": ["chardi", "chardih"],
    "IND_TRISHNA": ["trishna", "trsna"],
    "IND_HRIDROGA": ["hridroga", "hridyaroga", "hriddaurblya"],
    "IND_UNMADA": ["unmada", "unmadah"],
    "IND_APASMARA": ["apasmara", "apasmarah"],
}


# ============================================================================
# 2. Tolerant Key Normalization
# ============================================================================

def tolerant_illness_key(term: str) -> str:
    """Normalize illness term with extra tolerance for Sanskrit transliteration variants.

    Tolerances:
    1. Case and Unicode diacritics removal (NFC -> NFKD -> ASCII)
    2. Visarga removal (trailing 'h'/'H')
    3. Sanskrit transliteration: w -> v
    4. Sibilants: z -> s, sh -> s
    5. Affricates: cch -> c, chh -> c, ch -> c
    6. Doubled consonants collapsed (e.g. tt -> t, dd -> d, kk -> k)
    7. Non-alphanumeric characters stripped
    """
    if not term:
        return ""
    text = unicodedata.normalize("NFKD", term.strip())
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace("w", "v")
    text = text.replace("sh", "s").replace("z", "s")
    text = text.replace("cch", "c").replace("chh", "c").replace("ch", "c")
    text = re.sub(r"([b-df-hj-np-tv-z])\1+", r"\1", text)
    text = re.sub(r"h+$", "", text)
    text = re.sub(r"[^a-z0-9]", "", text)
    return text


def _split_slashed_cell(value: str) -> tuple[str, list[str]]:
    """Split a cell like 'Primary / Synonym 1 / Synonym 2' into (primary, synonyms)."""
    if not value or not value.strip():
        return "", []
    parts = [p.strip() for p in value.split("/") if p.strip()]
    if not parts:
        return "", []
    return parts[0], parts[1:]


# ============================================================================
# 3. Label & Resolved Illness Models
# ============================================================================

class LanguageLabel(dict):
    """Holds label text and language metadata, behaving as both a dict and object."""

    def __init__(
        self,
        label: str,
        language_name: str,
        native_name: str,
        language_code: str,
        synonyms: list[str] | None = None,
        raw_text: str | None = None,
    ) -> None:
        synonyms = synonyms or []
        raw_text = raw_text if raw_text is not None else label
        super().__init__(
            label=label,
            language_name=language_name,
            native_name=native_name,
            language_code=language_code,
            synonyms=synonyms,
            raw_text=raw_text,
        )
        self.label = label
        self.language_name = language_name
        self.native_name = native_name
        self.language_code = language_code
        self.synonyms = synonyms
        self.raw_text = raw_text

    def __str__(self) -> str:
        return self.label


class ResolvedIllness(dict):
    """Represents a resolved illness concept with translations and provenance metadata."""

    def __init__(
        self,
        matched: bool,
        key: str,
        english: str,
        english_synonyms: list[str],
        labels: dict[str, LanguageLabel],
        origin: str = "machine_generated",
        verification: str = "unverified",
        original_term: str = "",
        kind: str | None = None,
        catalog_code: str | None = None,
        note: str | None = None,
    ) -> None:
        super().__init__(
            matched=matched,
            key=key,
            english=english,
            english_synonyms=english_synonyms,
            labels=labels,
            origin=origin,
            verification=verification,
            original_term=original_term,
            kind=kind,
            catalog_code=catalog_code,
            note=note,
        )
        self.matched = matched
        self.key = key
        self.english = english
        self.english_synonyms = english_synonyms
        self.labels = labels
        self.origin = origin
        self.verification = verification
        self.original_term = original_term
        self.kind = kind
        self.catalog_code = catalog_code
        self.note = note

    def get_label(self, lang_code: str = "en") -> str:
        """Returns the primary label for the specified language, falling back to English."""
        if lang_code == "en" or not lang_code:
            return self.english
        label_obj = self.labels.get(lang_code)
        if label_obj and label_obj.label:
            return label_obj.label
        return self.english

    def get_label_object(self, lang_code: str = "en") -> LanguageLabel | None:
        """Returns the LanguageLabel object for the specified language."""
        return self.labels.get(lang_code)


# ============================================================================
# 4. Glossary Cache and Loader
# ============================================================================

class GlossaryStore:
    """In-memory index of parsed illness glossary records and catalog overrides."""

    def __init__(self) -> None:
        self.records: list[ResolvedIllness] = []
        self.by_canonical_key: dict[str, ResolvedIllness] = {}
        self.by_tolerant_key: dict[str, ResolvedIllness] = {}
        self.by_original_term: dict[str, ResolvedIllness] = {}
        self.by_english_term: dict[str, ResolvedIllness] = {}
        self.conflicts: list[dict[str, Any]] = []
        self._load()

    def _load_catalog_indications(self) -> dict[str, dict[str, Any]]:
        """Extracts the 24 IND_* concepts from Stage C canonical concepts."""
        catalog_map: dict[str, dict[str, Any]] = {}
        for c in CANONICAL_CONCEPTS:
            if not c.concept_code.startswith("IND_"):
                continue
            labels_by_lang: dict[str, str] = {}
            for l in c.labels:
                if l.is_preferred:
                    if l.language_code == "sa":
                        if l.script_code == "Deva":
                            labels_by_lang["sa_deva"] = l.label_text
                        elif l.script_code == "Latn":
                            labels_by_lang["sa_latn"] = l.label_text
                    else:
                        labels_by_lang[l.language_code] = l.label_text
            catalog_map[c.concept_code] = {
                "concept_code": c.concept_code,
                "en": labels_by_lang.get("en", ""),
                "hi": labels_by_lang.get("hi", ""),
                "sa": labels_by_lang.get("sa_deva") or labels_by_lang.get("sa_latn", ""),
                "sa_latn": labels_by_lang.get("sa_latn", ""),
            }
        return catalog_map

    def _load(self) -> None:
        """Load CSV data via importlib.resources and build multi-index."""
        data_res = pkg_resources.files("herbal_almanac").joinpath("data", "illness_glossary.csv")
        with data_res.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            raw_rows = list(reader)

        catalog_indications = self._load_catalog_indications()

        # Build reverse lookup from key to catalog indication
        key_to_catalog: dict[str, dict[str, Any]] = {}
        for ind_code, alias_keys in CATALOG_INDICATION_KEYS.items():
            if ind_code in catalog_indications:
                ind_info = catalog_indications[ind_code]
                for ak in alias_keys:
                    key_to_catalog[canonical_illness_key(ak)] = ind_info
                    key_to_catalog[tolerant_illness_key(ak)] = ind_info

        for row in raw_rows:
            orig_term = row["Original_Term"].strip()
            english_val = row["English"].strip()
            primary_en, en_synonyms = _split_slashed_cell(english_val)

            # Check for kind (P1-2: procedure, non-disease concept)
            kind = None
            for sensitive_term, sensitive_kind in NON_DISEASE_OR_PROCEDURE_TERMS.items():
                if sensitive_term.lower() in orig_term.lower() or tolerant_illness_key(sensitive_term) == tolerant_illness_key(orig_term):
                    kind = sensitive_kind
                    break

            # Parse language labels
            labels_dict: dict[str, LanguageLabel] = {}
            for lang_code, lang_meta in SUPPORTED_LANGUAGES.items():
                if lang_code == "en":
                    continue
                col_name = lang_meta["column"]
                col_val = row.get(col_name, "").strip()
                primary_label, label_synonyms = _split_slashed_cell(col_val)
                labels_dict[lang_code] = LanguageLabel(
                    label=primary_label,
                    language_name=lang_meta["name"],
                    native_name=lang_meta["native_name"],
                    language_code=lang_code,
                    synonyms=label_synonyms,
                    raw_text=col_val,
                )

            # Check if this term matches one of the 24 Stage C IND_* catalog concepts
            # (catalog curated labels win on conflict)
            catalog_match = None
            term_parts = [p.strip() for p in orig_term.split("/") if p.strip()]
            for p in term_parts:
                p_canon = canonical_illness_key(p)
                p_tol = tolerant_illness_key(p)
                if p_canon in key_to_catalog:
                    catalog_match = key_to_catalog[p_canon]
                    break
                if p_tol in key_to_catalog:
                    catalog_match = key_to_catalog[p_tol]
                    break

            catalog_code = None
            if catalog_match:
                catalog_code = catalog_match["concept_code"]
                cat_en = catalog_match.get("en")
                cat_hi = catalog_match.get("hi")
                cat_sa = catalog_match.get("sa")

                # Detect disagreements for --conflicts report
                disagreements = {}
                if cat_en and cat_en != english_val:
                    disagreements["en"] = {"catalog": cat_en, "csv": english_val}
                csv_hi = row.get("Hindi", "").strip()
                if cat_hi and cat_hi != csv_hi:
                    disagreements["hi"] = {"catalog": cat_hi, "csv": csv_hi}
                csv_sa = row.get("Sanskrit", "").strip()
                if cat_sa and cat_sa != csv_sa:
                    disagreements["sa"] = {"catalog": cat_sa, "csv": csv_sa}

                if disagreements:
                    self.conflicts.append({
                        "catalog_code": catalog_code,
                        "original_term": orig_term,
                        "disagreements": disagreements,
                    })

                # Curated catalog labels WIN on conflict
                if cat_en:
                    cat_primary_en, cat_en_synonyms = _split_slashed_cell(cat_en)
                    primary_en = cat_primary_en
                    # Append CSV English as synonym if not already present
                    for s in cat_en_synonyms + [primary_en] + en_synonyms:
                        if s and s != primary_en and s not in en_synonyms:
                            en_synonyms.append(s)

                if cat_hi and "hi" in labels_dict:
                    labels_dict["hi"] = LanguageLabel(
                        label=cat_hi,
                        language_name="Hindi",
                        native_name="हिन्दी",
                        language_code="hi",
                        synonyms=[row.get("Hindi", "").strip()],
                        raw_text=cat_hi,
                    )

                if cat_sa and "sa" in labels_dict:
                    labels_dict["sa"] = LanguageLabel(
                        label=cat_sa,
                        language_name="Sanskrit",
                        native_name="संस्कृतम्",
                        language_code="sa",
                        synonyms=[row.get("Sanskrit", "").strip()],
                        raw_text=cat_sa,
                    )

            resolved = ResolvedIllness(
                matched=True,
                key=canonical_illness_key(orig_term),
                english=primary_en,
                english_synonyms=en_synonyms,
                labels=labels_dict,
                origin="machine_generated",
                verification="unverified",
                original_term=orig_term,
                kind=kind,
                catalog_code=catalog_code,
            )

            self.records.append(resolved)

            # Index by exact original term
            self.by_original_term[orig_term] = resolved
            self.by_canonical_key[canonical_illness_key(orig_term)] = resolved
            self.by_tolerant_key[tolerant_illness_key(orig_term)] = resolved

            # Index by English terms
            self.by_english_term[primary_en.lower()] = resolved
            for syn in en_synonyms:
                self.by_english_term[syn.lower()] = resolved

            # Index slash-compounds by each part
            for part in term_parts:
                self.by_original_term[part] = resolved
                self.by_canonical_key[canonical_illness_key(part)] = resolved
                self.by_tolerant_key[tolerant_illness_key(part)] = resolved


@lru_cache(maxsize=1)
def get_glossary_store() -> GlossaryStore:
    """Returns the singleton cached GlossaryStore."""
    return GlossaryStore()


# ============================================================================
# 5. Public Resolution API
# ============================================================================

def resolve_illness(name: str | None) -> ResolvedIllness:
    """Resolves an illness name into a ResolvedIllness object with translations.

    If name matches a glossary record (exact, canonical, or tolerant), returns
    the matched record with translations across all 15 supported languages.
    If unmatched, falls back to formatted readable transliteration with
    matched=False and a subtle 'translation not available' note.
    """
    if not name or not name.strip():
        return ResolvedIllness(
            matched=False,
            key="",
            english="",
            english_synonyms=[],
            labels={},
            origin="machine_generated",
            verification="unverified",
            original_term="",
            note="translation not available",
        )

    clean_name = name.strip()
    store = get_glossary_store()

    # 1. Exact original term lookup
    if clean_name in store.by_original_term:
        return store.by_original_term[clean_name]

    # 2. Canonical illness key lookup
    canon_key = canonical_illness_key(clean_name)
    if canon_key in store.by_canonical_key:
        return store.by_canonical_key[canon_key]

    # 3. Tolerant transliteration key lookup
    tol_key = tolerant_illness_key(clean_name)
    if tol_key in store.by_tolerant_key:
        return store.by_tolerant_key[tol_key]

    # 4. English term lookup
    en_key = clean_name.lower()
    if en_key in store.by_english_term:
        return store.by_english_term[en_key]

    # 5. Split compound parts lookup
    if "/" in clean_name:
        for part in clean_name.split("/"):
            part_clean = part.strip()
            if not part_clean:
                continue
            if part_clean in store.by_original_term:
                return store.by_original_term[part_clean]
            p_canon = canonical_illness_key(part_clean)
            if p_canon in store.by_canonical_key:
                return store.by_canonical_key[p_canon]
            p_tol = tolerant_illness_key(part_clean)
            if p_tol in store.by_tolerant_key:
                return store.by_tolerant_key[p_tol]

    # Fallback for unmatched illnesses: format readable text without altering data
    from .web_app import format_readable_illness

    readable = format_readable_illness(clean_name)
    return ResolvedIllness(
        matched=False,
        key=canon_key,
        english=readable,
        english_synonyms=[],
        labels={},
        origin="machine_generated",
        verification="unverified",
        original_term=clean_name,
        note="translation not available",
    )


def search_glossary(query: str) -> list[ResolvedIllness]:
    """Search glossary across English, Original_Term, synonyms, and all language columns.

    Matches query with Unicode NFC normalization and case-insensitivity.
    """
    if not query or not query.strip():
        return []

    q_norm = unicodedata.normalize("NFC", query.strip().lower())
    q_canon = canonical_illness_key(query)
    q_tol = tolerant_illness_key(query)

    store = get_glossary_store()
    matched: list[ResolvedIllness] = []
    seen_keys: set[str] = set()

    for record in store.records:
        if record.key in seen_keys:
            continue

        match_found = False

        # Match English primary & synonyms
        if q_norm in unicodedata.normalize("NFC", record.english.lower()):
            match_found = True
        elif any(q_norm in unicodedata.normalize("NFC", syn.lower()) for syn in record.english_synonyms):
            match_found = True
        # Match original term or normalized key
        elif q_norm in unicodedata.normalize("NFC", record.original_term.lower()):
            match_found = True
        elif q_canon and (q_canon == record.key or q_canon in record.key):
            match_found = True
        elif q_tol and (q_tol in tolerant_illness_key(record.original_term)):
            match_found = True
        else:
            # Match in any language column
            for label_obj in record.labels.values():
                raw = label_obj.raw_text or label_obj.label
                if raw and q_norm in unicodedata.normalize("NFC", raw.lower()):
                    match_found = True
                    break

        if match_found:
            matched.append(record)
            seen_keys.add(record.key)

    return matched


def get_catalog_csv_conflicts() -> list[dict[str, Any]]:
    """Returns detected disagreements between curated Stage C catalog labels and CSV translations."""
    store = get_glossary_store()
    return store.conflicts
