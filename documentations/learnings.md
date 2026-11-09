# Learnings

## SQLite connection context managers

A SQLite connection used as a context manager controls transactions but does not close the connection. Nest `with connection:` inside `try/finally` and close in the `finally` block to preserve commit/rollback behavior while guaranteeing cleanup on success and failure. `contextlib.closing()` alone is insufficient when transaction semantics are required.

## SQLite initialization locking

An in-memory lock protects only threads sharing the same Python object. Independent instances and processes need database-level coordination. Acquire a writer reservation with `BEGIN IMMEDIATE` before changing schema state, and keep the migration-version check, migration body, and version-row insert in the same transaction. Avoid `sqlite3.Connection.executescript()` inside an active transaction: it implicitly commits pending work. Execute trusted static DDL statements individually when the surrounding transaction must retain its writer lock. Configure a bounded busy timeout so competing initializers can wait for the lock. Use separate operation-scoped connections rather than sharing a connection across worker threads.


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
.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use a process-scoped policy change:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.venv\Scripts\Activate.ps1
```

### Deactivating

```bash
deactivate
```

### Install the package and its development tools from the repository root:

```bash
python -m pip install -e ".[dev]"
```

Translation is optional and can be installed separately:

```bash
python -m pip install -e ".[translate]"
```

## Foreign Keys in Python SQLite3

SQLite does not enforce foreign keys by default, so execute the following for
each connection:

```python
conn.execute("PRAGMA foreign_keys = ON;")
```

## Setting up git

```bash

# Run the initialization command. It is recommended to explicitly set your default branch name to main
git init -b main

# 1. Stage all files in the directory
git add .

# 2. Save the snapshot with a message
git commit -m "Initial commit"

git remote add origin <PASTE_REMOTE_REPOSITORY_URL>
git push -u origin main

# 3. Pull task before continuing further on local environment to stay up to date with repository
git pull

# 4. In case you forgot to pull and worked locally
git add .
git commit -m "Temporary commit"
git pull --rebase
git push
# This downloads the latest commit and apply fresh changes from local commit on them avoiding any merge conflicts
```

## Creating progress bar in Python

The current scraper uses Rich's `Progress` context manager in `scrape()` to
show the plant currently being processed, completion count, and estimated time
remaining. Presentation stays in the orchestration layer; the parser and
database operator do not depend on Rich.

## Using retry

The scraper creates a `requests.Session` and mounts an `HTTPAdapter` configured
with `urllib3.util.retry.Retry`.

```python
retry = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=("GET",),
)
```

This retries temporary rate-limit and server failures. Read retries are
disabled because retrying a response that is already connected but slow can
make a scrape appear to hang. It does not replace timeouts or status
validation: `fetch()` uses a `(connect_timeout, read_timeout)` pair and calls
`raise_for_status()` so permanent HTTP errors remain visible.

Using one session also allows the HTTP adapter and User-Agent to be reused for
all directory and plant requests.

## `re.compile` versus `re.search`

`re.compile()` creates a reusable regular-expression pattern. The scraper
compiles the plant URL pattern once:

```python
PLANT_PATH = re.compile(r"/plant/(\d+)(?:/|$)")
```

`re.search()` then checks that pattern against each discovered link. This
extracts the numeric source record ID while avoiding false matches from
unrelated URLs.

The parser uses `re.search()` directly for field labels such as
`Scientific Name`, `Botanical Name`, and `Family`, because those expressions
are used only while inspecting the small set of fields in one page.

## Imports used by the scraper

- `requests`: HTTP sessions and responses.
- `urllib3.util.retry.Retry`: retry policy for temporary HTTP failures.
- `requests.adapters.HTTPAdapter`: attaches the retry policy to the session.
- `bs4.BeautifulSoup`: parses directory and plant HTML.
- `argparse`: exposes the scraper as a command-line program.
- `datetime`: records the UTC retrieval timestamp.
- `urllib.parse.urljoin`: converts relative plant links into absolute URLs.
- `re`: identifies plant URLs and source fields.
- `cleaning`: owns record cleanup and validation.
- `database_operator`: owns SQLite persistence.
- `translation`: optionally enriches names with `deep-translator`.

The modules are imported without performing network requests. Scraping starts
only when `scrape()` or the command-line `main()` function is called.

## `ON CONFLICT` in SQL

The `herbs` table uses `(source, source_record_id)` as the source identity.
`insert_record()` uses SQLite's upsert form:

```sql
ON CONFLICT(source, source_record_id) DO UPDATE SET ...
```

This makes repeated runs idempotent. A plant already stored from the same
source is updated rather than duplicated. The attributes for that plant are
deleted and reinserted so removed source values do not remain stale.

After the upsert, the code queries the row by its natural key instead of
trusting `lastrowid`. `lastrowid` is not a reliable way to identify the row
when the statement takes the conflict-update path.

## How text cleaning works

`clean_text()` applies Unicode NFC normalization and collapses all whitespace
to single spaces. NFC is important because it normalizes equivalent Unicode
representations without removing Devanagari characters or Sanskrit diacritics.

`clean_values()` applies `clean_text()`, removes empty values, and preserves
only the first occurrence of each value. `split_values()` additionally splits
source text on newlines, semicolons, and pipe characters.

`PlantRecord.clean()` cleans the main identity fields, attribute names,
attribute values, and preserved source text. `PlantRecord.validate()` then
checks the source ID, HTTP(S) URL, and required Ayurvedic name before the
record reaches SQLite.

The original extracted table text is retained in `source_values`. Cleaning
therefore improves queryability without losing provenance.

## Translation enrichment

`GoogleNameTranslator` caches requests by `(text, target language)`, waits at
least 0.25 seconds between new requests, and treats an individual translation
failure as missing enrichment. Source vernacular values are never replaced.
The scraper remains usable without translation network access, but translated
attributes may be incomplete.

## Direct ingestion design

The primary ingestion pipeline intentionally avoids an intermediate JSON file:

```text
HTML → PlantRecord → clean → validate → SQLite upsert
```

Raw HTML is still the source artifact, while the typed `PlantRecord` is the
in-memory boundary between parsing, cleaning, validation, and persistence.

JSON and CSV remain available as explicit CLI exports from the stored SQLite
records. They are output formats, not intermediate stages of scraping.

## Dosha normalization

Dosha expressions are normalized by parsing complete Dosha/effect groups from
left to right. This allows mixed expressions such as
`VātavardhakaPittahara` to assign Vata `increase` and Pitta `decrease`
independently. Missing Doshas remain `unspecified`; they are never inferred.
Unknown, incomplete, conflicting, or partially matched expressions are treated
as ambiguous and return `unspecified` for every Dosha. The normalized effects
are persisted in `herb_doshas`, while the original expression remains
available for review and provenance.

## Normalized schema design

The normalized Dravyaguna design separates stable herb identity from source
records and claim-level provenance. Names, parts, properties, Karma, Dosha
effects, taxonomy, and condition relationships can therefore receive evidence
from multiple sources without overwriting source expressions. Migration 1
implements only the core identity/provenance tables; the remaining domain
tables still require an additive migration and compatibility adapter.

## Schema refinement decisions

Source claims belong to source records and are attached to herbs through the
domain rows they support. Requiring a non-null claim reference on each
claim-bearing row keeps provenance explicit while allowing one claim to support
multiple normalized rows. Names and synonyms share one table with a typed
`name_type`. Relationship rows use surrogate IDs and unique indexes over
non-null identity columns because SQLite allows duplicate `NULL` values in
UNIQUE constraints. Manual corrections append claims and supersede earlier
claims instead of overwriting source data.

## Migration 1 core identity and provenance

The first normalized migration is additive and versioned. It creates source,
source-record, claim, legacy-map, and herb-name tables while leaving the
legacy application tables active. Legacy records without an external key retain
an explicit artifact reference rather than receiving an invented identifier.
The migration creates only a justified claim-backed source alias for each
existing herb name; attributes, treatment relationships, and Dosha rows are
preserved for later domain migrations.

## Migration 1 provenance hardening

Legacy source identity is validated before any normalized migration tables are
created. Non-null duplicate `(source, source_record_id)` pairs fail with the
legacy herb IDs; null IDs use explicit artifact references. Backfill keeps the
inserted source-record ID rather than reselecting by a potentially ambiguous
key. SQLite foreign keys provide existence checks, while `_validate_herb_claim`
provides the application-level subject check for herb names. Manual claims are
accepted only with an explicit `legacy_herb_id:<id>` binding.

## Migration 2 botanical taxonomy

Taxonomy backfill must preserve source expressions without inventing a complete
hierarchy. Botanical names are `unknown` rank, family values are `family` rank,
and both become non-preferred source-identification associations backed by
Migration 1 claims. Matching names on different herbs are not merged during
backfill; explicit taxonomic curation is required before concept identity is
shared.

## Harvard-Kyoto Convention

The project uses a compatibility transliteration for English-facing database
fields and search keys. `ascii_text()` first applies the explicit romanization
map, then removes Unicode combining marks and non-ASCII characters. For
example, `Kāsa` becomes `KAsa`, while the original Unicode value remains in
the source-facing fields.

This is a search/display normalization, not a claim that every Sanskrit word
has one universally correct romanization. Regional scripts and original source
values are preserved separately.

## Fuzzy match

Search values are normalized by `search_key()`: text is cleaned, case-folded,
and reduced to letters, numbers, and whitespace. `search_herbs()` and
`search_illnesses()` compare that key with `difflib.SequenceMatcher` and reject
weak matches below the `0.65` score threshold. Exact matches therefore rank
first, while small spelling or transliteration differences remain searchable.
Illnesses also use a canonical key that folds ASCII transliteration variants
and known aliases such as `fever` and `jvara`.

## pyproject.toml

`pyproject.toml` is the packaging and build source of truth. It defines the
`herbal-almanac` distribution, the `src/` package directory, the
`herbal-almanac` console entry point, and Python 3.10 or newer support. Core
dependencies cover scraping, persistence, and CLI operation. The `dev` extra
adds pytest, build, Twine, and translation support; the `translate` extra adds
only `deep-translator`.

The standard release checks are:

```bash
python -m pytest -q
python -m build
python -m twine check dist/*
```

## Automated tests

Tests import `herbal_almanac` through the configured `src` path and use saved
HTML strings, fake sessions, temporary SQLite files, and fake translators.
They do not contact DRAVYA or Google. The suite currently covers parser
sections, malformed HTML, retries and failures, database migrations, search,
CLI exports, and translation caching. CI installs `.[dev]` and runs the suite
on Python 3.10 through 3.14.
## Orchestration modules

`cli.py` is the user-facing orchestration layer. It validates Typer arguments,
selects the database path, calls `scrape()` or database operations, formats
tables and exports, and converts expected failures into exit code 1. It does
not contain HTML parsing or SQL schema logic.

`scrapper.py` orchestrates HTTP discovery, parsing, optional translation,
validation, retries, progress output, and database insertion. `cleaning.py`
and `database_operator.py` remain usable independently as library modules.

## Responses 429, 500, 502, 503, 504

The scraper retries these temporary HTTP statuses through `urllib3.Retry`.
The default policy allows two connection and status retries with exponential
backoff, while read retries remain disabled. Requests use a five-second
connect timeout and a configurable fifteen-second read timeout. A final HTTP
failure remains visible to the per-plant failure report instead of silently
creating an incomplete record.
## DRAVYA page structure and extracted data

The directory page contains links matching `/plant/` followed by a numeric ID.
Each plant page may contain a title, a scientific-profile card, a Vernacular
Names card, and accordion tables. The parser extracts:

- the Ayurvedic name from the title when written as `English - Ayurvedic`;
- scientific and family names from the profile card or table attributes;
- section-qualified table fields such as `Parts Used.Name`;
- language-qualified values such as `Vernacular Names.Hindi`;
- the source URL, numeric record ID, and UTC retrieval timestamp.

Section qualification prevents repeated headers such as `Name` from colliding
across unrelated tables. Therapeutic Usage values are later normalized into
unverified illness and treatment records.
## _function_name convention

Names beginning with one underscore are implementation helpers rather than
stable public API. The scraper uses this convention for parsing stages such as
`_discover_plants()`, `_table_attributes()`, and `_scientific_profile()`.
Public entry points include `discover_plants()`, `parse_plant()`, `scrape()`,
`PlantRecord`, and `AyurvedicAlmanac`. Tests may exercise private helpers when
that gives precise coverage of parser behavior, but application code should
prefer the public functions.

## Release validation status

The source distribution and wheel build successfully and pass `twine check`.
The clean wheel smoke test verifies library imports, the installed CLI, and a
user-selected database path without the optional translation dependency. The
TestPyPI upload is still pending valid TestPyPI credentials after a rejected
upload, so no public package release has been made.

## assert keyword
The `assert` keyword in Python is a debugging aid that tests a condition as a internal sanity check. If the condition evaluates to `True`, the program carries on running normally. If the condition evaluates to `False`, Python immediately crashes the program and raises an AssertionError

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

## Web interface as a separate application layer

Keep the browser interface separate from the scraper and database
implementation. FastAPI routes should orchestrate existing domain/read methods;
Jinja2 should render the results. Add only narrowly scoped database read
helpers when the existing API cannot provide an efficient page model. Keep
runtime database selection explicit and test routes against temporary SQLite
files. A first read-only milestone avoids mixing request/response handling
with long-running scraping or write operations.
