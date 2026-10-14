from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from pathlib import Path
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
LANGUAGE_CODES = {language: code for language, code in INDIAN_TRANSLATION_LANGUAGES.items()}


class GoogleNameTranslator:
    """Translate plant names with cached Google Translator requests."""

    def __init__(
        self,
        minimum_interval: float = 0.25,
        cache_path: str | Path | None = None,
    ) -> None:
        self._cache: dict[tuple[str, str], TranslationResult] = {}
        self._cache_path = Path(cache_path) if cache_path else None
        self._minimum_interval = minimum_interval
        self._last_request_at = 0.0

    def _load_cached(self, text: str, target: str) -> TranslationResult | None:
        if self._cache_path is None:
            return self._cache.get((text, target))
        with sqlite3.connect(self._cache_path) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS translation_cache (
                    source_text TEXT NOT NULL, target_language TEXT NOT NULL,
                    translated_text TEXT, status TEXT NOT NULL,
                    error TEXT, source_language TEXT NOT NULL,
                    PRIMARY KEY (source_text, target_language)
                )"""
            )
            row = connection.execute(
                "SELECT translated_text, status, error, source_language "
                "FROM translation_cache WHERE source_text = ? AND target_language = ?",
                (text, target),
            ).fetchone()
        if row is None:
            return None
        return TranslationResult(row[0], row[1], row[2], row[3])

    def translate(self, text: str, target: str) -> "TranslationResult":
        key = (text, target)
        cached = self._load_cached(text, target)
        if cached is not None:
            self._cache[key] = cached
            return cached
        try:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self._minimum_interval:
                time.sleep(self._minimum_interval - elapsed)
            translated = GoogleTranslator(source="auto", target=target).translate(text)
            self._last_request_at = time.monotonic()
        except Exception as error:
            result = TranslationResult(None, "failed", str(error), "auto")
        else:
            result = TranslationResult(
                clean_text(translated) if translated else None,
                "missing" if not translated else "success",
                None if translated else "empty response",
                "auto",
            )
        self._cache[key] = result
        if self._cache_path is not None:
            with sqlite3.connect(self._cache_path) as connection:
                connection.execute(
                    "INSERT OR REPLACE INTO translation_cache "
                    "(source_text, target_language, translated_text, status, error, source_language) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (text, target, result.value, result.status, result.error, result.source_language),
                )
        return result


@dataclass(frozen=True, slots=True)
class TranslationResult:
    value: str | None
    status: str
    error: str | None
    source_language: str


def _translation_result(value: TranslationResult | str | None) -> TranslationResult:
    if isinstance(value, TranslationResult):
        return value
    return TranslationResult(value, "success" if value else "missing", None, "auto")


def enrich_record(record: PlantRecord, translator: GoogleNameTranslator) -> PlantRecord:
    """Add English and Indian-language translations without replacing source values."""
    translated: dict[str, list[str]] = {"Translated Names.English": [record.ayurvedic_name]}

    for language, code in INDIAN_TRANSLATION_LANGUAGES.items():
        if language == "English":
            continue
        result = _translation_result(translator.translate(record.ayurvedic_name, code))
        result = TranslationResult(result.value, result.status, result.error, "sa")
        if result.value:
            translated[f"Translated Names.{language}"] = [result.value]
            record.attribute_metadata[f"Translated Names.{language}"] = {
                "source_language": result.source_language,
                "machine_generated": True,
                "verification_status": "unverified",
            }
        elif result.status == "failed":
            record.translation_failures.append(
                f"{record.ayurvedic_name}->{language}: {result.error or 'translation failed'}"
            )

    for field, values in record.attributes.items():
        if not field.startswith("Vernacular Names."):
            continue
        language = field.rsplit(".", 1)[-1]
        if language == "English":
            continue
        for value in values:
            result = _translation_result(translator.translate(value, "en"))
            result = TranslationResult(
                result.value,
                result.status,
                result.error,
                LANGUAGE_CODES.get(language, result.source_language),
            )
            if result.value:
                translated.setdefault("Translated Names.English", []).append(
                    ascii_text(result.value)
                )
                record.attribute_metadata["Translated Names.English"] = {
                    "source_language": result.source_language,
                    "machine_generated": True,
                    "verification_status": "unverified",
                }
            elif result.status == "failed":
                record.translation_failures.append(
                    f"{value}->English: {result.error or 'translation failed'}"
                )

    for field, values in translated.items():
        record.attributes[field] = clean_values(values)
        record.source_values[field] = " | ".join(record.attributes[field])
    return record.clean()