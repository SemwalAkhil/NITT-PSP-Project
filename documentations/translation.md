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
source-language detection, an in-memory cache, and a 0.25-second minimum
request interval. The cache prevents repeated requests for the same text and
target language, while the interval helps keep a large scrape below Google's
documented request rate.

Translation exceptions are converted to missing results. This keeps a source
record ingestible when Google Translator is unavailable, rate-limited, or
unable to translate a particular value.

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
English and added to `Translated Names.English`. Existing source attributes
are never overwritten.

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
SQLite layer. Database persistence remains deterministic and stores translated
attributes alongside all other record attributes.
