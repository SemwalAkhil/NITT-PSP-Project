from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata
from typing import Iterable, Literal
from urllib.parse import urlsplit


AttributeKind = Literal["disease", "ambiguous"]
DoshaEffect = Literal["decrease", "increase", "unspecified"]
DOSHAS = ("Vata", "Pitta", "Kapha")
DOSHA_ALIASES = {
    "vata": "Vata",
    "pitta": "Pitta",
    "kapha": "Kapha",
}


@dataclass(frozen=True, slots=True)
class TypedAttribute:
    field: str
    value: str
    kind: AttributeKind


# The source's therapeutic name column is a condition/indication feed. Its
# values remain unverified until they are mapped to a controlled vocabulary.
CONDITION_FIELDS = frozenset({"Therapeutic Usage.Name"})
PRESERVED_FORMAT_CHARACTERS = frozenset({"\u200c", "\u200d"})
ROMANIZATION = str.maketrans({
    "ā": "A", "ī": "I", "ū": "U", "ṛ": "R", "ṝ": "RR", "ḷ": "L",
    "ḹ": "LL", "ṅ": "G", "ñ": "J", "ṭ": "T", "ḍ": "D", "ṇ": "N",
    "ś": "z", "ṣ": "S", "ḥ": "H", "ṃ": "M",
    "Ā": "A", "Ī": "I", "Ū": "U", "Ṛ": "R", "Ṝ": "RR", "Ḷ": "L",
    "Ḹ": "LL", "Ṅ": "G", "Ñ": "J", "Ṭ": "T", "Ḍ": "D", "Ṇ": "N",
    "Ś": "Z", "Ṣ": "S", "Ḥ": "H", "Ṃ": "M",
})
SPLIT_PATTERN = re.compile(r"\s*(?:\n|;|\|)\s*")
DOSHA_DECREASE_TERMS = ("shamana", "zamana", "ghna", "hara")
DOSHA_INCREASE_TERMS = ("vardhaka", "vrddhi")


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    value = "".join(
        character
        for character in value
        if (
            unicodedata.category(character) != "Cf"
            or character in PRESERVED_FORMAT_CHARACTERS
        ) and unicodedata.category(character) not in {"So", "Sk"}
        and not 0xFE00 <= ord(character) <= 0xFE0F
    )
    return " ".join(value.split())


def clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = clean_text(value)
    return cleaned or None


def ascii_text(value: str) -> str:
    """Return Harvard-Kyoto-style ASCII transliteration for search/display."""
    value = unicodedata.normalize("NFC", value)
    value = value.translate(ROMANIZATION)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    return clean_text(value.encode("ascii", "ignore").decode("ascii"))


def clean_values(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = clean_text(value)
        if cleaned and cleaned not in seen:
            result.append(cleaned)
            seen.add(cleaned)
    return result


def attribute_kind(field: str, value: str) -> AttributeKind:
    """Classify every value from the known source condition field."""
    del value
    return "disease" if clean_text(field) in CONDITION_FIELDS else "ambiguous"


@dataclass(slots=True)
class PlantRecord:
    source: str
    source_record_id: int
    source_url: str
    retrieved_at: str
    ayurvedic_name: str
    botanical_name: str | None = None
    family: str | None = None
    attributes: dict[str, list[str]] = field(default_factory=dict)
    source_values: dict[str, str] = field(default_factory=dict)
    attribute_metadata: dict[str, dict[str, str | bool]] = field(default_factory=dict)
    dosha_expressions: list[str] = field(default_factory=list)
    translation_failures: list[str] = field(default_factory=list)
    transliterated_name: str = ""
    transliterated_botanical_name: str | None = None
    transliterated_family: str | None = None

    def clean(self) -> PlantRecord:
        self.source = clean_text(self.source)
        self.retrieved_at = clean_text(self.retrieved_at)
        self.ayurvedic_name = clean_text(self.ayurvedic_name)
        self.botanical_name = clean_optional_text(self.botanical_name)
        self.family = clean_optional_text(self.family)
        self.transliterated_name = ascii_text(self.ayurvedic_name)
        self.transliterated_botanical_name = (
            ascii_text(self.botanical_name) if self.botanical_name else None
        )
        self.transliterated_family = ascii_text(self.family) if self.family else None
        cleaned_attributes: dict[str, list[str]] = {}
        for field, values in self.attributes.items():
            cleaned_field = clean_text(field)
            if not cleaned_field:
                continue
            cleaned_values = clean_values(values)
            if cleaned_values:
                merged_values = cleaned_attributes.setdefault(cleaned_field, [])
                for value in cleaned_values:
                    if value not in merged_values:
                        merged_values.append(value)
        self.attributes = cleaned_attributes
        self.source_values = {
            clean_text(field): clean_text(value)
            for field, value in self.source_values.items()
            if clean_text(field) and clean_text(value)
        }
        self.dosha_expressions = clean_values(self.dosha_expressions)
        self.attribute_metadata = {
            clean_text(field): metadata
            for field, metadata in self.attribute_metadata.items()
            if clean_text(field)
        }
        return self

    def typed_attributes(self) -> Iterable[TypedAttribute]:
        for field, values in self.attributes.items():
            for value in values:
                yield TypedAttribute(field, value, attribute_kind(field, value))

    def validate(self) -> None:
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source cannot be empty")
        if not isinstance(self.retrieved_at, str) or not self.retrieved_at.strip():
            raise ValueError("retrieved_at cannot be empty")
        if isinstance(self.source_record_id, bool) or self.source_record_id <= 0:
            raise ValueError("source_record_id must be a positive integer")
        parsed_url = urlsplit(self.source_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise ValueError("source_url must be an HTTP(S) URL")
        if not self.ayurvedic_name:
            raise ValueError("ayurvedic_name cannot be empty")


def split_values(value: str) -> list[str]:
    return clean_values(SPLIT_PATTERN.split(value))


@dataclass(frozen=True, slots=True)
class DoshaNormalization:
    source_expression: str
    effects: dict[str, DoshaEffect]


def normalize_dosha_expression(expression: str) -> DoshaNormalization:
    """Normalize documented Dosha effects without inferring missing Doshas."""
    normalized = re.sub(r"[^a-z]", "", ascii_text(clean_text(expression)).casefold())
    effects_by_dosha: dict[str, set[DoshaEffect]] = {dosha: set() for dosha in DOSHAS}
    cursor = 0
    while cursor < len(normalized):
        if normalized.startswith("tridosa", cursor):
            cursor += len("tridosa")
            present_doshas = DOSHAS
        elif normalized.startswith("tridosha", cursor):
            cursor += len("tridosha")
            present_doshas = DOSHAS
        else:
            dosha = next(
                (
                    canonical
                    for alias, canonical in DOSHA_ALIASES.items()
                    if normalized.startswith(alias, cursor)
                ),
                None,
            )
            if dosha is None:
                break
            cursor += len(dosha.casefold())
            present_doshas = (dosha,)
            while cursor < len(normalized):
                next_dosha = next(
                    (
                        canonical
                        for alias, canonical in DOSHA_ALIASES.items()
                        if normalized.startswith(alias, cursor)
                    ),
                    None,
                )
                if next_dosha is None:
                    break
                cursor += len(next_dosha.casefold())
                present_doshas += (next_dosha,)

        effect: DoshaEffect | None = None
        for term in DOSHA_DECREASE_TERMS:
            if normalized.startswith(term, cursor):
                effect = "decrease"
                cursor += len(term)
                break
        if effect is None:
            for term in DOSHA_INCREASE_TERMS:
                if normalized.startswith(term, cursor):
                    effect = "increase"
                    cursor += len(term)
                    break
        if effect is None:
            break
        for dosha in present_doshas:
            effects_by_dosha[dosha].add(effect)

    if cursor != len(normalized) or not any(effects_by_dosha.values()):
        effects_by_dosha = {dosha: set() for dosha in DOSHAS}

    return DoshaNormalization(
        source_expression=expression,
        effects={
            dosha: next(iter(effects)) if len(effects) == 1 else "unspecified"
            for dosha, effects in effects_by_dosha.items()
        },
    )
