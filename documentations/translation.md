# Translation Enrichment

`translation.py` adds optional Google Translator enrichment without replacing
source values.

## Supported targets

The current target set is:

- English
- Assamese
- Bengali
- Gujarati
- Hindi
- Kannada
- Malayalam
- Marathi
- Nepali
- Odia
- Punjabi
- Sanskrit
- Tamil
- Telugu
- Urdu

The language codes are the Google Translator codes used by
`deep-translator`.

## `GoogleNameTranslator`

`GoogleNameTranslator` wraps `deep_translator.GoogleTranslator` with automatic
source-language detection, an in-memory cache, an optional SQLite-backed
cache, and a 0.25-second minimum request interval. Cached entries include the
result status, error, and source-language metadata, so failed requests are not
repeated on later runs.

`TranslationResult.status` distinguishes `success`, `missing` (an empty
response), and `failed` (an exception with its reason). Source values remain
available when either non-success status occurs.

## `enrich_record()`

`enrich_record(record, translator)` adds attributes in this form:

```text
Translated Names.English
Translated Names.Hindi
Translated Names.Bengali
...
```

The record's primary English name is translated into each configured regional
language. Existing `Vernacular Names.<Language>` values are translated back to
English and added to `Translated Names.English`. Existing source attributes are never overwritten. Generated attributes carry
`source_language`, `machine_generated`, and `verification_status=unverified`
metadata. Botanical names and medical terminology are therefore not treated as
validated facts merely because a machine translation exists.

The function returns the cleaned record. English-facing values use ASCII
normalization, so diacritics and symbols do not remain in English output:

```text
Kāsa           -> Kasa
📚 Etymology   -> Etymology
```

Regional translated values retain their native scripts.

## Runtime behavior

The scraper creates one translator per run and enriches each plant after HTML
parsing and before validation/database insertion. Complete translation output
requires network access to Google Translator. A failed translation does not
fail the scrape; the source value remains available in its original attribute.

Translation is intentionally performed during scraping rather than inside the
SQLite layer. Database persistence stores translated attributes and their
metadata alongside all other record attributes. The scraper supplies its
database path to the translator so the cache persists across runs.
