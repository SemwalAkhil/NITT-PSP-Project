# Learnings

## SQLite connection context managers

A SQLite connection used as a context manager controls transactions but does
not close the connection. Nest `with connection:` inside `try/finally` and
close in the `finally` block to preserve commit/rollback behavior while
guaranteeing cleanup on success and failure. `contextlib.closing()` alone is
insufficient when transaction semantics are required.

## SQLite initialization locking

An in-memory lock protects only threads sharing the same Python object.
Independent instances and processes need database-level coordination. Acquire
a writer reservation with `BEGIN IMMEDIATE` before changing schema state, and
keep the migration-version check, migration body, and version-row insert in
the same transaction. Avoid `sqlite3.Connection.executescript()` inside an
active transaction: it implicitly commits pending work. Execute trusted static
DDL statements individually when the surrounding transaction must retain its
writer lock. Configure a bounded busy timeout so competing initializers can
wait for the lock. Use separate operation-scoped connections rather than
sharing a connection across worker threads.

## Versioned additive schema migrations

A migration ledger makes schema upgrades repeatable, but a ledger row must
describe work that actually committed. Apply each migration body and its
version record in the same transaction. Validate legacy natural keys before
backfill and fail with an actionable error when the old data is ambiguous;
do not silently choose one duplicate. When introducing normalized tables in
stages, explicitly document which tables are active application storage and
which are only additive migration targets.

## Claim provenance and subject validation

Foreign keys can establish that a claim and a herb both exist, but they cannot
prove that the source record behind a claim belongs to that herb. Validate
that association in the application before creating a claim-backed name row.
Manual curation should also retain an explicit source/artifact binding so its
origin is auditable.

## Conservative botanical taxonomy migration

Legacy botanical-name text does not prove an accepted taxon, authorship, or
parent-child relationship. Backfill botanical names at `unknown` rank and
family values at `family` rank, preserve the original fields, and avoid
inferring hierarchy or synonym relationships without evidence.

## Python environment

### Creating

```bash
python -m venv .venv
```

### Activating

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\\Scripts\\Activate.ps1
```

If PowerShell blocks activation, use a process-scoped policy change:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.venv\\Scripts\\Activate.ps1
```

### Deactivating

```bash
deactivate
```

### Installing the package and development tools

From the repository root:

```bash
python -m pip install -e ".[dev]"
```

Translation is optional and can be installed separately:

```bash
python -m pip install -e ".[translate]"
```

## Foreign keys in Python SQLite3

SQLite foreign-key enforcement is enabled per connection. Execute:

```python
conn.execute("PRAGMA foreign_keys = ON;")
```

when opening each connection, before starting a transaction.

## Git workflow

Start the repository with an explicit default branch:

```bash
git init -b main
git add .
git commit -m "Initial commit"
git remote add origin <REPOSITORY_URL>
git push -u origin main
```

Before starting a task, synchronize the local branch. If local work was based
on a stale main branch, commit or stash it first, then rebase it on the latest
remote main rather than creating an avoidable merge commit.

## Progress bars in Python

The current scraper uses Rich's `Progress` context manager in `scrape()` to
show the plant currently being processed, completion count, and estimated
time remaining. Presentation stays in the orchestration layer; parser and
database modules remain independent of terminal UI.

## Private helper convention

Names beginning with one underscore are implementation helpers rather than
stable public API. The scraper uses this convention for parsing stages such as
`_discover_plants()`, `_table_attributes()`, and `_scientific_profile()`.
Public entry points include `discover_plants()`, `parse_plant()`, `scrape()`,
`PlantRecord`, and `AyurvedicAlmanac`. Tests may exercise private helpers
when that gives precise coverage, but application code should prefer public
functions.

## Release validation status

The source distribution and wheel build successfully and pass `twine check`.
The clean wheel smoke test verifies library imports, the installed CLI, and a
user-selected database path without the optional translation dependency.
The TestPyPI upload is still pending valid TestPyPI credentials after a
rejected upload, so no public package release has been made.

## Assert keyword

The `assert` keyword in Python is a debugging aid that checks a condition as
an internal sanity check. If the condition is true, execution continues; if
false, Python raises `AssertionError`.
