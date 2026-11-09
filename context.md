# Project Context: Herbal Almanac

## 1. Domain and purpose
Herbal Almanac is a research-oriented Python project for exploring Ayurvedic herbs, illness references, and herb–treatment relationships. The currently supported ingestion source is the CCRAS DRAVYA portal. The application exposes a Python package and a Typer CLI backed by SQLite.

This project is for research and software evaluation only; it is not medical advice. Scraped therapeutic associations and machine translations can be unverified.

## 2. Current repository structure
- `src/herbal_almanac/` — installable package using the `src/` layout.
  - `cleaning.py` — `PlantRecord`, text cleanup, transliteration, Dosha-expression normalization, and validation.
  - `scrapper.py` — DRAVYA discovery, HTTP retrieval, parsing, retries, and scrape orchestration.
  - `translation.py` — optional machine-translation support.
  - `database_operator.py` — `AyurvedicAlmanac`, SQLite schema, legacy compatibility migrations, versioned migrations, transactional CRUD, and search.
  - `cli.py` — Typer commands and JSON/CSV export.
- `tests/test_scrapper.py` — offline scraper, cleaning, translation, CLI, and legacy database regression tests.
- `tests/test_database_connections.py` — connection isolation, commit/rollback, closure, and foreign-key tests.
- `tests/test_database_initialization.py` — initialization concurrency, migration idempotence, rollback/retry, and closure tests.
- `tests/smoke_installed_package.py` — clean installed-package and CLI smoke test.
- `documentations/` — module docs, schema proposal, learning notes, and roadmap.
- `sample.html` and `data.txt` — local parser/terminology fixtures.

## 3. Runtime data model
The legacy application tables remain the active read/write contract:
- `herbs` — herb identity, source identity, original/transliterated names, botanical/family text, URL, and retrieval time.
- `illness` — condition names and search/canonical keys, with machine-generation and verification metadata.
- `treatment` — herb–illness relationships; `source` distinguishes scraped links from manual links.
- `herb_attributes` — section-qualified source values, vernacular names, source text/language, and translation metadata.
- `herb_doshas` — normalized Vata/Pitta/Kapha effects tied to their original Doshakarma expression.

Vernacular names are stored as `Vernacular Names.<Language>` attributes. Optional translations are added only when `--translate` is requested and are marked machine-generated/unverified. Therapeutic Usage values remain source attributes; the supported condition field also creates unverified illness rows and scraped treatment links. Re-scraping refreshes scraped relationships while preserving manual treatment links.

## 4. Versioned schema additions
The database operator applies additive migrations after legacy schema compatibility initialization:
- Migration 1 (`core_identity_and_provenance`) creates `schema_migrations`, `sources`, `source_records`, `source_claims`, `legacy_herb_map`, and `herb_names`.
- Migration 2 (`normalized_botanical_taxonomy`) creates `taxa`, `taxon_relationships`, and `herb_taxa`.

These migrations backfill source identity/provenance and conservative botanical taxonomy assertions. The legacy application continues to use the original tables; the new normalized tables are additive and do not yet replace legacy application reads or writes. Remaining normalized Dravyaguna domain tables described in `documentations/database_schema.md` are proposals, not implemented features.

Migration preflight rejects duplicate legacy source identities instead of guessing. Each migration body and its version-ledger row are committed transactionally. Migration 2 records botanical names at unknown rank and family values at family rank without inferring accepted status or taxonomy hierarchy.

## 5. SQLite lifecycle and concurrency
- Each operation obtains an independent SQLite connection; connections are not shared between worker threads.
- `connect()` enables foreign-key enforcement and returns `sqlite3.Row` objects.
- Ordinary read/CRUD operations use private `_connection()`, preserving transaction commit/rollback while always closing the connection.
- `create_database()` manages initialization separately, with an instance `RLock`, `BEGIN IMMEDIATE`, and a 10-second `busy_timeout` to coordinate concurrent initializers.
- The initialization tests cover same-instance threads, independent instances, migration idempotence, rollback/retry, and connection closure.

## 6. Installation and common commands
Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Initialize a selected database and run a small scrape:

```bash
herbal-almanac setup --database /tmp/ayurvedic.db
herbal-almanac scrape dravya --max-pages 1 --max-plants 5 --database /tmp/ayurvedic.db
```

Run the mandatory scraper regression and full test suite:

```bash
python -m pytest tests/test_scrapper.py -q
python -m pytest -q
```

Tests must remain offline and use fixtures, mocks/fakes, and temporary database paths.

## 7. Roadmap snapshot
- Publish a release candidate to TestPyPI when valid credentials are available.
- Continue normalized Dravyaguna schema migrations beyond identity/provenance and botanical taxonomy.
- Add further external source adapters only after the DRAVYA pipeline remains stable.
- Expand supported query capabilities and provide a dedicated public Python search API.
