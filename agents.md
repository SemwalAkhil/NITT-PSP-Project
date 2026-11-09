# AI Agent Operating Guide (`agents.md`)

## Environment setup

Before running project commands or tests, install the package and development
dependencies from the repository root:

```bash
python -m pip install -e ".[dev]"
```

## Agent work cycle

For each requested change:

1. **Select and scope:** identify the concrete task, owning module, tests, and
   documentation.
2. **Implement:** follow existing conventions and preserve unrelated changes.
3. **Synchronize documentation:** update `context.md` and every relevant
   module document under `documentations/`. Keep implementation status
   distinct from design proposals.
4. **Verify:** run the narrowest relevant checks. If Python source or tests
   changed, also run the mandatory scraper regression.
5. **Commit together:** include code, tests, `context.md`, and relevant
   documentation in the same focused commit.

Do not combine unrelated refactors or overwrite user changes.

## Verification protocol

After modifying any Python file under `src/herbal_almanac/` or `tests/`,
the mandatory regression command is:

```bash
python -m pytest tests/test_scrapper.py -q
```

For a complete verification pass, also run:

```bash
python -m pytest -q
```

The GitHub Actions workflow runs the scraper regression and full suite across
Python 3.10, 3.11, 3.12, 3.13, and 3.14.

## Offline testing rules

- **No live network calls:** tests must not contact CCRAS DRAVYA or Google
  Translate. Use `sample.html`, `data.txt`, mocked HTTP responses, or a fake
  translator.
- **Temporary SQLite databases:** use pytest `tmp_path` or an explicit
  temporary `--database` path. Do not mutate the user's default database.
- **Deterministic assertions:** prefer checking records, transaction state,
  schema versions, and observable outputs over implementation details unless
  a private helper is the precise subject of the test.

## Documentation rules

- Every task updates `context.md` and relevant Markdown files under
  `documentations/`.
- Add a matching learning note in `documentations/learnings.md` when a new
  documentation heading or implementation concept is introduced.
- Every new Python module requires a companion Markdown document explaining
  purpose, inputs, outputs, main flow, and verification.
- Keep the README, context, module docs, and roadmap consistent about what is
  implemented, additive-only, or planned.

## Module boundaries

- **Web GUI:** keep `web_app.py` as a thin FastAPI/Jinja2 presentation layer. Reuse `AyurvedicAlmanac` methods; do not duplicate SQL, scraping, cleaning, or translation logic in routes. The initial web interface is read-only. Test routes with temporary SQLite databases.

- **Scraper sources:** source-specific selectors stay in scraper modules.
  Scrapers output validated `PlantRecord` objects; cleaning and persistence
  remain source-agnostic.
- **Database schema:** changes must migrate existing SQLite files in place.
  Preserve manual treatment relationships and source/provenance data.
- **Migrations:** validate ambiguous legacy identities before backfill;
  migration body and version-ledger row must commit together.
- **Connections:** use independent operation-scoped SQLite connections;
  do not share a connection between worker threads.
- **Normalized schema:** Migrations 1 and 2 are implemented additively.
  Do not describe proposal tables as active application storage until their
  migrations and tests exist.
