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
whitespace, removes leading and trailing whitespace, and removes emoji and
Unicode symbol/format characters. It preserves the Devanagari
zero-width joiner (`U+200D`) and zero-width non-joiner (`U+200C`), which are
required for correct half-consonant and conjunct rendering. NFC preserves
Devanagari and Sanskrit text while making equivalent Unicode sequences
consistent.

### `ascii_text()`

`ascii_text(value)` is used for English-facing fields. It first applies NFC
normalization so decomposed Sanskrit diacritics are handled consistently. It applies
Harvard-Kyoto-style romanization before removing unsupported symbols and
returns ASCII text. This keeps Sanskrit distinctions such as `ś` (`z`) and
`ṣ` (`S`) instead of collapsing every sibilant to `s`; uppercase `Ś` maps to
`Z` while lowercase `ś` maps to `z`. It also uses the Harvard-Kyoto nasal
mappings `ṅ` (`G`), `ñ` (`J`), and `ṇ` (`N`). For example, `Kāsa` becomes
`KAsa` and `📚 Etymology` becomes `Etymology`.

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
| `ayurvedic_name` | Unicode-normalized plant name from the source. |
| `botanical_name` | Unicode-normalized scientific/botanical name, when available. |
| `family` | Unicode-normalized botanical family, when available. |
| `attributes` | Parsed fields mapped to Unicode-normalized value lists. |
| `source_values` | Cleaned source field text for provenance. |
| `transliterated_name` | ASCII transliteration for compatibility/search indexing. |
| `transliterated_botanical_name` | ASCII botanical-name transliteration, when available. |
| `transliterated_family` | ASCII family-name transliteration, when available. |

### `PlantRecord.clean()`

`clean()` normalizes identity fields, attribute names, attribute values, and
source text. It returns the same record after updating it, allowing the parser
to construct and clean a record in one expression.

It also normalizes `source` and `retrieved_at`. Optional text fields use the
same cleanup path and become `None` when empty after normalization.

Attribute fields that normalize to the same name are merged in source order,
with cleaned duplicate values retained only once.

Optional botanical and family fields that clean to empty text are stored as
`None`, keeping them consistent with their optional transliteration fields.

Identity fields, attributes, and source values retain Unicode after NFC
normalization. `ascii_text()` is used only to populate the explicit
`transliterated_*` fields; it never replaces source data. The database keeps
the normalized name in `original_name` and uses the transliteration in the
legacy `english_name` search column.

### Typed attribute classification

`CONDITION_FIELDS` identifies the source's `Therapeutic Usage.Name` column.
Every value from that column is labeled `disease` by
`PlantRecord.typed_attributes()` and ingested as an unverified condition.
Controlled-vocabulary mapping is intentionally deferred. Values from other
fields remain `ambiguous` and do not create treatment relationships.

### `PlantRecord.validate()`

Validation rejects empty `source` and `retrieved_at` values, non-positive
source IDs, HTTP(S) URLs without a hostname, non-HTTP(S) URLs, and empty
Ayurvedic names. Errors are raised instead of producing a successful-looking
record.

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

The module provides deterministic text cleanup only. Google translation is
kept in `translation.py` so cleaning remains independent of network access.
Domain-specific Dosha normalization and condition mapping should be added as
separate deterministic functions once the source expressions and rules are
defined.