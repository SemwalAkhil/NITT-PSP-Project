# Command Line Interface (`cli.py`)

## 1. Purpose
The `cli.py` module exposes the Typer command-line interface for the Herbal Almanac package. It allows users to initialize schemas, scrape online records, query herbs and conditions, manage data exports, and perform Stage C upgrades.

## 2. Where it fits
- **Upstream callers:** Invoked from terminal shells via the `herbal-almanac` entry point, or via `python -m herbal_almanac` (routed through `__main__.py`). The top-level package `__init__.py` exposes core classes and delegates execution to `cli.main()`.
- **Downstream dependencies:** Calls `database_operator.py` for database CRUD, `scrapper.py` for web scraping, and `schema_capability_gate.py` for migration inspection.

## 3. Key functions and classes
- `app`: The primary `typer.Typer` application object registering all CLI subcommands.
- `main()`: Entry point function that executes the Typer CLI runner.
- `setup(database, force)`: CLI command to create legacy and Stage B tables on a target SQLite file.
- `scrape(source, max_pages, max_plants, database, translate)`: CLI command to scrape botanical records from CCRAS DRAVYA.
- `upgrade_stage_c(database)`: CLI command to apply Migration 3 DDL, seed the concept catalog, and run semantic backfill.
- `stage_c_status(database)`: CLI command to inspect schema version and count Stage C concepts and mappings.

## 4. Worked example
```bash
# Initialize database and upgrade to Stage C semantic model
herbal-almanac setup --database data/ayurvedic.db
herbal-almanac upgrade-stage-c --database data/ayurvedic.db

# Search herbs by common or transliterated name
herbal-almanac herbs --query "Tulsi" --database data/ayurvedic.db
```
