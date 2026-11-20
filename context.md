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
  - `illness_glossary.py` — multilingual machine-generated glossary loader (15 languages), fault-tolerant resolution, and catalog-precedence engine.
  - `herb_view.py` — herb detail presentation view-model layer: property deduplication, 3-dosha synthesis, attribute classification, family cleaning, and date formatting.
  - `data/illness_glossary.csv` — packaged UTF-8 multilingual illness glossary (227 rows, 16 columns).
  - `web_app.py` — optional FastAPI/Jinja2 read-only browser interface.
  - `templates/` and `static/` — server-rendered pages and local stylesheet.
- `tests/test_scrapper.py` — offline scraper, cleaning, translation, CLI, and legacy database regression tests.
- `tests/test_illness_glossary.py` — CSV integrity, phonetic tolerance, catalog precedence, fallback, and multilingual search tests.
- `tests/test_packaging_and_guards.py` — packaging integrity (including CSV data assets) and hermetic skip-guard checks.
- `tests/test_provenance_integration.py` — operational provenance tests (source records, claim extraction, supersession lineage, claim-to-subject validation, and idempotency).
- `tests/test_database_connections.py` — connection isolation, commit/rollback, closure, and foreign-key tests.
- `tests/test_database_initialization.py` — initialization concurrency, migration idempotence, rollback/retry, and closure tests.
- `tests/test_web_app.py` — dashboard, herb search, detail pages, and HTTP error behavior using a temporary database.
- `tests/test_demo_db.py` — offline demo database synthesis, manual curations, Stage C upgrade, and CLI invocation tests.
- `tests/smoke_installed_package.py` — clean installed-package and CLI smoke test.
- `scripts/make_demo_db.py` — offline demo SQLite database generator from `sample.html`.
- `scripts/illness_coverage.py` — database illness resolution auditor and catalog conflict reporter.
- `.github/workflows/copilot-instructions.md` and `agents.md` — contributor/agent workflow and verification guardrails.
- `documentations/` — module docs, project report (`project_report.md`), demo database guide (`make_demo_db.md`), multilingual glossary guide (`illness_glossary.md`), schema proposals, learning notes, and roadmap.
- `sample.html` and `data.txt` — local parser/terminology fixtures.

## 3. Runtime data model
The legacy application tables remain the active read/write contract:
- `herbs` — herb identity, source identity, original/transliterated names, botanical/family text, URL, and retrieval time.
- `illness` — condition names and search/canonical keys, with machine-generation and verification metadata.
- `treatment` — herb–illness relationships; `source` distinguishes scraped links from manual links.
- `herb_attributes` — section-qualified source values, vernacular names, source text/language, and translation metadata.
- `herb_doshas` — normalized Vata/Pitta/Kapha effects tied to their original Doshakarma expression.

Vernacular names are stored as `Vernacular Names.<Language>` attributes. Optional translations are added only when `--translate` is requested and are marked machine-generated/unverified. Therapeutic Usage values remain source attributes; the supported condition field also creates unverified illness rows and scraped treatment links. Re-scraping refreshes scraped relationships while preserving manual treatment links.

## 4. Versioned schema additions and operational provenance
The database operator applies additive migrations after legacy schema compatibility initialization:
- Migration 1 (`core_identity_and_provenance`) creates `schema_migrations`, `sources`, `source_records`, `source_claims`, `legacy_herb_map`, and `herb_names`.
- Migration 2 (`normalized_botanical_taxonomy`) creates `taxa`, `taxon_relationships`, and `herb_taxa`.
- Milestone C.1 (`semantic_dravyaguna`) delivers the validated Stage C schema architecture, Migration 3 module (`migration_0003_semantic_dravyaguna.py`), complete DDL with partial unique indexes for nullable composite uniqueness, 44 integrity triggers enforcing source-claim assertion immutability and label verification, and test suite (`tests/test_stage_c_migration.py`, 23 tests) in `stage_c_review/` and `tests/`. Milestone C.1 has formally achieved independent review sign-off with verified write-lock acquisition & contention (`test_21`), sequential stale-version rejection (`test_22`), and synchronized multi-threaded lock serialization (`test_23`). Migration 3 remains additive and unapplied to the production database (maintained at schema version 2) until production execution is authorized. Stage C.2 is fully completed, hardened, and formally promoted into the production package `src/herbal_almanac/` across all eight work packages (WP-0 through WP-7): (1) WP-0 Architecture & Transition Policy ADR (`ADR_STAGE_C2_ARCHITECTURE.md`, Revision 9); (2) WP-1 Canonical Concept Catalog (`concept_catalog.py`, 136 concepts, 649 multilingual labels); (3) WP-2 Schema Capability Gating & Migration Ledger Validation (`schema_capability_gate.py`); (4) WP-3 Claim Lifecycle, Interpretation Review & Section-Level Omission Engine (`claim_lifecycle.py`); (5) WP-4 Stage B -> Stage C Provenance Backfill & Semantic Ingestion Engine (`backfill_engine.py`); (6) WP-5 Repository API & Presentation Services (`repository_api.py`); (7) WP-6 Web Application Integration & GUI Routing (`web_app.py`, `templates/`, version-aware FastAPI presentation with capability banner on v2, full semantic cards and Virya reconciliation on v3); and (8) WP-7 Production Package Promotion & CLI Commands (`upgrade-stage-c`, `stage-c-status` in `cli.py`, `upgrade_to_stage_c()` and `run_stage_c_backfill()` in `AyurvedicAlmanac`, and official test suites mirrored into `tests/`). Tests are strictly hermetic: session-scoped `hermetic_v2_db_path` fixture in `tests/conftest.py` synthesizes a Schema Version 2 database from `sample.html` for backfill and CLI tests, while local database invariance checks skip cleanly in CI when uncommitted `data/inspection.db` is absent. Package data in `pyproject.toml` explicitly bundles `migrations/*.sql` (`stage_c_ddl_and_triggers.sql`, `virya_reconciliation.sql`) alongside templates and styles, ensuring complete wheel installations outside developer editable workspaces. GitHub Actions workflow (`.github/workflows/tests.yml`) enforces both the 3.10-3.14 non-short-circuiting unit test matrix (`fail-fast: false`) and an independent `package-smoke` wheel build and multi-tier installation job (verifying both core-only installation and `[web]` extra), with `setuptools>=68` and `wheel` declared in `dev` extras for PEP 517 non-isolated builds. Staging directory `stage_c_review/` is retired as a code location and preserved strictly for architectural documentation (`ADR_STAGE_C2_ARCHITECTURE.md`, `README.md`, `WP1_CATALOG_COVERAGE_REPORT.md`); duplicate code and tests were de-duplicated into `src/herbal_almanac/` and `tests/` with clean relative imports. Full test suite (218 passed locally, 215 passed / 3 skipped in clean CI) and mandatory scraper regression (57 tests) pass with 100% success. Packaging asset inclusion and AST skip guards are enforced by `tests/test_packaging_and_guards.py`. Production database `data/inspection.db` remains strictly at schema version 2 ([1, 2]). The Stage C milestone gate is fully audited and documented in `documentations/stage_c_gate_checklist.md`. Stage D multi-source ingestion feasibility, epistemic deduplication algorithms, and evidence schema design are documented as proposals in `documentations/stage_d_feasibility_and_schema.md`. In addition, an in-memory multilingual illness glossary (`src/herbal_almanac/data/illness_glossary.csv`, 227 conditions, 16 columns) and resolution engine (`src/herbal_almanac/illness_glossary.py`) provide localized condition names across 15 Indian languages with fault-tolerant Sanskrit normalization, catalog precedence, cross-script search, database coverage auditing (`scripts/illness_coverage.py`), and a dedicated introductory User Guide and Ayurvedic Reference page (`/guide`) with a 19-term Dravyaguna glossary. Lexical ruleset fix (P0-1): removed erroneous mapping of privative ('guna', 'aguru') to GUNA_GURU so that expressions like 'Laghu/ Aguru' map solely to GUNA_LAGHU; existing databases require a rebuild (`herbal-almanac setup --database <path>`, `scrape`, `upgrade-stage-c` or `python scripts/make_demo_db.py`) to refresh stored properties.

With Stage B operational provenance integration, the live ingestion pipeline actively populates and synchronizes these provenance tables:
- `insert_record()` creates/reuses `sources` and `source_records`, generates traceable `source_claims` for names, taxonomy, section attributes, and Dosha expressions, and links `herb_names` and `herb_taxa` via validated claims within the same atomic transaction.
- Re-scraping is idempotent: unchanged claims are reused, while source updates mark old claims as `superseded` (`verification_status = 'superseded'`) and set `supersedes_claim_id`, ensuring an immutable audit trail without data loss.
- Manual curation via `add_herb()` registers `legacy_herb_map` and dedicated manual `source_records` (`raw_artifact_ref = legacy_herb_id:<herb_id>`), preserving manual links and relationships across scraping runs.
- `AyurvedicAlmanac` exposes public inspection APIs: `herb_claims(herb_id)` and `herb_source_record(herb_id)`.

Migration preflight rejects duplicate legacy source identities instead of guessing. Each migration body and its version-ledger row are committed transactionally. Migration 2 records botanical names at unknown rank and family values at family rank without inferring accepted status or taxonomy hierarchy. Remaining normalized Dravyaguna domain tables described in `documentations/database_schema.md` are proposals, not implemented features.

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
- Stage B (operational provenance integration) and Stage C (semantic Dravyaguna architecture & multilingual catalog) are complete.
- Next priority: Stage D (multi-source scientific evidence, statutory pharmacopoeia adapters, and independent corroboration).
- Add further external source adapters only after licensing and feasibility review.
- Expand supported query capabilities and provide a dedicated public Python search API.

## 8. Optional local web GUI

The FastAPI/Uvicorn/Jinja2 interface is a read-only layer over
`AyurvedicAlmanac`. Its stylesheet is served at `/static/styles.css` and is
included in package data. It provides the dashboard at `/` (counts, recent herbs, top conditions, callout to guide),
introductory guide and conceptual reference at `/guide` (what the site is, 3 numbered navigation flows, 19-term Dravyaguna glossary, data sources, and safety limits), searchable herbs at
`/herbs`, detail pages at `/herbs/{herb_id}`, searchable illness directory at
`/illnesses`, condition detail at `/illnesses/{illness_id}`, and REST endpoints under
`/api/`. The herb detail view (`herb_detail_semantic.html`) restructures botanical presentation: a single 6-column normalized properties table (`Rasa | Guna | Virya | Vipaka | Prabhava | Karma`) with unique chips, claim counts (`×N`), and collapsed source claim details; a clean 3-row Dosha table (`Vata | Pitta | Kapha`) with explicit "Not recorded" fallback; and structured plant characteristic cards (Vernacular Names, Parts Used, Preparations, Dose, Therapeutic Usages, Etymology & Pharmacopoeia) replacing raw 200+ attribute dumps. Transliterated illness names are formatted into readable title case via
`format_readable_illness` (`readable_illness` filter) without mutating stored database records.
The interface features an interactive 15-language multilingual selector (English, Hindi, Sanskrit, and 12 regional Indic scripts) with native script buttons, URL parameter persistence (`?language=<code>`), cross-script search (matching English names, synonyms, and Devanagari/regional scripts), automatic query redirection from `/herbs` to `/illnesses` on condition queries, and disclaimer notices for CCRAS research and machine translations.
Install with `python -m pip install -e ".[web]"` and run
`uvicorn herbal_almanac.web_app:app --reload`. The default database path is
shared with the CLI; `HERBAL_ALMANAC_DATABASE` overrides it. Scraping and
writes remain CLI-only in this first milestone. See
`documentations/web_gui.md` and `documentations/illness_glossary.md`.
