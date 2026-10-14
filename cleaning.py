from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata
from typing import Iterable, Literal


AttributeKind = Literal["disease", "ambiguous"]


@dataclass(frozen=True, slots=True)
class TypedAttribute:
    field: str
    value: str
    kind: AttributeKind


# The source's therapeutic name column is a condition/indication feed. Its
# values remain unverified until they are mapped to a controlled vocabulary.
CONDITION_FIELDS = frozenset({"Therapeutic Usage.Name"})


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    value = "".join(
        character
        for character in value
        if unicodedata.category(character) not in {"Cf", "So", "Sk"}
        and not 0xFE00 <= ord(character) <= 0xFE0F
    )
    return " ".join(value.split())


def ascii_text(value: str) -> str:
    """Return Harvard-Kyoto-style ASCII transliteration for search/display."""
    romanization = str.maketrans({
        "ā": "A", "ī": "I", "ū": "U", "ṛ": "R", "ṝ": "RR", "ḷ": "L",
        "ḹ": "LL", "ṅ": "N", "ñ": "~n", "ṭ": "T", "ḍ": "D", "ṇ": "N",
        "ś": "z", "ṣ": "S", "ḥ": "H", "ṃ": "M",
        "Ā": "A", "Ī": "I", "Ū": "U", "Ṛ": "R", "Ṝ": "RR", "Ḷ": "L",
        "Ḹ": "LL", "Ṅ": "N", "Ñ": "~N", "Ṭ": "T", "Ḍ": "D", "Ṇ": "N",
        "Ś": "Z", "Ṣ": "S", "Ḥ": "H", "Ṃ": "M",
    })
    value = value.translate(romanization)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    return clean_text(value.encode("ascii", "ignore").decode("ascii"))


def clean_values(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        cleaned = clean_text(value)
        if cleaned and cleaned not in result:
            result.append(cleaned)
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
    translation_failures: list[str] = field(default_factory=list)
    transliterated_name: str = ""
    transliterated_botanical_name: str | None = None
    transliterated_family: str | None = None

    def clean(self) -> PlantRecord:
        self.ayurvedic_name = clean_text(self.ayurvedic_name)
        self.botanical_name = clean_text(self.botanical_name) if self.botanical_name else None
        self.family = clean_text(self.family) if self.family else None
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
            cleaned_values = clean_values(clean_text(value) for value in values)
            if cleaned_values:
                cleaned_attributes[cleaned_field] = cleaned_values
        self.attributes = cleaned_attributes
        self.source_values = {
            clean_text(field): clean_text(value)
            for field, value in self.source_values.items()
            if clean_text(field) and clean_text(value)
        }
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
        if not self.source_record_id > 0:
            raise ValueError("source_record_id must be a positive integer")
        if not self.source_url.startswith(("http://", "https://")):
            raise ValueError("source_url must be an HTTP(S) URL")
        if not self.ayurvedic_name:
            raise ValueError("ayurvedic_name cannot be empty")


def split_values(value: str) -> list[str]:
    return clean_values(re.split(r"\s*(?:\n|;|\|)\s*", value))
