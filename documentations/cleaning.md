# Cleaning and Plant Records

## Purpose

`cleaning.py` is the boundary between unstructured HTML extraction and the
database layer. The scraper finds and parses source values; this module
prepares those values for storage without handling SQL.

This separation keeps Unicode handling, whitespace cleanup, and validation out
of `database_operator.py`. It also makes cleanup behavior testable with
in-memory records.

## Components

### `clean_text()`

`clean_text(value)` applies Unicode NFC normalization, collapses runs of
whitespace, and removes leading and trailing whitespace. NFC preserves
Devanagari and Sanskrit diacritics while making equivalent Unicode sequences
consistent.

### `clean_values()`

`clean_values(values)` cleans every value, removes empty values, and removes
duplicates while preserving the original order.

### `split_values()`

`split_values(value)` splits one source value on newlines, semicolons, and
pipe characters, then applies the normal value cleanup.

### `PlantRecord`

`PlantRecord` is the typed in-memory contract shared by the scraper, cleaner,
validator, and database operator.

| Field | Purpose |
|---|---|
| `source` | Source system, currently `CCRAS DRAVYA`. |
| `source_record_id` | Stable plant ID from the source URL. |
| `source_url` | URL used to retrieve the source record. |
| `retrieved_at` | UTC retrieval timestamp. |
| `ayurvedic_name` | Main plant name from the source. |
| `botanical_name` | Scientific/botanical name, when available. |
| `family` | Botanical family, when available. |
| `attributes` | Parsed fields mapped to cleaned value lists. |
| `source_values` | Original extracted field text for provenance. |

### `PlantRecord.clean()`

`clean()` normalizes identity fields, attribute names, attribute values, and
source text. It returns the same record after updating it, allowing the parser
to construct and clean a record in one expression.

### `PlantRecord.validate()`

Validation currently rejects non-positive source IDs, non-HTTP(S) URLs, and
empty Ayurvedic names. Errors are raised instead of producing a successful
looking record.

## Data flow

```text
HTML tables and vernacular-name cards
      ↓
scrapper table/card parsers
      ↓
PlantRecord
      ↓
PlantRecord.clean()
      ↓
PlantRecord.validate()
      ↓
database_operator.insert_record()
```

The cleaner does not distinguish between ordinary attributes and vernacular
attributes. Fields such as `Vernacular Names.English` pass through the same
normalization path as `Parts Used.Name` or `Therapeutic Usage.Name`, preserving
their section and language in the field name.

The module currently provides general cleanup only. Domain-specific Dosha
normalization and condition mapping should be added as separate deterministic
functions once the source expressions and rules are defined.