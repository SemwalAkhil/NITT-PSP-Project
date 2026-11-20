# Data Cleaning & Plant Records (`cleaning.py`)

## 1. Purpose
The `cleaning.py` module cleans and normalizes raw text extracted from HTML and establishes the primary in-memory record model. It handles Unicode NFC normalization, ASCII transliteration, and rule-based Dosha expression parsing before database ingestion.

## 2. Where it fits
- **Upstream callers:** Called directly by `scrapper.py` during web parsing and by `database_operator.py` during validation and search key generation.
- **Downstream dependencies:** Pure standard-library module relying on Python's `unicodedata`, `re`, and `dataclasses`.

## 3. Key functions and classes
- `PlantRecord`: Dataclass holding normalized plant identity, flexible attribute dictionaries, provenance URLs, and timestamps; serves as the shared data contract between scraper and database.
- `clean_text(value)`: Accepts a raw string, returns cleaned Unicode NFC text with normalized whitespace and preserved Devanagari joiners.
- `ascii_text(value)`: Accepts a Unicode string, returns ASCII romanization with Harvard-Kyoto phonetic transliterations.
- `normalize_dosha_expression(expression)`: Accepts a raw Dravyaguna string (e.g. "Kaphavatahara"), returns a dictionary of normalized directional effects (`decrease`, `increase`, or `unspecified`) for Vata, Pitta, and Kapha.

## 4. Worked example
```python
from herbal_almanac.cleaning import clean_text, normalize_dosha_expression

cleaned = clean_text("  तुलसी   (Holy Basil)  ")
doshas = normalize_dosha_expression("Kapha-Vata shamana")
print(cleaned)  # "तुलसी (Holy Basil)"
print(doshas)   # {'vata': 'decrease', 'pitta': 'unspecified', 'kapha': 'decrease'}
```
