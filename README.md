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

The CLI can export stored record groups to JSON or CSV after ingestion. Those
exports are optional views of the database and are not an intermediate
scraping stage.

SQLite databases are generated runtime artifacts and are not committed. This
avoids shipping stale schema migrations or incomplete scraped data. Runtime
databases and translation caches should normally be placed outside the
repository. To create a fresh database, run:

```bash
python cli.py setup --database /tmp/ayurvedic.db
python cli.py scrape dravya --max-plants 5 --database /tmp/ayurvedic.db
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
| Automated regression tests | Implemented for core parser and persistence paths |
| Persistent scrape-error report, fuzzy search, and normalized search keys | Implemented |
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
pip install -r requirements.txt
```

Create the database schema:

```bash
python cli.py setup
```

Scrape plant records from the currently supported DRAVYA site:

```bash
python cli.py scrape dravya
```

For a smaller development run, limit the number of pages or plants:

```bash
python cli.py scrape dravya --max-pages 1 --max-plants 5
```

Search the database for herbs, illnesses, or treatments:

```bash
python cli.py herbs tulsi
python cli.py illnesses fever
python cli.py treatments HERB_ID
python cli.py attributes HERB_ID
```

View all stored records, or export a record group as JSON or CSV:

```bash
python cli.py records
python cli.py records herbs
python cli.py records attributes
python cli.py records all --format json --output records.json
python cli.py records treatments --format csv --output treatments.csv
python cli.py records attributes --format csv --output attributes.csv
```

Attributes for one herb can also be exported directly:

```bash
python cli.py attributes HERB_ID --output attributes.json
python cli.py attributes HERB_ID --format csv --output attributes.csv
```

Add individual records manually. Use the IDs printed by the herb and illness
commands when creating a treatment relationship:

```bash
python cli.py herb "Tulsi" --botanical-name "Ocimum tenuiflorum"
python cli.py illness "Cough"
python cli.py treatment HERB_ID ILLNESS_ID
```

Use a different SQLite database by passing `--database` to any command:

```bash
python cli.py setup --database /tmp/ayurvedic-test.db
python cli.py herbs tulsi --database /tmp/ayurvedic-test.db
```

Run `python cli.py --help` or `python cli.py COMMAND --help` to see all
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
