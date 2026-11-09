# GitHub Copilot Instructions — Herbal Almanac

## Project overview

Herbal Almanac (`herbal_almanac`) is a Python 3.10–3.14 library and
Typer/Rich CLI (`herbal-almanac`). It currently ingests Ayurvedic plant data
from the CCRAS DRAVYA portal, cleans and validates records, optionally
translates vernacular names, and stores herbs, attributes, illnesses,
treatments, and normalized Dosha effects in SQLite.

The database also has two additive, versioned schema migrations:
Migration 1 adds source identity and claim provenance; Migration 2 adds
botanical taxonomy. These tables do not replace the active legacy application
read/write model yet. Treat the remaining normalized Dravyaguna schema as a
proposal until its own migration and tests are implemented.

## Core architecture and separation of concerns

Follow the pipeline boundary:

`discover → fetch → parse → clean/validate → optional translate → SQLite transaction`

1. **Scraper layer:** `src/herbal_almanac/scrapper.py` handles URL discovery,
   retries/timeouts, and HTML parsing. Do not put raw SQL in the scraper.
2. **Cleaning and validation:** `cleaning.py` owns `PlantRecord` validation,
   deterministic Unicode cleanup, value splitting, transliteration, and
   conservative Dosha-expression normalization. Preserve source wording.
3. **Database layer:** `database_operator.py` owns SQLite connections,
   legacy compatibility, schema migrations, transactional persistence,
   provenance foundations, search, and read/export operations.
4. **Translation layer:** `translation.py` uses `deep-translator` only when
   `--translate` is explicitly enabled. Store generated values as
   `Translated Names.<Language>` and mark them machine-generated/unverified.
5. **CLI layer:** `cli.py` exposes setup, scraping, manual record operations,
   search/inspection, and JSON/CSV exports. Do not treat exports as an
   intermediate scraper stage.

## Strict coding rules

- **No committed databases:** SQLite files and translation caches are runtime
  artifacts. Use the user data directory or temporary paths; never commit
  generated databases.
- **Preserve manual links:** refreshing scraped Therapeutic Usage relationships
  must not delete manually curated treatment links.
- **Preserve provenance:** keep source expressions and original fields next to
  normalized interpretations. Do not manufacture source IDs or claim evidence.
- **Conservative taxonomy:** do not infer accepted status, authorship, synonym
  merges, or parent/child hierarchy from legacy botanical-name/family text.
- **Offline tests only:** tests must use local fixtures (`sample.html`,
  `data.txt`), mocked HTTP responses, fake translators, and temporary SQLite
  databases. Never call CCRAS DRAVYA or Google Translate from tests.
- **Python compatibility:** maintain compatibility with Python 3.10–3.14.

## Web GUI rules

- The optional web interface lives in `src/herbal_almanac/web_app.py` and uses FastAPI, Uvicorn, and Jinja2 templates.
- Keep routes thin and reuse `AyurvedicAlmanac` read methods. Add focused database read helpers rather than embedding SQL in templates or duplicating database logic in routes.
- The initial GUI milestone is read-only. Do not expose scraping, translation, or manual-write operations through HTTP routes until background-job and safety behavior is designed.
- Use `create_app(database_path)` for isolated tests with temporary SQLite files. Keep templates and static assets packaged with the distribution.

## SQLite and migration rules

- Open an independent connection per operation; do not share a connection
  between worker threads.
- Every connection must enable `PRAGMA foreign_keys = ON`.
- Ordinary CRUD/read methods must use the operation-scoped private
  `_connection()` context manager so transactions commit/roll back and
  connections close on both success and failure.
- Keep schema initialization separate from ordinary operation connection
  handling.
- Coordinate concurrent initialization with the existing instance lock,
  `BEGIN IMMEDIATE`, and bounded `busy_timeout`.
- Do not use `sqlite3.Connection.executescript()` inside an active migration
  transaction because it implicitly commits pending work.
- Validate ambiguous legacy natural keys before backfill; fail with an
  actionable error rather than selecting an arbitrary row.
- A migration body and its `schema_migrations` row must commit in the same
  transaction. Failed migrations must roll back and remain retryable.
- Schema changes must migrate existing databases in place and preserve manual
  treatment links and source/provenance information.

## Required work cycle

For every requested change:

1. **Select and scope:** identify the task, owning module, tests, and docs.
2. **Implement:** follow existing conventions and avoid unrelated refactors.
3. **Sync context and docs:** update `context.md` and relevant files under
   `documentations/`. Add a learning entry for new documentation headings or
   implementation concepts. Keep active functionality distinct from proposal.
4. **Verify:** run the narrowest relevant tests. If any Python file under
   `src/herbal_almanac/` or `tests/` changes, also run:

   ```bash
   python -m pytest tests/test_scrapper.py -q
   ```

   For a complete check, run `python -m pytest -q`.
5. **Commit together:** include code, tests, `context.md`, and relevant docs in
   one focused commit after verification.

Keep cycles focused. Do not overwrite unrelated user changes.
