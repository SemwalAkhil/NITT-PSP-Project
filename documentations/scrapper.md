# Scraper

This document explains the design and execution flow of `scrapper.py`.

The scraper is an orchestration module. It discovers source records, downloads
HTML, parses tables, creates `PlantRecord` objects, validates them, and sends
them to the database operator. It does not own text-cleaning rules or SQL.

## Sources
STEP 1   DRAVYA URL discovery
STEP 2   DRAVYA HTML downloader + cache
STEP 3   DRAVYA section parser
STEP 4   parsed source-record contract
STEP 5   cleaning and normalization
STEP 6   validation + deduplication
STEP 7   direct SQLite insertion
STEP 8   deterministic Dosha normalizer
STEP 9   API PDF parser
STEP 10  NAMASTE Excel importer
STEP 11  botanical taxonomy resolver

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
Cleaning and validation
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

Fetches one URL with a 5-second connection timeout and a 15-second default
read timeout, then calls `raise_for_status()`. Timeouts, network errors, and
permanent HTTP failures remain visible to the caller.

### `discover_plants()`

Requests directory pages in sequence:

```text
/all_plants?page=1
/all_plants?page=2
...
```

Each link is checked against the compiled `/plant/<id>` pattern. IDs are
stored in a dictionary, so duplicate links do not create duplicate work. The
function stops when a later page produces no new IDs or `max_pages` is
reached, then returns sorted `(plant_id, absolute_url)` pairs.

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
before cleaning and persistence. When an English vernacular value exists,
its first value becomes the record's primary `ayurvedic_name`/database
`english_name`; otherwise the page heading remains the fallback name.

### `parse_plant()`

Builds one `PlantRecord`. It extracts a heading or page title as the fallback
name, identifies scientific/botanical name and family fields when present,
records every parsed table and vernacular-name attribute, and adds source ID,
URL, and the current UTC timestamp. When available, the first English
vernacular name replaces the fallback heading as the primary plant name. The
record is cleaned before being returned.

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

The return value is the number of successfully inserted or updated records.
During the plant-ingestion loop, the CLI displays a `rich.progress` bar with
the completed count and estimated time remaining. A plant is counted only
after its record has been validated and inserted successfully.

When the parsed attributes contain a `Therapeutic Usage` field, the database
operator converts each condition value into an illness and links it to the
current herb through the treatment join table. Re-scraping the same herb
replaces its current attributes and treatment links, preventing stale source
relationships.

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

- HTML caching is planned but not yet implemented.
- Flexible table fields are stored as section-qualified attributes. Illness and
      treatment relationships are currently normalized only from the source's
      `Therapeutic Usage` section; other domain-specific relationships remain
      attributes.
- A failed plant stops the current run instead of being accumulated into a
  structured error report.
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

The scraper raises network, parsing, validation, and database errors instead
of silently treating a failed record as successful. Ctrl+C exits with status
130 and closes the HTTP session cleanly.

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