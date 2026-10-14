# Learnings

## Virual Environment

### Creating

```powershell
python -m venv .venv
```

### Activating

```powershell
.venv\Scripts\Activate.ps1
```

### Bypass powershell_Execution_Policy if executing script not allowed

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process; .venv\Scripts\Activate.ps1
```

### Exit

```powershell
exit
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

The first scraper used Rich's `Progress` context manager to show progress
while discovering links and fetching tables. The current scraper intentionally
does not use a progress bar yet. It focuses on a reusable pipeline and a
small command-line interface first. A progress display can be added later
without putting presentation logic inside the parser or database layer.

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

## Direct ingestion design

The current pipeline intentionally avoids an intermediate JSON file:

```text
HTML → PlantRecord → clean → validate → SQLite upsert
```

Raw HTML is still the source artifact, while the typed `PlantRecord` is the
in-memory boundary between parsing, cleaning, validation, and persistence.