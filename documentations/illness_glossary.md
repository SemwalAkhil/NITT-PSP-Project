# Multilingual Illness Glossary (`illness_glossary.py`)

## 1. Purpose
The `illness_glossary.py` module resolves Ayurvedic clinical conditions across 15 Indian languages using an in-memory glossary. It decouples multilingual terminology presentation from database storage, enabling localized UI exploration without schema changes.

## 2. Where it fits
- **Upstream callers:** Called by `web_app.py` for `/illnesses` pages, condition resolution filters, and REST APIs, as well as `database_operator.py` during search ranking.
- **Downstream dependencies:** Loads `data/illness_glossary.csv` via `importlib.resources` and checks `concept_catalog.py` for curated Stage C indication overrides.

## 3. Key functions and classes
- `LanguageLabel`: Specialized string holding a localized label alongside metadata (`language`, `script_name`, `origin`, `verification`).
- `ResolvedIllness`: Structured dictionary/object containing English name, original scraped term, localized labels for all 15 languages, and epistemic safety flags.
- `load_glossary()`: Reads and caches the 227-condition UTF-8 CSV glossary from package data.
- `tolerant_illness_key(term)`: Accepts raw transliterated term (e.g. "jvaraH"), returns phonetic normalized key by stripping visargas and normalizing consonants.
- `resolve_illness(term)`: Accepts condition name or scraped term, returns `ResolvedIllness` entity with catalog precedence applied.
- `search_glossary(query, limit=50)`: Searches conditions across English names, clinical synonyms, and 15 native Indic scripts.
- `get_catalog_csv_conflicts()`: Audits discrepancies between curated Stage C catalog labels and machine-generated CSV translations.

## 4. Worked example
```python
from herbal_almanac.illness_glossary import resolve_illness

res = resolve_illness("KAsa")
print(res.english)                   # "Cough"
print(res.get_label("hi"))           # "खांसी"
print(res.get_label("ta"))           # "இருமல்"
print(res.origin, res.verification)  # "catalog", "curated"
```

## 5. Glossary Notes & Epistemic Boundaries
- **Supported Languages (15):** English (`en`), Hindi (`hi`), Sanskrit (`sa`), Assamese (`as`), Bengali (`bn`), Gujarati (`gu`), Kannada (`kn`), Malayalam (`ml`), Marathi (`mr`), Nepali (`ne`), Odia (`or`), Punjabi (`pa`), Tamil (`ta`), Telugu (`te`), and Urdu (`ur`).
- **Data Source & Disclaimer:** 227 conditions derived from Gemini Deep Research. All CSV entries are marked `origin="machine_generated"` and `verification="unverified"`. They are research aids, not clinical medical advice.
- **Catalog Precedence:** Curated Stage C catalog terms (`concept_catalog.py`) strictly override CSV entries on conflict for English, Hindi, and Sanskrit while inheriting regional Indic scripts.
- **Phonetic Tolerance:** Normalizes Harvard-Kyoto capitalization, trailing visargas (`-H`, `-h`), and compound slashes (e.g. `khAlityam/khalati`).
