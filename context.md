# Project Context: Herbal Almanac

## 1. Domain & Purpose
Herbal Almanac catalogs Ayurvedic herbs, illnesses, and their therapeutic relationships. It ingests botanical and clinical data from the CCRAS DRAVYA portal into a relational SQLite database and exposes both a Python API and a Typer CLI.

*Disclaimer: For research and software evaluation only, not medical advice.*

## 2. Repository Structure
- `src/herbal_almanac/` — Main package source (`src/` layout).
  - `cleaning.py` — `PlantRecord` data model, `clean_text`, Unicode normalization, and Harvard-Kyoto ASCII transliteration.
  - `database_operator.py` — `AyurvedicAlmanac` class, SQLite connection lifecycle, schema initialization, migration locking, CRUD, fuzzy search, and transactional upserts.
- `tests/test_scrapper.py` — Offline scraper/database regression test suite.
- `tests/test_database_connections.py` — Independent connections, transaction rollback, connection closure, and foreign-key tests.
- `tests/test_database_initialization.py` — Concurrent initialization, migration idempotence, rollback/retry, and schema tests.
- `documentations/` — Detailed module docs (`cli.md`, `scrapper.md`, `cleaning.md`, `database_operator.md`, `translation.md`, `plan.md`, `learnings.md`).
- `documentations/database_schema.md` — Proposed normalized Dravyaguna schema, provenance model, ER diagram, and staged migration design.
- `sample.html` — Saved DRAVYA HTML fixture for offline parser development.
- `data.txt` — Sanskrit terminology/reference sample.

## 3. Data Model & Attributes
- **Primary Herb Name:** Derived from the source title's Ayurvedic/Sanskrit name when present.
- **Vernacular Names:** Stored in `herb_attributes` as `Vernacular Names.<Language>` (for example, `Vernacular Names.Hindi`).
- **Translated Names:** Generated via `deep-translator` only when `--translate` is passed; stored as `Translated Names.<Language>` and flagged as machine-generated and unverified.
- **Illness & Treatment Links:** Normalized from `Therapeutic Usage` fields into `Illnesses` and `Treatment` join tables. Manual treatment links are preserved across scrapes.
- **Dosha Expressions:** Doshakarma expressions are parsed independently by Dosha/effect group; mixed, unknown, and conflicting expressions are handled conservatively, then persisted with their original source expressions in `herb_doshas`.
- **Schema Design:** A normalized multi-source Dravyaguna schema has been documented without changing the existing SQLite schema or migrations.
- **Schema Refinement:** The proposal uses source-record-owned, reusable claims, one names table with typed synonyms, non-null claim references for domain rows, append-only manual curation, and NULL-safe unique indexes.
- **Migration 1:** Core identity/provenance tables (`schema_migrations`, `sources`, `source_records`, `source_claims`, `legacy_herb_map`, and `herb_names`) are implemented additively; legacy application reads and writes remain active.
- **Migration 1 Integrity:** Duplicate legacy source identities fail before backfill, null IDs retain explicit artifact references, and application-level claim validation prevents cross-herb name associations under the documented manual-claim policy.
- **Migration 2:** Botanical taxonomy tables (`taxa`, `taxon_relationships`, and `herb_taxa`) are implemented additively with source-claim provenance; legacy botanical names use unknown rank and family values use family rank without inferred hierarchy or acceptance.

## 4. SQLite Connection and Concurrency Policy
- Each database operation opens its own connection; connections are not shared between worker threads.
- `connect()` enables SQLite foreign keys and returns rows as `sqlite3.Row`.
- Ordinary CRUD/read methods use `_connection()`, which preserves commit/rollback semantics and always closes the connection.
- `create_database()` has separate connection and transaction management for schema initialization and migrations.
- A per-instance `RLock`, `BEGIN IMMEDIATE`, and a 10-second `busy_timeout` coordinate concurrent initialization from threads, independent instances, and processes.
- Migration state is read and updated under the SQLite writer reservation; a migration and its version-ledger row commit together.

## 5. Key Commands
- **Install (Dev):** `pip install -e ".[dev]"` (add `".[translate]"` for translation support).
- **Initialize DB:** `herbal-almanac setup --database /tmp/ayurvedic.db`
- **Dev Scrape:** `herbal-almanac scrape dravya --max-pages 1 --max-plants 5 --database /tmp/ayurvedic.db`
- **Run Tests:** `python -m pytest tests/test_scrapper.py -q`

## 6. Upcoming Roadmap
- Upload release candidate to TestPyPI.
- Expand documented Dosha terminology and query capabilities.
- Implement the remaining normalized Dravyaguna domain tables through additive, reversible migrations.
- Build adapters for additional external herbal sources beyond CCRAS DRAVYA.
- Provide a dedicated public Python search API.