from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata
from typing import Iterable


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
    """Return readable English text using only standard ASCII characters."""
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

    def clean(self) -> PlantRecord:
        self.ayurvedic_name = ascii_text(self.ayurvedic_name)
        self.botanical_name = ascii_text(self.botanical_name) if self.botanical_name else None
        self.family = ascii_text(self.family) if self.family else None
        cleaned_attributes: dict[str, list[str]] = {}
        for field, values in self.attributes.items():
            cleaned_field = clean_text(field)
            if not cleaned_field:
                continue
            language = cleaned_field.rsplit(".", 1)[-1]
            preserve_regional = (
                cleaned_field.startswith("Vernacular Names.")
                or cleaned_field.startswith("Translated Names.") and language != "English"
            )
            clean_value = clean_text if preserve_regional else ascii_text
            cleaned_values = clean_values(clean_value(value) for value in values)
            if cleaned_values:
                cleaned_attributes[cleaned_field] = cleaned_values
        self.attributes = cleaned_attributes
        self.source_values = {
            clean_text(field): (
                clean_text(value)
                if (
                    clean_text(field).startswith("Vernacular Names.")
                    or clean_text(field).startswith("Translated Names.")
                )
                and clean_text(field).rsplit(".", 1)[-1] != "English"
                else ascii_text(value)
            )
            for field, value in self.source_values.items()
            if clean_text(field) and clean_text(value)
        }
        return self

    def validate(self) -> None:
        if not self.source_record_id > 0:
            raise ValueError("source_record_id must be a positive integer")
        if not self.source_url.startswith(("http://", "https://")):
            raise ValueError("source_url must be an HTTP(S) URL")
        if not self.ayurvedic_name:
            raise ValueError("ayurvedic_name cannot be empty")


def split_values(value: str) -> list[str]:
    return clean_values(re.split(r"\s*(?:\n|;|\|)\s*", value))
