# Multilingual Illness Glossary (`illness_glossary.py`)

## 1. Purpose

`src/herbal_almanac/illness_glossary.py` loads a packaged CSV glossary and provides lookup, normalization, and search for illness terminology.

The module helps connect illness names stored in the CCRAS-derived data with English and Indic-language display labels. It is designed to tolerate common Sanskrit transliteration variations and to use selected curated Stage C indication labels where a glossary entry matches a known catalog concept.

Its main responsibilities are:

- Load and index multilingual glossary records.
- Normalize transliterated illness terms for lookup.
- Resolve a term into a structured `ResolvedIllness` object.
- Search glossary records across English, original terms, synonyms, and language labels.
- Detect differences between selected catalog labels and CSV values.

The glossary is a terminology and presentation aid. Its translations are not automatically verified medical terminology.

## 2. Where It Fits in the Architecture

The module is used by:

- `web_app.py`, for multilingual illness labels, search, and illness-related API responses.
- `database_operator.py`, through the imported `canonical_illness_key()` normalization helper.
- `concept_catalog.py`, which supplies canonical Stage C indication concepts and their preferred labels.

The glossary does not add translation columns to SQLite. It loads the CSV as package data and creates an in-memory lookup store.

## 3. Imports and Dependencies

### Standard-library imports

| Import | Use |
|---|---|
| `csv` | Reads the glossary CSV |
| `importlib.resources` | Locates packaged CSV data |
| `re` | Applies transliteration normalization rules |
| `unicodedata` | Normalizes Unicode and removes combining marks |
| `lru_cache` | Caches the glossary store |
| `Any` | Type annotations for flexible metadata structures |

### Internal imports

| Import | Origin | Use |
|---|---|---|
| `CANONICAL_CONCEPTS` | `concept_catalog.py` | Supplies curated indication concepts and preferred labels |
| `canonical_illness_key` | `database_operator.py` | Applies the project's canonical illness-key normalization |

One additional dependency is imported locally inside `resolve_illness()`: `format_readable_illness` from `web_app.py`. It is used only for the unmatched-term fallback, rather than at module import time.

## 4. Constants and Language Configuration

### `SUPPORTED_LANGUAGES`

A dictionary describing 15 supported language codes:

| Code | Language |
|---|---|
| `en` | English |
| `hi` | Hindi |
| `sa` | Sanskrit |
| `bn` | Bengali |
| `gu` | Gujarati |
| `kn` | Kannada |
| `ml` | Malayalam |
| `mr` | Marathi |
| `ne` | Nepali |
| `or` | Odia |
| `pa` | Punjabi |
| `ta` | Tamil |
| `te` | Telugu |
| `ur` | Urdu |
| `as` | Assamese |

Each entry contains the language code, English name, native-language name, and corresponding CSV column name.

### `ORDERED_LANGUAGE_CODES`

Defines the order in which the application presents the supported languages.

### `NON_DISEASE_OR_PROCEDURE_TERMS`

Contains selected source terms classified as procedures or non-disease concepts. The classification is stored in the resolved record's `kind` field. This helps distinguish these entries from ordinary illness terminology.

### `CATALOG_INDICATION_KEYS`

Maps 24 Stage C `IND_*` concept codes to accepted canonical/transliteration aliases:
- `IND_JVARA`, `IND_KASA`, `IND_SHWASA`, `IND_PRAMEHA`, `IND_ARSHA`, `IND_ATISARA`
- `IND_GRAHANI`, `IND_KAMALA`, `IND_PANDU`, `IND_KUSHTHA`, `IND_SHOTHA`, `IND_AMAVATA`
- `IND_VATARAKTA`, `IND_AMLAPITTA`, `IND_KRIMI`, `IND_MUTRAKRICCHRA`, `IND_ASHMARI`, `IND_VRANA`
- `IND_DAHA`, `IND_CHARDI`, `IND_TRISHNA`, `IND_HRIDROGA`, `IND_UNMADA`, `IND_APASMARA`

These aliases are used to connect CSV original terms with canonical indication concepts.

## 5. Transliteration and Cell Helpers

### 5.1 `tolerant_illness_key(term: str) -> str`

Creates a tolerant normalized key for Sanskrit transliteration variants.

The implementation:

1. Applies Unicode NFKD normalization.
2. Removes combining marks.
3. Converts the text to lowercase.
4. Replaces `w` with `v`.
5. Normalizes selected sibilants (`sh` and `z`).
6. Simplifies selected affricate spellings (`cch`, `chh`, and `ch`).
7. Collapses repeated consonants.
8. Removes trailing `h` characters.
9. Removes non-alphanumeric characters.

This is a pragmatic matching key, not a formal Sanskrit transliteration standard. Because normalization is intentionally tolerant, it can also make distinct spellings converge to the same key.

### 5.2 `_split_slashed_cell(value: str) -> tuple[str, list[str]]`

Splits a CSV cell containing slash-separated alternatives.

For example:

```text
Primary Name / Synonym One / Synonym Two
```

becomes:

```python
("Primary Name", ["Synonym One", "Synonym Two"])
```

The first non-empty item becomes the primary value; the remaining items become synonyms.

## 6. Data Models

The module defines three classes.

### 6.1 `LanguageLabel`

Represents one localized label and its metadata.

Fields include:

- `label`
- `language_name`
- `native_name`
- `language_code`
- `synonyms`
- `raw_text`

It inherits from `dict` and also exposes the same values as object attributes. Its `__str__()` method returns the label text.

### 6.2 `ResolvedIllness`

Represents a resolved glossary term.

Important fields include:

- `matched`: whether the input matched a glossary record
- `key`: canonical illness key
- `english`: primary English label
- `english_synonyms`: English alternatives
- `labels`: language-code-to-`LanguageLabel` mapping
- `origin`: source/origin metadata
- `verification`: verification metadata
- `original_term`: original glossary or input term
- `kind`: optional procedure/non-disease classification
- `catalog_code`: matching Stage C indication code, when present
- `note`: optional explanatory note

It also inherits from `dict` while exposing values as object attributes.

Methods:

- `get_label(lang_code="en")`: returns the requested language label, falling back to English when the language or label is unavailable.
- `get_label_object(lang_code="en")`: returns the `LanguageLabel` object for the requested language, or `None`.

### 6.3 `GlossaryStore`

Maintains the in-memory glossary and its lookup indexes.

It stores:

- `records`: loaded `ResolvedIllness` records
- `by_canonical_key`: canonical-key index
- `by_tolerant_key`: tolerant-key index
- `by_original_term`: original-term index
- `by_english_term`: English primary-label and synonym index
- `conflicts`: detected catalog-versus-CSV disagreements

Construction calls `_load()` to populate the indexes.

## 7. Glossary Loading and Catalog Precedence

### 7.1 `_load_catalog_indications()`

Reads `CANONICAL_CONCEPTS` and selects concepts whose codes begin with `IND_`.

For each selected concept, it collects preferred labels. It specifically distinguishes Sanskrit Devanagari and Latin-script labels, while collecting preferred labels for other available languages.

The resulting mapping is used during CSV loading.

### 7.2 `_load()`

Loads the packaged resource:

```text
herbal_almanac/data/illness_glossary.csv
```

It uses `importlib.resources.files()` so the data can be located as package data rather than relying on the process's current working directory.

The loading sequence is:

1. Read the CSV using UTF-8 and `csv.DictReader`.
2. Load the Stage C indication labels.
3. Build canonical and tolerant alias indexes for the configured `IND_*` concepts.
4. Iterate through CSV rows.
5. Split the English cell into a primary label and synonyms.
6. Classify selected procedure/non-disease terms.
7. Create `LanguageLabel` objects for the non-English columns.
8. Check whether the original term or one of its slash-separated parts matches a catalog alias.
9. Record detected disagreements between selected catalog labels and CSV values.
10. Apply catalog precedence for English, Hindi, and Sanskrit when a preferred catalog label is available.
11. Create a `ResolvedIllness` record.
12. Add the record to the exact, canonical, tolerant, English, and compound-part indexes.

### Catalog precedence is limited

The current implementation overrides the primary English, Hindi, and Sanskrit labels when a matching catalog concept supplies those labels.

Other language labels remain sourced from the CSV. The record's `origin` and `verification` values are still initialized as:

```python
origin="machine_generated"
verification="unverified"
```

Therefore, a record matching a curated catalog concept should not be interpreted as meaning that all of its translations have become curated or verified.

### Conflict tracking

When a catalog match is found, the loader compares selected catalog labels with the CSV values and appends disagreements to `GlossaryStore.conflicts`.

This is diagnostic metadata. The loader does not rewrite the CSV file.

## 8. Public Functions

### 8.1 `get_glossary_store() -> GlossaryStore`

Returns the cached singleton glossary store.

The function uses:

```python
@lru_cache(maxsize=1)
```

The CSV is therefore loaded and indexed once per process under normal use, rather than being re-read for every lookup.

### 8.2 `resolve_illness(name: str | None) -> ResolvedIllness`

Resolves an input term into a `ResolvedIllness`.

The lookup order is:

1. Exact original-term lookup.
2. Canonical illness-key lookup.
3. Tolerant transliteration-key lookup.
4. English primary-label or synonym lookup.
5. Slash-separated compound-part lookup.

If no match is found, the function:

- Uses `format_readable_illness()` from `web_app.py` to make the input more readable.
- Returns `matched=False`.
- Keeps the original input term.
- Provides no translated label objects.
- Sets a `"translation not available"` note for an empty input.

The fallback changes the display representation, not the stored database term.

### 8.3 `search_glossary(query: str) -> list[ResolvedIllness]`

Searches glossary records across:

- English primary labels
- English synonyms
- Original terms
- Canonical and tolerant normalized keys
- Raw localized labels across the supported language columns

The query is Unicode NFC-normalized and lowercased for text matching. Canonical and tolerant keys are also computed for transliteration matching.

The function avoids returning the same record more than once by tracking its canonical record key.

**Current API detail:** `search_glossary()` accepts only `query`. It does not currently define a `limit` parameter.

### 8.4 `get_catalog_csv_conflicts() -> list[dict[str, Any]]`

Returns the conflict records collected by the cached glossary store.

Each conflict identifies:

- The catalog concept code
- The original glossary term
- The language-specific disagreement values

It reports differences; it does not resolve them by editing either source.

## 9. Example

```python
from herbal_almanac.illness_glossary import (
    resolve_illness,
    search_glossary,
)

result = resolve_illness("KAsa")

print(result.matched)
print(result.english)
print(result.get_label("hi"))
print(result.get_label("ta"))

matches = search_glossary("cough")
for illness in matches:
    print(illness.english)
```

The exact resolved labels depend on the packaged CSV and the current canonical concept catalog.

## 10. Data Provenance and Limitations

- The glossary is loaded from packaged CSV data, not from SQLite translation columns.
- CSV-derived labels are marked `machine_generated` and `unverified` by the current implementation.
- Catalog precedence applies only to matching concepts and the English, Hindi, and Sanskrit labels described above.
- Regional-language translations continue to depend on the CSV.
- Tolerant transliteration normalization can produce collisions between different spellings.
- Conflict records are diagnostic and do not automatically modify source data.
- A successful glossary match is a terminology match, not confirmation of a clinical diagnosis.
- The glossary is a research and navigation aid, not medical advice.
