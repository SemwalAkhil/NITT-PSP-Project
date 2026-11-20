# Offline Demo Database Generator (`scripts/make_demo_db.py`)

## 1. Purpose

`scripts/make_demo_db.py` builds a local SQLite database for demonstrating Herbal Almanac without scraping a live website.

It combines:

- A local HTML fixture (`sample.html`).
- The existing database initialization workflow.
- Two manually inserted illness records.
- Treatment relationships connecting the sample herb to those illnesses.
- Stage C schema upgrade and canonical concept seeding.
- Stage C semantic backfill.

The result is a populated database that can be used with the local web interface.

## 2. Where It Fits in the Architecture

This is a standalone project script, not a module inside `src/herbal_almanac/`.

Its execution flow is:

```text
scripts/make_demo_db.py
          |
          +---- sample.html
          |         |
          |         v
          |      parse_plant()
          |
          +---- database_operator.py
          |         |
          |         +---- create_database()
          |         +---- insert_record()
          |         +---- add_illness()
          |         +---- add_treatment()
          |         +---- upgrade_to_stage_c()
          |         +---- run_stage_c_backfill()
          |
          v
      data/demo.db
          |
          v
     web_app.py
```

The script is useful for demonstrations and local evaluation because it does not need a live CCRAS request to obtain its sample herb record.

## 3. Imports and Dependencies

### Standard-library imports

| Import | Responsibility |
|---|---|
| `argparse` | Parses command-line arguments |
| `Path` | Handles fixture and database paths |
| `sys` | Imported by the current script; not used in the shown implementation |

### Internal imports

| Imported symbol | Origin | Responsibility |
|---|---|---|
| `AyurvedicAlmanac` | `herbal_almanac.database_operator` | Database creation, insertion, upgrade, and backfill operations |
| `parse_plant` | `herbal_almanac.scrapper` | Parses the local HTML fixture into a plant record |

The script does not import or call the network scraping function `scrape()`. It uses the parser directly.

## 4. Module Constant

### `PROJECT_ROOT`

```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent
```

Resolves the repository root by moving two directory levels upward from the script file.

This is used to locate:

- `sample.html`
- The default `data/demo.db` output location

The script therefore does not rely on the terminal's current working directory for these default paths.

## 5. Main Function: `build_demo_database()`

```python
def build_demo_database(
    database_path: Path | str | None = None,
    sample_path: Path | str | None = None,
) -> Path:
```

This function performs the complete demo database construction and returns the database path.

### Step 1: Determine the output path

If `database_path` is omitted, the default is:

```text
data/demo.db
```

Otherwise, the supplied path is converted to a `Path`.

### Step 2: Create the parent directory

```python
db_path.parent.mkdir(parents=True, exist_ok=True)
```

Ensures the target directory exists before creating the database.

### Step 3: Remove an existing database file

```python
if db_path.exists():
    db_path.unlink()
```

**Warning:** Destructive operation: If the target database file already exists, it is deleted before rebuilding to ensure a clean, deterministic state.

The script deletes an existing file at the selected target path before rebuilding the database.

This makes the output deterministic, but it also means any existing database at that path is lost. The script does not first back up the file or ask for confirmation.

**Do not point this script at a database containing data you need to preserve.**

### Step 4: Initialize the baseline database

```python
almanac = AyurvedicAlmanac(db_path)
almanac.create_database()
```

Creates the database and applies the baseline migrations through the database operator.

The script's documented starting point is Schema Version 2.

### Step 5: Load and parse the local fixture

If `sample_path` is omitted, the script uses:

```text
sample.html
```

It checks that the fixture exists and raises `FileNotFoundError` if it does not.

The file is read as UTF-8:

```python
html_content = sample_file.read_text(encoding="utf-8")
```

The HTML is converted into a plant record:

```python
record = parse_plant(
    plant_id=1,
    url="https://example.com/plant/1",
    html=html_content,
)
```

The URL is supplied as a parsing context value; this script does not fetch that URL.

### Step 6: Insert the plant record

```python
almanac.insert_record(record)
```

Inserts the parsed record into the database.

The script then searches the database for herbs:

```python
herbs = almanac.search_herbs("")
```

If no herb is found, it raises a `RuntimeError`.

The first returned herb ID is used for the manual treatment relationships.

### Step 7: Add two manual illnesses

The script creates:

```python
illness_1 = almanac.add_illness("Digestive Weakness")
illness_2 = almanac.add_illness("Chronic Fatigue")
```

These are demonstration records, not illnesses extracted from the HTML fixture.

### Step 8: Add treatment relationships

The sample herb is linked to both manually created illnesses:

```python
almanac.add_treatment(herb_id=herb_id, illness_id=illness_1)
almanac.add_treatment(herb_id=herb_id, illness_id=illness_2)
```

This creates the relationships needed for treatment-related demonstrations.

### Step 9: Upgrade to Stage C

```python
almanac.upgrade_to_stage_c()
```

Applies the Stage C schema upgrade and seeds the canonical concept catalog through the database operator.

### Step 10: Run semantic backfill

```python
almanac.run_stage_c_backfill()
```

Runs the semantic backfill process to populate normalized concept mappings and derived semantic records from eligible source claims.

### Step 11: Return the database path

The function returns `db_path`.

The function does not call `.resolve()` before returning, so a relative path supplied by the caller remains relative.

## 6. Command-Line Entry Point: `main()`

The script uses `argparse` to expose one option:

| Option | Purpose |
|---|---|
| `--database` / `-d` | Target database path; defaults to `data/demo.db` |

It then:

1. Calls `build_demo_database()`.
2. Resolves the resulting path for display.
3. Prints the database location.
4. Prints a command for starting the web application with that database.

Example:

```bash
python scripts/make_demo_db.py
```

Custom output path:

```bash
python scripts/make_demo_db.py --database data/my_demo.db
```

The script has no command-line option for `sample_path`; that parameter is available when calling `build_demo_database()` programmatically.

## 7. Launching the Demo Web Application

After generating the database, the script prints launch instructions.

Linux/macOS:

```bash
HERBAL_ALMANAC_DATABASE=/absolute/path/to/data/demo.db \
uvicorn herbal_almanac.web_app:app
```

Windows PowerShell:

```powershell
$env:HERBAL_ALMANAC_DATABASE="C:\absolute\path\to\data\demo.db"
uvicorn herbal_almanac.web_app:app
```

The web application reads the environment variable when it creates its default application instance.

## 8. Example Programmatic Usage

```python
from pathlib import Path
from scripts.make_demo_db import build_demo_database

database_path = build_demo_database(
    database_path=Path("data/demo-local.db"),
    sample_path=Path("sample.html"),
)

print(database_path)
```

This call rebuilds the selected target database file if it already exists.

## 9. What the Demo Database Contains

The construction logic guarantees that it attempts to create:

- One plant record parsed from the local fixture.
- Two manually added illness records.
- Two treatment relationships connecting the plant to those illnesses.
- A Stage C schema upgrade.
- Canonical concept catalog seeding.
- Semantic backfill output.

The exact number of concepts, labels, mappings, and derived semantic records depends on the current catalog, fixture content, and backfill behavior. The script does not hard-code those counts.

## 10. Design Boundaries and Limitations

- The script is a demo-data builder, not a production ingestion workflow.
- It uses a local fixture rather than scraping a live site.
- The manual illness records are illustrative demonstration data.
- It deletes an existing target database before rebuilding it.
- It does not back up the previous database.
- It does not accept a custom sample fixture through its CLI, although the Python function supports `sample_path`.
- It upgrades the generated database to Stage C and runs backfill; it should not be treated as a neutral Schema Version 2 fixture.
- It does not guarantee fixed row counts across future catalog or fixture changes.

Use a separate disposable database path for demonstrations and tests.
