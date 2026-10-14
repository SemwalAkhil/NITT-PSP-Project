from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata
from typing import Iterable


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    return " ".join(value.split())


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
        self.ayurvedic_name = clean_text(self.ayurvedic_name)
        self.botanical_name = clean_text(self.botanical_name) if self.botanical_name else None
        self.family = clean_text(self.family) if self.family else None
        self.attributes = {
            clean_text(field): clean_values(values)
            for field, values in self.attributes.items()
            if clean_text(field) and clean_values(values)
        }
        self.source_values = {
            clean_text(field): clean_text(value)
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
