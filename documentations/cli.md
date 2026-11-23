# Command Line Interface (`cli.py`)

## 1. Purpose

`src/herbal_almanac/cli.py` implements the `herbal-almanac` terminal command using Typer.

It provides commands to:

- Initialize a database.
- Scrape CCRAS DRAVYA records.
- Insert individual herbs, illnesses, and treatment relationships.
- Search and inspect existing records.
- Export records and herb attributes to JSON or CSV.
- Upgrade a database to Stage C.
- Inspect the current Stage C migration version and record counts.

The CLI is an operational interface over the existing database and scraping modules. It does not implement the underlying scraping or database schema logic itself.

## 2. Entry Point and Architecture

The command-line entry point is registered in `pyproject.toml`:

```toml
[project.scripts]
herbal-almanac = "herbal_almanac.cli:main"
```

The execution flow is:

```text
Terminal
   |
   v
herbal-almanac
   |
   v
cli.main()
   |
   v
Typer app
   |
   +---- database_operator.py
   |
   +---- scrapper.py
   |
   +---- schema_capability_gate.py
   |
   +---- SQLite database
```

The module also supports direct execution:

```bash
python -m herbal_almanac.cli
```

## 3. Imports and Dependencies

### Standard-library imports

| Import | Responsibility |
|---|---|
| `csv` | Writes CSV exports |
| `json` | Writes JSON exports |
| `sqlite3` | Handles SQLite exceptions and reads Stage C status |
| `Path` | Handles output and database paths |
| `Any` | Flexible record type annotations |
| `NoReturn` | Indicates that the error helper exits instead of returning |

### Third-party imports

| Import | Responsibility |
|---|---|
| `requests` | Identifies HTTP request exceptions from scraping |
| `Console` | Rich terminal output |
| `Table` | Formats database records and status reports |
| `typer` | Defines command-line commands, arguments, and options |

### Internal imports

| Imported symbol | Origin | Use |
|---|---|---|
| `AyurvedicAlmanac` | `database_operator.py` | Database operations |
| `default_database_path` | `database_operator.py` | Default database location |
| `ScraperError` | `scrapper.py` | Scraping-specific error handling |
| `scrape` | `scrapper.py` | Executes the scraping workflow |
| `MigrationError` | `schema_capability_gate.py` | Imported migration error type |
| `validate_schema_migration_ledger` | `schema_capability_gate.py` | Validates the migration sequence |

## 4. Global Objects and Constants

### `app`

The main Typer application:

```python
app = typer.Typer(
    name="herbal-almanac",
    help="Manage the Herbal Almanac database and data sources.",
    no_args_is_help=True,
)
```

All commands are registered on this object using `@app.command()`.

### `console`

A Rich `Console` instance used to display formatted tables.

### `DEFAULT_DATABASE_PATH`

Computed using `default_database_path()` and converted to a string. Most commands use this path unless the user supplies `--database`.

### `CSV_FIELDS`

Defines preferred CSV column order for:

- `herbs`
- `illnesses`
- `treatments`
- `attributes`
- `doshas`

Additional columns discovered in the records are appended during export.

## 5. Helper Functions

### 5.1 `database(path: str) -> AyurvedicAlmanac`

A small factory that returns an `AyurvedicAlmanac` instance for the given database path.

This avoids repeating the constructor call in every command.

### 5.2 `show_rows(rows, title) -> None`

Displays a list of dictionaries as a Rich table.

Logic:

1. If the list is empty, prints `No matching records.`
2. Uses the first dictionary's keys as the table columns.
3. Converts non-`None` values to strings.
4. Displays the table through the Rich console.

The function assumes records in a result set share a compatible structure.

### 5.3 `resolve_export_format(output, file_format) -> str | None`

Determines whether an export should be JSON or CSV.

Rules:

- If `--format` is supplied, it must be `json` or `csv`.
- Explicit `--format` requires `--output`.
- If only `--output` is supplied, the filename extension determines the format.
- Only `.json` and `.csv` extensions are accepted.
- If neither option is supplied, returns `None`, meaning the command should display records in the terminal.

Invalid combinations raise `typer.BadParameter`.

### 5.4 `fail(error: Exception) -> NoReturn`

Centralized command error handling.

It:

1. Prints the error message to standard error.
2. Raises `typer.Exit(code=1)`.

This ensures handled operational failures produce a non-zero CLI exit status.

### 5.5 `write_records(records, output, file_format) -> None`

Writes grouped records to JSON or CSV.

**JSON path:**

- Creates parent directories when necessary.
- Serializes the complete record dictionary.
- Uses indentation and `ensure_ascii=False` to preserve Unicode.
- Writes UTF-8 text with a trailing newline.

**CSV path:**

1. Flattens record groups into individual rows.
2. Adds a `record_type` column to identify the source group.
3. Starts with the preferred columns in `CSV_FIELDS`.
4. Adds any additional fields found in the records.
5. Writes the header and rows using `csv.DictWriter`.

CSV is a flattened representation; JSON preserves the original record-group structure.

### 5.6 `show_record_groups(records) -> None`

Iterates over each record type and calls `show_rows()` to display it as a separate terminal table.

## 6. CLI Commands

### 6.1 `setup`

```bash
herbal-almanac setup --database data/almanac.db
```

Creates the database schema and applies the migrations through:

```python
database(database_path).create_database()
```

The database path defaults to `DEFAULT_DATABASE_PATH`.

Handled errors include filesystem, validation, and SQLite errors.

### 6.2 `scrape`

```bash
herbal-almanac scrape dravya --database data/almanac.db
```

Arguments and options:

| Parameter | Purpose |
|---|---|
| `site` | Supported source; currently only `dravya` |
| `--database` / `-d` | Target database |
| `--max-pages` | Maximum pages to process |
| `--max-plants` | Maximum plants to process |
| `--timeout` | Request timeout; default 15 seconds |
| `--retries` | General retry count; default 2 |
| `--record-retries` | Per-record retry count; default 1 |
| `--failure-report` | Optional failure-report destination |

The command rejects unsupported site names before invoking the scraper.

It calls:

```python
scrape(
    database_path,
    max_pages,
    max_plants,
    timeout,
    retries,
    record_retries,
    failure_report,
)
```

It reports the number of processed records and, when applicable, the number of failures.

### 6.3 `herb`

```bash
herbal-almanac herb "Tulsi" \
  --database data/almanac.db \
  --botanical-name "Ocimum tenuiflorum" \
  --family "Lamiaceae"
```

Inserts one herb through `AyurvedicAlmanac.add_herb()`.

Optional metadata includes:

- Botanical name
- Family
- Source
- Source record ID
- Source URL

The database layer performs the actual field validation and insertion.

### 6.4 `illness`

```bash
herbal-almanac illness "Digestive Weakness" --database data/almanac.db
```

Inserts one illness using `add_illness()`.

The command documentation notes that duplicate illness names are rejected by the database schema.

### 6.5 `treatment`

```bash
herbal-almanac treatment 1 2 --database data/almanac.db
```

Links an existing herb ID to an existing illness ID through `add_treatment()`.

Both IDs must be positive integers.

### 6.6 `herbs`

```bash
herbal-almanac herbs "Tulsi" --database data/almanac.db
```

Searches herb records by common or botanical name using `search_herbs()` and displays the results.

The search string is a positional argument, not a `--query` option.

### 6.7 `illnesses`

```bash
herbal-almanac illnesses "fever" --database data/almanac.db
```

Searches illness records through `search_illnesses()`.

### 6.8 `treatments`

```bash
herbal-almanac treatments 1 --database data/almanac.db
```

Displays treatment details associated with a herb ID using `treatment_details()`.

### 6.9 `attributes`

```bash
herbal-almanac attributes 1 --database data/almanac.db
```

Retrieves all source attributes for a herb using `herb_attributes()`.

It can display the records in the terminal or export them:

```bash
herbal-almanac attributes 1 \
  --database data/almanac.db \
  --output exports/tulsi_attributes.json
```

Explicit format is also supported:

```bash
herbal-almanac attributes 1 \
  --database data/almanac.db \
  --output exports/tulsi_attributes.dat \
  --format csv
```

The extension is not required to match the explicitly selected format.

### 6.10 `records`

```bash
herbal-almanac records all --database data/almanac.db
```

Displays all records or a selected group.

Accepted record types:

- `all`
- `herbs`
- `illnesses`
- `treatments`
- `attributes`
- `doshas`

Export examples:

```bash
herbal-almanac records all \
  --database data/almanac.db \
  --output exports/all_records.json

herbal-almanac records herbs \
  --database data/almanac.db \
  --output exports/herbs.csv
```

The command retrieves `all_records()` and selects the requested group before displaying or exporting.

### 6.11 `upgrade-stage-c`

```bash
herbal-almanac upgrade-stage-c --database data/almanac.db
```

This is a database-changing operation.

The command:

1. Requires an explicit database path.
2. Checks that the target database file exists.
3. Requests interactive confirmation unless `--yes` is supplied.
4. Calls `upgrade_to_stage_c()`.
5. Calls `run_stage_c_backfill()`.
6. Prints a summary of migration, catalog seeding, and backfill counts.

The summary can include:

- Schema version
- Seeded canonical concepts
- Seeded multilingual labels
- Seeded authoritative sources
- Processed source claims
- Inserted concept mappings
- Inserted properties
- Inserted plant parts
- Inserted Dosha effects
- Inserted preparations
- Inserted indications

For non-interactive execution:

```bash
herbal-almanac upgrade-stage-c \
  --database data/almanac.db \
  --yes
```

`--yes` skips the confirmation prompt; it does not make the operation read-only or reversible.

### 6.12 `stage-c-status`

```bash
herbal-almanac stage-c-status --database data/almanac.db
```

Checks the migration ledger and displays the schema version.

For a valid version-3 database, it also counts records in:

- `dravyaguna_concepts`
- `concept_labels`
- `concept_claim_mappings`
- `herb_dravyaguna_properties`
- `herb_dosha_effects`
- `herb_plant_parts`
- `herb_preparations`
- `herb_indications`

For version 2, it reports that Stage C is not active and points to the upgrade command.

The command opens the database directly with `sqlite3` and closes the connection in a `finally` block.

## 7. Main Entry Point

### `main() -> None`

```python
def main() -> None:
    app()
```

Starts the Typer application and dispatches the requested command.

The module's `if __name__ == "__main__"` block calls `main()` when the file is executed directly.

## 8. CLI ↔ Web Feature Parity Matrix

Every database manipulation and inspection operation available via the CLI is mirrored by a corresponding Web GUI view, form, or export endpoint:

| CLI Command | Equivalent Web GUI Route / Method | Notes & Parity Behavior |
|---|---|---|
| `herbal-almanac setup` | Automatic on startup or DB connection | Initializes tables and migration ledger. |
| `herbal-almanac scrape` | Documented in `/stage-c/status` | Scraping is an intensive batch operation reserved for the CLI to avoid web worker starvation and request timeouts. |
| `herbal-almanac herb` | `GET /herbs/add`, `POST /herbs/add` | Interactive web form with client & server-side validation and CSRF origin verification. |
| `herbal-almanac illness` | `GET /illnesses/add`, `POST /illnesses/add` | Web form to add conditions with unique-name constraint enforcement. |
| `herbal-almanac treatment` | `GET /treatments/add`, `POST /treatments/add` | Form with searchable herb and illness dropdowns. |
| `herbal-almanac herbs [q] [-l]` | `GET /herbs?q=...&language=...` | Multilingual search supporting English, Latin, Sanskrit, Hindi, Tamil, etc., with thumbnail images. |
| `herbal-almanac illnesses [q]` | `GET /illnesses?q=...&language=...` | Condition explorer with Indic language selector bar and machine-translation indicators. |
| `herbal-almanac treatments <id>` | `GET /treatments?q=...` or `/herbs/{id}` | Paginated treatments directory with filtering by herb or illness name. |
| `herbal-almanac attributes <id>` | `GET /attributes` & `GET /herbs/{id}/attributes` | Raw attribute tables with provenance, field filtering, and CSV export. |
| `herbal-almanac records [type]` | `GET /records?group=...` | Interactive records hub with live counts and group inspection tabs. |
| `herbal-almanac records --output` | `GET /export/{herbs,illnesses,treatments}.{csv,json}` | One-click downloads with UTF-8 BOM encoding and formula injection protection. |
| `herbal-almanac upgrade-stage-c` | `POST /stage-c/upgrade` | One-click upgrade with confirmation dialog on `/stage-c/status`. |
| `herbal-almanac dravyaguna-profile`| `GET /herbs/{id}` & `/api/stage-c/herbs/{id}/profile` | Classical 6-domain semantic view, virya consensus, and 3-dosha matrix. |
| *(Web Only)* | `POST /herbs/{id}/photo`, `POST /herbs/{id}/photo/delete` | Local photo contributions with filesystem storage and magic-byte format validation. |

## 9. Typical Workflow

A normal local workflow might be:

```bash
# Create the baseline database
herbal-almanac setup --database data/almanac.db

# Inspect herbs
herbal-almanac herbs "Tulsi" --database data/almanac.db

# Inspect a herb's legacy attributes
herbal-almanac attributes 1 --database data/almanac.db

# Export the complete database
herbal-almanac records all \
  --database data/almanac.db \
  --output exports/almanac.json

# Inspect the schema capability
herbal-almanac stage-c-status --database data/almanac.db
```

Stage C upgrade should be performed only when intentionally upgrading the target database and after verifying that the migration and backfill workflow is ready for that database.

## 9. Design Boundaries and Limitations

- The CLI delegates database operations to `AyurvedicAlmanac`.
- Scraping behavior belongs to `scrapper.py`.
- Migration-ledger validation belongs to `schema_capability_gate.py`.
- JSON exports preserve grouped records; CSV exports flatten them and add `record_type`.
- `stage-c-status` checks the ledger and then queries expected Stage C tables; it is not a complete schema integrity audit.
- `upgrade-stage-c` performs schema upgrade and semantic backfill. It is not a read-only status command.
- The CLI does not provide a general-purpose SQL console or claim-review interface.
