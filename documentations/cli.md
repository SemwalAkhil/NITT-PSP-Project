# Command-Line Interface

This document explains how [`src/herbal_almanac/cli.py`](../src/herbal_almanac/cli.py)
provides access to the Herbal Almanac database and scraper.

## Overview

The CLI is implemented with [Typer](https://typer.tiangolo.com/) and uses
Rich for table output. It provides commands for:

- Creating the SQLite database schema.
- Scraping the supported DRAVYA website.
- Adding herbs, illnesses, and treatment relationships manually.
- Searching herbs and illnesses.
- Viewing treatment relationships.
- Viewing or exporting all stored records.

Install the project from the repository root, which also configures the
`herbal-almanac` command:

```bash
pip install -e .
herbal-almanac
```

Running the CLI without a command displays the available commands. General and
command-specific help are also available:

```bash
herbal-almanac --help
herbal-almanac scrape --help
```

## Database selection

Every database command uses the per-user writable
`herbal-almanac/AyurvedicDB.db` location by default. SQLite files are generated
runtime artifacts and are not tracked in the repository or written into the
installed package. Use `--database` or `-d` to select another SQLite file; use
a new path when you need a clean rebuild rather than an in-place migration:

```bash
herbal-almanac setup --database /tmp/herbal-almanac.db
herbal-almanac herbs tulsi --database /tmp/herbal-almanac.db
```

The selected database path is passed to `AyurvedicAlmanac`, which enables
SQLite foreign-key enforcement and creates the schema when needed.
Herb and illness commands display only matches meeting the operator's
relevance cutoff; an empty query still lists all records.
Database and filesystem errors from setup and read commands are reported as
CLI errors instead of exposing uncaught exceptions.

## Commands

### `setup`

Creates the database tables and applies the existing schema migrations.

```bash
herbal-almanac setup
herbal-almanac setup --database /tmp/herbal-almanac.db
```

The command creates the `herbs`, `illness`, `treatment`, and
`herb_attributes` tables if they do not already exist.

### `scrape`

Scrapes a supported source and inserts each validated record directly into the
database. The only currently supported source is `dravya`.

```bash
herbal-almanac scrape dravya
```

Useful options:

```bash
herbal-almanac scrape dravya \
  --database /tmp/herbal-almanac.db \
  --max-pages 1 \
  --max-plants 5 \
  --timeout 10 \
  --retries 1
```

- `--max-pages`: limits directory pages visited.
- `--max-plants`: limits plant records processed.
- `--timeout`: sets the HTTP read timeout in seconds.
- `--retries`: sets the number of retry attempts for supported temporary
  failures.
- `--record-retries`: retries a plant after parsing, translation, validation,
  or database failure.
- `--failure-report`: writes failed plant IDs, URLs, attempts, and reasons to
  a JSON report.
- `--translate`: enables optional machine translation enrichment. It is
  disabled by default because it makes many external requests. Install the
  optional dependency first with `pip install "herbal-almanac[translate]"`.

The scraper displays a progress bar, continues after isolated plant failures,
and retries failed plants separately. Failed records are reported without
committing incomplete database transactions.

During scraping, the Ayurvedic/Sanskrit name from the source heading is the
primary herb name when available. All language-specific names are
also stored as attributes with fields such as `Vernacular Names.Hindi` and
`Vernacular Names.Malayalam`. Translation enrichment adds corresponding
`Translated Names.<Language>` attributes when Google Translator is explicitly
enabled.
Unicode source names are preserved in exports through `original_name` and
source attributes. The compatibility `english_name` field contains the ASCII
Harvard-Kyoto-style transliteration (`Kāsa` is searchable as `KAsa`).
Manual treatment links are preserved when a herb is scraped again.

### `herb`

Adds one manually entered herb:

```bash
herbal-almanac herb "Tulsi"
herbal-almanac herb "Tulsi" \
  --botanical-name "Ocimum tenuiflorum" \
  --family "Lamiaceae" \
  --source "Manual"
```

Available options:

- `--botanical-name`: botanical name.
- `--family`: botanical family.
- `--source`: source name.
- `--source-record-id`: positive source-specific record ID.
- `--source-url`: HTTP or HTTPS source URL.
- `--database`, `-d`: target database.

The herb name is required and cannot be empty. Invalid source IDs and
non-HTTP(S) source URLs are rejected.

### `illness`

Adds one illness:

```bash
herbal-almanac illness "Cough"
```

Illness names are required and unique. Attempting to insert a duplicate name
returns an error from the database constraint.

### `treatment`

Creates a relationship between an existing herb and an existing illness:

```bash
herbal-almanac treatment HERB_ID ILLNESS_ID
```

Both IDs must be positive integers and must already exist. SQLite foreign keys
prevent relationships to missing records. Duplicate herb/illness relationships
are also rejected.

### `herbs`

Searches herb names and botanical names. An empty query lists all matching
herbs:

```bash
herbal-almanac herbs tulsi
herbal-almanac herbs
```

Results are displayed as a Rich table.

### `illnesses`

Searches illness names:

```bash
herbal-almanac illnesses fever
herbal-almanac illnesses
```

### `treatments`

Lists illnesses associated with one herb ID:

```bash
herbal-almanac treatments HERB_ID
```

### `attributes`

Lists all source attributes stored for a herb, including the normalized field
name, individual value, and original source text:

```bash
herbal-almanac attributes HERB_ID
```

Attributes for an individual herb can also be exported:

```bash
herbal-almanac attributes HERB_ID --output attributes.json
herbal-almanac attributes HERB_ID --format csv --output attributes.csv
```

When a scraped record contains a field such as `Therapeutic Usage` or
`Therapeutic Uses`, values from the source `Therapeutic Usage.Name` condition
field are inserted as unverified illnesses and linked to the herb in
`treatment`. Existing illness names and links are reused, so re-scraping is
safe and does not create duplicates.

### `records`

Displays all stored records, or only one record group:

```bash
herbal-almanac records
herbal-almanac records herbs
herbal-almanac records illnesses
herbal-almanac records treatments
herbal-almanac records attributes
```

Valid record groups are `all`, `herbs`, `illnesses`, `treatments`, and
`attributes`.

Records can be exported to JSON or CSV with `--output`/`-o`:

```bash
herbal-almanac records all --output records.json
herbal-almanac records herbs --output herbs.csv
herbal-almanac records attributes --output attributes.csv
```

The format is inferred from the file extension. It can also be specified
explicitly:

```bash
herbal-almanac records all --format json --output records.json
herbal-almanac records treatments --format csv --output treatments.csv
```

When the output filename has no extension, specify `--format json` or
`--format csv`; the command reports the missing format against `--output`.

The JSON export preserves separate `herbs`, `illnesses`, and `treatments`
and `attributes` arrays. CSV exports flatten the selected records into one file
and add a `record_type` column. Treatment exports include both IDs and the
related herb and illness names. Attribute exports include the herb ID, herb
name, field name, value, and original source text.

To export vernacular attributes, select the `attributes` record group:

```bash
herbal-almanac records attributes --format json --output attributes.json
```

The CLI writes exactly the selected record group to the requested output path.
Missing parent directories are created automatically. Empty CSV exports still
include the complete header for their selected record group.

`--format` requires `--output`, and only `json` and `csv` are supported.

## Error handling and constraints

The CLI reports invalid input and database errors as user-facing error
messages and exits with status code `1`. It does not silently discard failed
operations.

Database integrity is enforced by both CLI validation and SQLite constraints:

- Required names cannot be empty.
- Herb source IDs must be positive when supplied.
- Herb source URLs must use HTTP or HTTPS.
- Illness names are unique.
- Treatment relationships require existing herb and illness IDs.
- The same treatment relationship cannot be inserted twice.

## Typical workflow

```bash
# Install the package and create the schema.
pip install -e .
herbal-almanac setup

# Import source data.
herbal-almanac scrape dravya --max-plants 10

# Inspect imported records.
herbal-almanac herbs
herbal-almanac illnesses
herbal-almanac records treatments

# Add a manual relationship.
herbal-almanac herb "Ashwagandha"
herbal-almanac illness "Fatigue"
herbal-almanac treatment HERB_ID ILLNESS_ID

# Back up the database contents.
herbal-almanac records all --format json --output herbal-almanac.json
```
