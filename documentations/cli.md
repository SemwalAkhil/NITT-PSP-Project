# Command-Line Interface

This document explains how [`cli.py`](./cli.py) provides access to the Herbal
Almanac database and scraper.

## Overview

The CLI is implemented with [Typer](https://typer.tiangolo.com/) and uses
Rich for table output. It provides commands for:

- Creating the SQLite database schema.
- Scraping the supported DRAVYA website.
- Adding herbs, illnesses, and treatment relationships manually.
- Searching herbs and illnesses.
- Viewing treatment relationships.
- Viewing or exporting all stored records.

Run the CLI from the project root:

```bash
python cli.py
```

Running the CLI without a command displays the available commands. General and
command-specific help are also available:

```bash
python cli.py --help
python cli.py scrape --help
```

## Database selection

Every database command uses `AyurvedicDB.db` by default. Use `--database` or
`-d` to select another SQLite file:

```bash
python cli.py setup --database /tmp/herbal-almanac.db
python cli.py herbs tulsi --database /tmp/herbal-almanac.db
```

The selected database path is passed to `AyurvedicAlmanac`, which enables
SQLite foreign-key enforcement and creates the schema when needed.

## Commands

### `setup`

Creates the database tables and applies the existing schema migrations.

```bash
python cli.py setup
python cli.py setup --database /tmp/herbal-almanac.db
```

The command creates the `herbs`, `illness`, `treatment`, and
`herb_attributes` tables if they do not already exist.

### `scrape`

Scrapes a supported source and inserts each validated record directly into the
database. The only currently supported source is `dravya`.

```bash
python cli.py scrape dravya
```

Useful options:

```bash
python cli.py scrape dravya \
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

The scraper displays a progress bar and advances only after a plant has been
parsed, validated, and inserted successfully.

### `herb`

Adds one manually entered herb:

```bash
python cli.py herb "Tulsi"
python cli.py herb "Tulsi" \
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
python cli.py illness "Cough"
```

Illness names are required and unique. Attempting to insert a duplicate name
returns an error from the database constraint.

### `treatment`

Creates a relationship between an existing herb and an existing illness:

```bash
python cli.py treatment HERB_ID ILLNESS_ID
```

Both IDs must be positive integers and must already exist. SQLite foreign keys
prevent relationships to missing records. Duplicate herb/illness relationships
are also rejected.

### `herbs`

Searches herb names and botanical names. An empty query lists all matching
herbs:

```bash
python cli.py herbs tulsi
python cli.py herbs
```

Results are displayed as a Rich table.

### `illnesses`

Searches illness names:

```bash
python cli.py illnesses fever
python cli.py illnesses
```

### `treatments`

Lists illnesses associated with one herb ID:

```bash
python cli.py treatments HERB_ID
```

### `attributes`

Lists all source attributes stored for a herb, including the normalized field
name, individual value, and original source text:

```bash
python cli.py attributes HERB_ID
```

Attributes for an individual herb can also be exported:

```bash
python cli.py attributes HERB_ID --output attributes.json
python cli.py attributes HERB_ID --format csv --output attributes.csv
```

When a scraped record contains a field such as `Therapeutic Usage` or
`Therapeutic Uses`, each cleaned value in that field is also inserted as an
illness and linked to the herb in `treatment`. Existing illness names and
links are reused, so re-scraping is safe and does not create duplicates.

### `records`

Displays all stored records, or only one record group:

```bash
python cli.py records
python cli.py records herbs
python cli.py records illnesses
python cli.py records treatments
python cli.py records attributes
```

Valid record groups are `all`, `herbs`, `illnesses`, `treatments`, and
`attributes`.

Records can be exported to JSON or CSV with `--output`/`-o`:

```bash
python cli.py records all --output records.json
python cli.py records herbs --output herbs.csv
python cli.py records attributes --output attributes.csv
```

The format is inferred from the file extension. It can also be specified
explicitly:

```bash
python cli.py records all --format json --output records.json
python cli.py records treatments --format csv --output treatments.csv
```

The JSON export preserves separate `herbs`, `illnesses`, and `treatments`
and `attributes` arrays. CSV exports flatten the selected records into one file
and add a `record_type` column. Treatment exports include both IDs and the
related herb and illness names. Attribute exports include the herb ID, herb
name, field name, value, and original source text.

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
# Install dependencies and create the schema.
pip install -r requirements.txt
python cli.py setup

# Import source data.
python cli.py scrape dravya --max-plants 10

# Inspect imported records.
python cli.py herbs
python cli.py illnesses
python cli.py records treatments

# Add a manual relationship.
python cli.py herb "Ashwagandha"
python cli.py illness "Fatigue"
python cli.py treatment HERB_ID ILLNESS_ID

# Back up the database contents.
python cli.py records all --format json --output herbal-almanac.json
```
