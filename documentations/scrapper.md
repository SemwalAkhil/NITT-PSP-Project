# Scraper

This document explains the design and execution flow of `scrapper.py`.

The scraper is an orchestration module. It discovers source records, downloads
HTML, parses tables, creates `PlantRecord` objects, validates them, and sends
them to the database operator. It does not own text-cleaning rules or SQL.

## Sources

| Status | Capability |
|---|---|
| Implemented | DRAVYA URL discovery |
| Implemented | DRAVYA HTML download with retries and timeouts |
| Implemented | DRAVYA section and vernacular-card parsing |
| Implemented | `PlantRecord` contract, cleaning, and validation |
| Implemented | Optional translation enrichment |
| Implemented | Direct SQLite insertion and upsert |
| Implemented | Per-plant recovery, retries, and structured scrape-error reporting |
| Planned | Dosha normalization |
| Planned | API PDF and NAMASTE Excel importers |
| Planned | Botanical taxonomy resolution |

## Current direct-ingestion flow

```text
DRAVYA directory
      ↓
Plant URL discovery
      ↓
HTTP fetch with retries and timeout
      ↓
Semantic table parsing
      ↓
Cleaning
      ↓
Google translation enrichment
      ↓
Validation
      ↓
SQLite upsert
```

The parser keeps each plant as an in-memory `PlantRecord`. It does not create
an intermediate JSON file. The original source URL, source record ID, source
values, and retrieval timestamp are stored with the database record.

## Components

### `create_session()`

Creates a reusable `requests.Session` with a descriptive User-Agent, two
retries by default, exponential backoff, and retries for temporary `429`,
`500`, `502`, `503`, and `504` responses. Read retries are disabled because a
slow response should not be repeated automatically. A session centralizes HTTP
behavior for every directory and plant request.

### `fetch()`

Fetches one URL with a 15-second default timeout, then calls
`raise_for_status()`. Timeouts, network errors, and permanent HTTP failures
remain visible to the caller.

### `discover_plants()`

Requests directory pages in sequence:

```text
/all_plants?page=1
/all_plants?page=2
...
```

Each link is checked against the compiled `/plant/<id>` pattern. IDs are
stored in a dictionary, so duplicate links do not create duplicate work.
Transient empty pages are tolerated; discovery terminates only after two
consecutive pages add no IDs or when `max_pages` is reached. The scrape report
includes the total discovered, pages fetched, and termination reason.

### `_normalize_label()`

Removes numeric prefixes and surrounding punctuation from DRAVYA labels. For
example, `1. Parts Used` becomes `Parts Used`, and `1.1 Name` becomes `Name`.
This keeps source presentation numbering out of database field names.

### `_section_name()`

Finds the accordion heading or nearest `h3` associated with a table and
normalizes it with `_normalize_label()`. The section is retained as context
for every column in that table.

### `_table_attributes()`

Treats each HTML table as a relational table: the first row containing `th`
cells is the header row, and later rows contain values for those headers. Each
value is stored under a section-qualified field such as
`Parts Used.Name` or `Therapeutic Usage.Name`.

Values are split on the supported source delimiters, deduplicated by the
`PlantRecord.clean()` stage, and accumulated in `source_values` so repeated
rows preserve all source wording instead of overwriting earlier rows. Empty
cells are ignored and rows are limited to the number of detected headers.

This uses table structure and nearby section headings instead of fixed table
indexes, so changes in table ordering are less likely to break extraction.

### `_vernacular_attributes()`

Extracts the separate `Vernacular Names` card, where each language is shown as
a badge followed by a name paragraph. Each language becomes an attribute such
as `Vernacular Names.Assamese` or `Vernacular Names.English`. Source spelling
aliases are canonicalized, including `Malyalam` to `Malayalam` and `Oriya` to
`Odia`.

Vernacular attributes and source values are merged into the same record
before cleaning and persistence. The source title's text after ` - ` becomes
the primary `ayurvedic_name`/database `original_name` when present; the first
English vernacular value remains the `Vernacular Names.English` attribute.
This avoids promoting incorrect English values published by some source pages.
Its ASCII transliteration is stored in the compatibility `english_name` field.

### `parse_plant()`

Builds one `PlantRecord`. It extracts the source heading, the live scientific
profile's scientific and family values, every parsed table and
vernacular-name attribute, and source ID, URL, and the current UTC timestamp.
The record is cleaned before being returned.

### Translation enrichment

`scrape()` creates one cached `GoogleNameTranslator` and passes each cleaned
record to `enrich_record()`. The primary Ayurvedic name is translated into the
configured major Indian languages, and each source vernacular name is also
translated back to English. Results are stored as attributes such as
`Translated Names.Hindi` and `Translated Names.English`; source
`Vernacular Names.*` attributes are never overwritten.

Translation requests are cached and throttled for the duration of a scrape.
Individual Google Translator failures are treated as missing enrichment rather
than causing the source record to fail. A live network connection is therefore
needed for complete translation output, but scraping remains usable when
translation is unavailable.

### `scrape()`

Runs the complete direct-ingestion workflow:

```text
create session
      ↓
discover plant URLs
      ↓
limit pages/plants if requested
      ↓
create database schema
      ↓
fetch each plant page
      ↓
parse and clean PlantRecord
      ↓
validate record
      ↓
upsert record and attributes into SQLite
```

The return value is a `ScrapeReport` containing the successful count and
structured failures with plant ID, URL, attempt count, exception type, and
reason. Each failed plant is retried in a separate pass according to
`record_retries`; a permanently failed plant does not stop other plants.
`failure_report_path` writes the same report as JSON. The CLI displays a
`rich.progress` bar and exposes both options as `--record-retries` and
`--failure-report`.

When the parsed attributes contain a `Therapeutic Usage` field, the database
operator creates unverified illness links for every value in the source
`Therapeutic Usage.Name` condition field. Controlled-vocabulary validation is
deferred; other therapeutic values remain attributes.

### `main()`

Provides the command-line interface. Importing `scrapper.py` does not make
network requests; execution starts only through `scrape()` or the CLI entry
point.

## Why there is no JSON stage

The ingestion path uses direct SQLite insertion. `PlantRecord` gives the
parser, cleaner, validator, and database operator a typed hand-off without
creating a second persisted source representation. Raw HTML and database
provenance are retained. JSON and CSV are available as explicit CLI exports
after persistence, but neither is an intermediate scrape stage.

## Current limitations

- HTML caching and resuming discovery itself are not yet implemented; rerun
  with the same database and failure report to retry failed source records.
- Translation enrichment depends on the availability and rate limits of
      Google Translator through `deep-translator`.
- Flexible table fields are stored as section-qualified attributes. Illness and
      treatment relationships are currently normalized from the source
      condition field and marked unverified; other domain-specific relationships
      remain attributes.
- Rate limiting between requests should be added before a large production
  scrape.

## Usage

Create the schema and scrape one page during development:

```bash
python scrapper.py --max-pages 1 --max-plants 1
```

Use a separate database for a test run:

```bash
python scrapper.py --database /tmp/ayurvedic-test.db --max-plants 5
```

For an unreliable or slow source, the network limits can be changed:

```bash
python scrapper.py --max-plants 1 --timeout 5 --retries 0
```

The scraper records network, parsing, validation, and database errors for the
affected plant, retries that plant according to `--record-retries`, and
continues with other records. Use `--failure-report` to write the structured
failure details as JSON. Ctrl+C exits with status 130 and closes the HTTP
session cleanly.

The Typer CLI is the preferred project entry point:

```bash
python cli.py setup
python cli.py scrape --max-pages 1 --max-plants 5
python cli.py herbs tulsi
python cli.py illnesses fever
```

Manual records can be inserted while preserving database constraints:

```bash
python cli.py herb "Tulsi" --botanical-name "Ocimum tenuiflorum"
python cli.py illness "Cough"
python cli.py treatment HERB_ID ILLNESS_ID
python cli.py treatments HERB_ID
```

Duplicate illness names, duplicate treatment links, missing foreign keys, empty
names, invalid source IDs, and invalid source URLs are rejected with a CLI
error instead of being silently accepted.