# Herbal Almanac

---

## Goal

To create a library to know about various illness and their treatments using herbs in ayurveda and vice versa

---

## Current implementation

The current MVP supports the CCRAS DRAVYA source. It discovers plant URLs,
downloads pages with retries and timeouts, parses semantic tables and the
Vernacular Names card, cleans and validates `PlantRecord` objects, and writes
them directly to SQLite.

Each vernacular language is stored as an attribute such as
`Vernacular Names.Hindi`. The source title's Ayurvedic/Sanskrit name becomes
the primary herb name when present; English vernacular values remain available
in `herb_attributes`. During scraping, `deep-translator`/Google Translator adds
corresponding English and major Indian-language values as
`Translated Names.<Language>` attributes when `--translate` is explicitly
enabled. English-facing text uses a Harvard-Kyoto-style ASCII transliteration,
while source regional scripts are preserved. Therapeutic Usage values are also
normalized into illness and treatment relationships; manual treatment links
survive later scrapes.

The importable code is provided by the `herbal_almanac` package, including the
public `PlantRecord` and `AyurvedicAlmanac` classes. The configured
`herbal-almanac` command provides the Typer CLI, which can export stored record
groups to JSON or CSV after ingestion. Those exports are optional views of the
database and are not an intermediate scraping stage.

Library consumers can use the cleaning and database APIs without starting the
CLI or making network requests:

```python
from herbal_almanac.cleaning import PlantRecord, clean_text
from herbal_almanac.database_operator import AyurvedicAlmanac

print(clean_text("  Tulsi  "))
database = AyurvedicAlmanac("/tmp/ayurvedic.db")
```

SQLite databases are generated runtime artifacts and are not committed. This
avoids shipping stale schema migrations or incomplete scraped data. Runtime
databases and translation caches are stored in the user data directory by
default, outside both the repository and the installed package. To create a
fresh database, run:

```bash
pip install -e .
herbal-almanac setup --database /tmp/ayurvedic.db
herbal-almanac scrape dravya --max-plants 5 --database /tmp/ayurvedic.db
```

The scrape command requires network access to the CCRAS DRAVYA source. Use
`--max-plants` or `--max-pages` for a small reproducible development run.
Existing local databases are migrated in place, so use a new path when
rebuilding from scratch.

Translation is disabled by default. Add `--translate` only when machine
translation is desired.

`data.txt` is a small Sanskrit terminology/reference sample. `sample.html` is
a saved source-page HTML fixture for parser development; neither is required
for a network scrape.

This project is for research and software evaluation, not medical advice.
Translations and scraped therapeutic associations are machine-generated or
unverified and must not be used to diagnose, treat, or prevent illness.
CCRAS data remains subject to the source site's terms and attribution
requirements; verify permission before redistributing scraped content.

## Architecture

```text
CCRAS DRAVYA
    │
    ▼
discover → fetch → parse → clean/validate → translate
                                      │
                                      ▼
                              SQLite transaction
                              ├─ herbs + provenance
                              ├─ herb_attributes
                              └─ illness/treatment links
```

The CCRAS DRAVYA website is the source of scraped plant data. Translated
attributes are machine-generated and marked unverified; source values are
preserved separately. See [`documentations/scrapper.md`](documentations/scrapper.md)
for the ingestion and recovery behavior.

## Current status

| Area | Status |
|---|---|
| DRAVYA discovery, parsing, and retrying | Implemented |
| Cleaning, validation, provenance, and SQLite upserts | Implemented |
| Vernacular and optional translated-name attributes | Implemented |
| Illness/treatment links from Therapeutic Usage | Implemented |
| Typer CLI search, inspection, manual inserts, and exports | Implemented |
| `src/` package layout, wheel/sdist build, and console entry point | Implemented |
| Automated regression tests and clean-install smoke test | Implemented |
| Persistent scrape-error report, fuzzy search, and normalized search keys | Implemented |
| TestPyPI release candidate upload | Pending valid TestPyPI credentials |
| Dosha normalization and additional external source adapters | Planned |

---

## Design

### 1. Scraper

Evaluate sites to understand their structures, parse source records, clean
them, validate them, and insert them directly into SQLite.

### 2. Database

Initial tables:

1. Herbs
2. Illnesses
3. Treatment (Join between herbs and illnesses)

The database operator owns schema creation, transactions, and persistence.
Cleaning and normalization are kept in a separate module so source parsing
does not become coupled to SQL.

### 3. Cleaning

`cleaning.py` provides deterministic Unicode cleanup, ASCII normalization for
English-facing values, value splitting, and `PlantRecord` validation.

### 4. Multilingual access

* Fetch data from databases and present it in multiple languages
<br>
* Query in a way to be able to search incomplete or misspelled queries

The current CLI stores multilingual vernacular and translated-name attributes.
Search uses normalized keys and ranked fuzzy matching; a dedicated public
Python API remains planned.

### 5. Look for further optimizations

---

## Execution

1. Python 3.10+ for the backend
2. SQLite for persistence
3. Typer and Rich for the CLI
4. Requests, BeautifulSoup, and urllib3 for ingestion
5. deep-translator for optional name enrichment

The supported/tested Python range is 3.10 through 3.14. Direct dependencies
are pinned in `requirements.txt`; CI runs the regression suite across that
range.

The project code is licensed under the MIT License. The CCRAS website,
terminology samples, and scraped data may have separate copyright,
attribution, or terms-of-use requirements; the MIT license does not grant
rights to redistribute third-party source data.

## Documentation map

- [`documentations/cli.md`](documentations/cli.md): commands, options, and
  export formats.
- [`documentations/scrapper.md`](documentations/scrapper.md): source discovery,
  parsing, translation, and ingestion flow.
- [`documentations/cleaning.md`](documentations/cleaning.md): normalization and
  `PlantRecord` behavior.
- [`documentations/database_operator.md`](documentations/database_operator.md):
  schema, migrations, and transactional persistence.
- [`documentations/translation.md`](documentations/translation.md): optional
  Google Translator enrichment.
- [`documentations/plan.md`](documentations/plan.md): implemented baseline and
  future roadmap.
- [`documentations/learnings.md`](documentations/learnings.md): implementation
  notes and operational patterns.

---

## How to Use

The project is accessed through the Typer command-line interface. Install the
Python dependencies first:

```bash
pip install -e .
```

For development and release checks, install `pip install -e ".[dev]"`.
Translation support is optional: install `pip install -e ".[translate]"` only
when using `--translate`.

Create the database schema:

```bash
herbal-almanac setup
```

Scrape plant records from the currently supported DRAVYA site:

```bash
herbal-almanac scrape dravya
```

For a smaller development run, limit the number of pages or plants:

```bash
herbal-almanac scrape dravya --max-pages 1 --max-plants 5
```

Search the database for herbs, illnesses, or treatments:

```bash
herbal-almanac herbs tulsi
herbal-almanac illnesses fever
herbal-almanac treatments HERB_ID
herbal-almanac attributes HERB_ID
```

View all stored records, or export a record group as JSON or CSV:

```bash
herbal-almanac records
herbal-almanac records herbs
herbal-almanac records attributes
herbal-almanac records all --format json --output records.json
herbal-almanac records treatments --format csv --output treatments.csv
herbal-almanac records attributes --format csv --output attributes.csv
```

Attributes for one herb can also be exported directly:

```bash
herbal-almanac attributes HERB_ID --output attributes.json
herbal-almanac attributes HERB_ID --format csv --output attributes.csv
```

Add individual records manually. Use the IDs printed by the herb and illness
commands when creating a treatment relationship:

```bash
herbal-almanac herb "Tulsi" --botanical-name "Ocimum tenuiflorum"
herbal-almanac illness "Cough"
herbal-almanac treatment HERB_ID ILLNESS_ID
```

Use a different SQLite database by passing `--database` to any command:

```bash
herbal-almanac setup --database /tmp/ayurvedic-test.db
herbal-almanac herbs tulsi --database /tmp/ayurvedic-test.db
```

Run `herbal-almanac --help` or `herbal-almanac COMMAND --help` to see all
available commands and options.

---

## Testing

Run the focused regression suite:

```bash
python -m pytest tests/test_scrapper.py -q
```

The tests cover section-aware table parsing, malformed HTML, pagination,
timeouts and HTTP errors, partial scrape recovery, provenance persistence,
fuzzy search, treatment-link refresh, Unicode cleanup, and translation
enrichment with a fake translator. Tests use fixtures and do not contact the
live network.
