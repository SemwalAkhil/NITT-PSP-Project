# Machine Translation (`translation.py`)

## 1. Purpose
The `translation.py` module provides optional English machine-translation enrichment for Hindi and Sanskrit plant names. It isolates third-party translation providers behind a strict protocol so translation failures never block ingestion.

## 2. Where it fits
- **Upstream callers:** Invoked conditionally during scraping when `--translate` is enabled or in offline tests with mock translators.
- **Downstream dependencies:** Optionally imports `deep_translator` (via `pip install -e ".[translate]"`).

## 3. Key functions and classes
- `TranslatorProtocol`: Structural typing protocol defining the expected `translate(text: str) -> str` interface for translation backends.
- `DeepTranslatorAdapter`: Concrete wrapper around GoogleTranslator from `deep-translator` implementing `TranslatorProtocol`.
- `translate_plant_record(record, translator=None)`: Translates Hindi and Sanskrit name attributes on a `PlantRecord`, marking added names as `machine_generated=True` and `verification_status="unverified"`.

## 4. Worked example
```python
from herbal_almanac.cleaning import PlantRecord
from herbal_almanac.translation import translate_plant_record

class MockTranslator:
    def translate(self, text: str) -> str:
        return "Holy Basil" if "तुलसी" in text else text

record = PlantRecord(source="TEST", source_record_id=1, source_url="https://example.org",
                     retrieved_at="2026-11-20T00:00:00Z", ayurvedic_name="तुलसी")
enriched = translate_plant_record(record, translator=MockTranslator())
print(enriched.attributes.get("Vernacular Names.English"))  # ['Holy Basil']
```
