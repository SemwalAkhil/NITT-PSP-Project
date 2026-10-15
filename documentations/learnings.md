# Learnings

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

Install the package and its development tools from the repository root:

```bash
python -m pip install -e ".[dev]"
```

Translation is optional and can be installed separately:

```bash
python -m pip install -e ".[translate]"
```

## Foreign Keys in Python SQLite3

Does not support foreign key by default you need to execute the following before each connection

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

## how automated tests work?

Tests import `herbal_almanac` through the configured `src` path and use saved
HTML strings, fake sessions, temporary SQLite files, and fake translators.
They do not contact DRAVYA or Google. The suite currently covers parser
sections, malformed HTML, retries and failures, database migrations, search,
CLI exports, and translation caching. CI installs `.[dev]` and runs the suite
on Python 3.10 through 3.14.
## orchestration module

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
## What is the page structure of DRAVYA what are we extracting from the page

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