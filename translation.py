from __future__ import annotations

import time

from deep_translator import GoogleTranslator

from cleaning import PlantRecord, ascii_text, clean_text, clean_values


INDIAN_TRANSLATION_LANGUAGES = {
    "English": "en",
    "Assamese": "as",
    "Bengali": "bn",
    "Gujarati": "gu",
    "Hindi": "hi",
    "Kannada": "kn",
    "Malayalam": "ml",
    "Marathi": "mr",
    "Nepali": "ne",
    "Odia": "or",
    "Punjabi": "pa",
    "Sanskrit": "sa",
    "Tamil": "ta",
    "Telugu": "te",
    "Urdu": "ur",
}


class GoogleNameTranslator:
    """Translate plant names with cached Google Translator requests."""

    def __init__(self, minimum_interval: float = 0.25) -> None:
        self._cache: dict[tuple[str, str], str | None] = {}
        self._minimum_interval = minimum_interval
        self._last_request_at = 0.0

    def translate(self, text: str, target: str) -> str | None:
        key = (text, target)
        if key in self._cache:
            return self._cache[key]
        try:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self._minimum_interval:
                time.sleep(self._minimum_interval - elapsed)
            translated = GoogleTranslator(source="auto", target=target).translate(text)
            self._last_request_at = time.monotonic()
        except Exception:
            translated = None
        result = clean_text(translated) if translated else None
        self._cache[key] = result
        return result


def enrich_record(record: PlantRecord, translator: GoogleNameTranslator) -> PlantRecord:
    """Add English and Indian-language translations without replacing source values."""
    translated: dict[str, list[str]] = {"Translated Names.English": [record.ayurvedic_name]}

    for language, code in INDIAN_TRANSLATION_LANGUAGES.items():
        if language == "English":
            continue
        value = translator.translate(record.ayurvedic_name, code)
        if value:
            translated[f"Translated Names.{language}"] = [value]

    for field, values in record.attributes.items():
        if not field.startswith("Vernacular Names."):
            continue
        language = field.rsplit(".", 1)[-1]
        if language == "English":
            continue
        for value in values:
            english_value = translator.translate(value, "en")
            if english_value:
                translated.setdefault("Translated Names.English", []).append(
                    ascii_text(english_value)
                )

    for field, values in translated.items():
        record.attributes[field] = clean_values(values)
        record.source_values[field] = " | ".join(record.attributes[field])
    return record.clean()