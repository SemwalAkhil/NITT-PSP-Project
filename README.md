# Herbal Almanac

Herbal Almanac is a Python research library and command-line application for
exploring Ayurvedic herbs, illness references, and herb–treatment
relationships. The current ingestion adapter supports the CCRAS DRAVYA portal.
SQLite is the persistence layer; Typer and Rich provide the CLI.

> **Research disclaimer:** This project is not medical advice. Scraped
> therapeutic associations and machine translations may be unverified and must
> not be used to diagnose, treat, or prevent illness.

## Current implementation

The DRAVYA pipeline discovers plant records, fetches pages with timeouts and
retries, parses semantic tables and the Vernacular Names card, cleans and
validates `PlantRecord` objects, optionally enriches names through machine
translation, and writes records to SQLite.

The active application schema contains:

| Table | Purpose |
|---|---|
| `herbs` | Herb identity, source identity, names, botanical/family text, source URL, and retrieval timestamp |
| `illness` | Condition display names and normalized search keys |
| `treatment` | Herb–illness links, distinguished as scraped or manually curated |
| `herb_attributes` | Flexible section-qualified fields, vernacular names, source wording, and translation metadata |
| `herb_doshas` | Normalized Vata/Pitta/Kapha effects with their source expressions |

Re-scraping refreshes source-derived attributes and scraped treatment/Dosha
rows while preserving manual treatment links.

### Additive schema migrations

Two versioned migrations currently add normalized structures without
replacing the legacy application tables:

- **Migration 1 — identity and provenance:** `schema_migrations`, `sources`,
  `source_records`, `source_claims`, `legacy_herb_map`, and `herb_names`.
- **Migration 2 — botanical taxonomy:** `taxa`, `taxon_relationships`,
  and `herb_taxa`.

The migration backfills preserve source context and avoid guessing ambiguous
legacy identities or taxonomic hierarchy. The remaining normalized domain
schema in [`documentations/database_schema.md`](documentations/database_schema.md)
is a design proposal, not a claim that the full target schema is implemented.
See [`documentations/database_operator.md`](documentations/database_operator.md)
for connection lifecycle, transaction, and migration behavior.

## Package API

The installable package is named `herbal_almanac`. It exports the main
`PlantRecord` and `AyurvedicAlmanac` types:

```python
from herbal_almanac import AyurvedicAlmanac, PlantRecord
from herbal_almanac.cleaning import clean_text

print(clean_text("  Tulsi  "))
database = AyurvedicAlmanac("/tmp/ayurvedic.db")
```

The `herbal-almanac` console command is registered through `pyproject.toml`.
JSON and CSV exports are views of stored database records; they are not an
intermediate stage in the scraper pipeline.

## Installation

Python 3.10 or later is required. Install the package from the repository root:

- **Core CLI and Library (Default):**
  ```bash
  python -m pip install -e .
  ```
  *Provides the `herbal-almanac` CLI, SQLite database operator, scraper, DDL migrations, and demo generator (`scripts/make_demo_db.py`). No web dependencies required.*

- **Web Interface Extra (`[web]`):**
  ```bash
  python -m pip install -e ".[web]"
  ```
  *Required for running the local FastAPI web server (`uvicorn herbal_almanac.web_app:app`) and browsing the web GUI.*

- **Translation Extra (`[translate]`):**
  ```bash
  python -m pip install -e ".[translate]"
  ```
  *Optional. Required only when running scraper with the `--translate` flag.*

- **Development Extra (`[dev]`):**
  ```bash
  python -m pip install -e ".[dev]"
  ```
  *For running tests (`pytest`), packaging checks (`build`), and static analysis.*

## Demo in 5 minutes

Evaluate the full Herbal Almanac system—including the Typer CLI, FastAPI Web GUI, Stage B provenance tracking, and Stage C semantic Dravyaguna features—in under 5 minutes.

### 1. Install with Web Dependencies

```bash
python -m pip install -e ".[web]"
```

### 2. Build the Demo Database

Choose either the instant offline demo database (recommended for quick evaluation without network calls) or a live scrape:

**Option A: Instant Offline Demo Database (Recommended)**
```bash
python scripts/make_demo_db.py
```
*Builds `data/demo.db` offline from `sample.html`, creates 2 manual illnesses and treatment links, applies Stage C Migration 3, seeds the 136-concept catalog, and runs semantic backfill.*

**Option B: Live Scrape (Requires Internet Access to CCRAS DRAVYA)**
```bash
herbal-almanac setup --database data/demo.db
herbal-almanac scrape dravya --max-plants 25 --database data/demo.db
herbal-almanac upgrade-stage-c --database data/demo.db --yes
```

### 3. Launch the Web Interface

Point the application to the demo database and start the server:

- **Linux / macOS:**
  ```bash
  HERBAL_ALMANAC_DATABASE=data/demo.db uvicorn herbal_almanac.web_app:app --reload
  ```
- **Windows (PowerShell):**
  ```powershell
  $env:HERBAL_ALMANAC_DATABASE="data/demo.db"; uvicorn herbal_almanac.web_app:app --reload
  ```
- **Windows (Command Prompt):**
  ```cmd
  set HERBAL_ALMANAC_DATABASE=data/demo.db && uvicorn herbal_almanac.web_app:app --reload
  ```

### 4. Pages to Open in Your Browser

Open `http://127.0.0.1:8000` and explore:

1. **User Guide & Ayurveda Primer (`/guide`):** Introductory guide and conceptual reference explaining what the site is, 3 numbered navigation flows, a 19-term glossary of classical Ayurvedic concepts (Rasa, Guna, Virya, Vipaka, Prabhava, Doshas) and architectural mechanisms (Claims, Concepts, Provenance, Virya Reconciliation), data sources (CCRAS DRAVYA, 15 languages), and research safety boundaries.
2. **Dashboard (`/`):** Summary cards displaying counts of herbs, illnesses, treatment relationships, and attributes alongside recent herbs, top frequent conditions, and dual search actions. Includes a prominent "New here? Read the guide" callout.
3. **Herb Catalog (`/herbs`):** Searchable, paginated directory of herbs with text filtering and pagination.
4. **Semantic Herb Detail (`/herbs/1`):** Complete Stage C presentation showcasing:
   - **Classical Dravyaguna Properties:** Rasa (taste), Guna (qualities), Virya (potency), Vipaka (post-digestive effect), Prabhava (specific action), and Karma (actions), with links to the Guide glossary.
   - **Plant Part Associations:** Officinal plant parts (leaves, seeds, roots).
   - **Sanskrit Lexical References:** Multi-script terms in Devanagari script and IAST Latin transliteration.
   - **Directional Dosha Effects:** Normalized Vata/Pitta/Kapha decrease and increase assertions.
   - **Linked Conditions:** Illnesses linking to their dedicated condition detail pages.
   - **Virya Reconciliation Summary Pill:** Multi-source concordance indicator.
5. **Illness Explorer (`/illnesses`):** Therapeutic index of conditions with:
   - **Multilingual Language Selector:** Switch between 15 Indian languages (English, हिन्दी, संस्कृतम्, বাংলা, தமிழ், తెలుగు, etc.) with native script buttons and URL persistence (`?language=hi`).
   - **Multilingual Search:** Query conditions by English common name ("fever", "cough", "piles"), classical transliteration ("jvara", "kasa", "arsha"), or vernacular scripts ("बुखार", "खांसी", "बवासीर").
   - **Clear Heading Hierarchy:** English name displayed as main heading, selected language script beneath it with `<span lang="...">`, and original scraped transliteration preserved in small monospace code tags.
   - **Disclaimers:** CCRAS DRAVYA medical research disclaimer and a machine-translation notice on non-English views, linking to the Guide limits.
6. **Illness Detail (`/illnesses/1`):** Detailed condition profile listing all associated herbs with:
   - Preserved language selection across links.
   - Distinct badges for scraped vs. manually curated herb-treatment relationships.
   - Mandatory medical disclaimer and machine translation notices.
7. **Virya Reconciliation Dashboard (`/stage-c/reconciliation/1`):** Detailed 4-tier audit report classifying concordance across sources, candidate divergence, and intra-claim ambiguity, with direct links to the Guide glossary.
8. **REST JSON Endpoints:**
   - Herb Semantic Profile: `GET /api/stage-c/herbs/1/profile`
   - Illness Search: `GET /api/illnesses?q=`
   - Condition Herbs: `GET /api/illnesses/1/herbs`

### Windows Troubleshooting (Application Control / Smart App Control)

If Windows Application Control or Smart App Control blocks direct execution of `.exe` launcher stubs in Python virtual environments (such as `pip.exe`, `herbal-almanac.exe`, or `uvicorn.exe` with error `WinError 4551`), invoke them directly via Python module syntax:

- Instead of `pip install ...` &rarr; `python -m pip install ...`
- Instead of `herbal-almanac ...` &rarr; `python -m herbal_almanac ...`
- Instead of `uvicorn ...` &rarr; `python -m uvicorn herbal_almanac.web_app:app --reload`

### 5. CLI Commands to Show

Demonstrate the command-line interface against the demo database:

```bash
# 1. Inspect Stage C schema capability, migration ledger, and table counts
herbal-almanac stage-c-status --database data/demo.db

# 2. Search and list herbs
herbal-almanac herbs --database data/demo.db

# 3. List illnesses (shows both scraped and manually curated illnesses)
herbal-almanac illnesses --database data/demo.db

# 4. View treatment links for Herb 1 (distinguishes scraped from manual treatments)
herbal-almanac treatments 1 --database data/demo.db

# 5. Inspect extracted section attributes
herbal-almanac attributes 1 --database data/demo.db

# 6. Export the full database to a single JSON archive
herbal-almanac records all --format json --output demo_records.json --database data/demo.db
```

---

## Quick start

Create a database and scrape a small number of records:

```bash
herbal-almanac setup --database /tmp/ayurvedic.db
herbal-almanac scrape dravya --max-pages 1 --max-plants 5 --database /tmp/ayurvedic.db
```

The scraper requires network access to CCRAS DRAVYA. Existing databases are
migrated in place; choose a new path for a clean rebuild.

Search records and inspect relationships:

```bash
herbal-almanac herbs tulsi --database /tmp/ayurvedic.db
herbal-almanac illnesses fever --database /tmp/ayurvedic.db
herbal-almanac treatments HERB_ID --database /tmp/ayurvedic.db
herbal-almanac attributes HERB_ID --database /tmp/ayurvedic.db
```

Browse/export records:

```bash
herbal-almanac records
herbal-almanac records herbs
herbal-almanac records attributes
herbal-almanac records all --format json --output records.json
herbal-almanac records treatments --format csv --output treatments.csv
herbal-almanac attributes HERB_ID --format csv --output attributes.csv
```

Add manual records and treatment relationships:

```bash
herbal-almanac herb "Tulsi" --botanical-name "Ocimum tenuiflorum"
herbal-almanac illness "Cough"
herbal-almanac treatment HERB_ID ILLNESS_ID
```

Use `herbal-almanac --help` and `herbal-almanac COMMAND --help` for the
complete command and option reference. See [`documentations/cli.md`](documentations/cli.md).

## Translation and multilingual values

Translation is disabled by default. With the optional dependency installed,
pass `--translate` to add machine-generated `Translated Names.<Language>`
attributes. Source regional scripts and source wording are retained separately.
Translated content is marked unverified; see
[`documentations/translation.md`](documentations/translation.md).

### Multilingual Illness Glossary and Language Selector

To bridge classical Ayurvedic nomenclature and modern vernacular understanding, Herbal Almanac bundles an in-memory multilingual illness glossary (`src/herbal_almanac/data/illness_glossary.csv`, 227 conditions, 16 language columns) supported by a resolution engine (`src/herbal_almanac/illness_glossary.py`).

1. **15 Supported Indian Languages:**
   - Quick selector buttons: **English**, **हिन्दी** (Hindi), **संस्कृतम्** (Sanskrit).
   - Additional regional scripts: **অসমীয়া** (Assamese), **বাংলা** (Bengali), **ગુજરાતી** (Gujarati), **ಕನ್ನಡ** (Kannada), **മലയാളം** (Malayalam), **मराठी** (Marathi), **नेपाली** (Nepali), **ଓଡ଼ିଆ** (Odia), **ਪੰਜਾਬੀ** (Punjabi), **தமிழ்** (Tamil), **తెలుగు** (Telugu), and **اردو** (Urdu).
   - Selection persists via URL query parameter (`?language=hi`) across condition and herb links.

2. **Fault-Tolerant Resolution:**
   - Classical scraped transliterations often include case variations, diacritics, Sanskrit visargas (`-H`, `-h`), phonetic alternatives (`w`/`v`, `sh`/`s`, `ch`/`cch`), and slash compounds (e.g. `ArtavadoSaH/ArtavaduSTiH/rajodoSaH`).
   - The resolver (`resolve_illness()`) handles all of these variations transparently and maps compound terms to both full and individual concepts without modifying stored database records.

3. **Multilingual and Alias Search:**
   - Searches across all 15 language columns as well as English clinical synonyms (e.g. searching "bawasir" or "piles" matches "Arsha / Piles").
   - **Cross-Explorer Redirection:** When a user searches for an illness term (e.g. "cough" or "बुखार") in the Herb Explorer and no herb matches, the GUI automatically redirects (HTTP 303) to `/illnesses?q=...`.

4. **Extending the Glossary:**
   - To add new conditions or regional synonyms, edit `src/herbal_almanac/data/illness_glossary.csv` following the 16-column UTF-8 format (`Original_Term, English, Assamese, Bengali, Gujarati, Hindi, Kannada, Malayalam, Marathi, Nepali, Odia, Punjabi, Sanskrit, Tamil, Telugu, Urdu`). The in-memory resolver reloads on application startup.

5. **AI Attribution & Scholarly Precedence:**
   - Translations in the CSV were generated with AI assistance via **Gemini Deep Research**. They are machine-generated and **not clinically verified**.
   - **Scholarly Precedence:** Curated Stage C canonical concepts (the 24 `IND_*` indications in `concept_catalog.py`) take strict precedence over CSV translations for English, Hindi, and Sanskrit on conflict. All discrepancies are audited transparently via `scripts/illness_coverage.py --conflicts`.
   - Non-English pages display an explicit disclaimer banner: *"Translations are machine-generated (Gemini) and not clinically verified."* alongside standard CCRAS research disclaimers.

6. **Database Coverage Audit:**
   - Check database illness resolution coverage at any time:
     ```bash
     python scripts/illness_coverage.py --database data/demo.db
     ```
   - See [`documentations/illness_glossary.md`](documentations/illness_glossary.md) for full architecture and resolution specifications.

## Local web interface

Herbal Almanac includes an optional read-only browser interface built with
FastAPI, Uvicorn, and Jinja2. It reuses the existing SQLite database operator
and provides an overview dashboard, searchable herb explorer, and herb detail
pages.

Install and launch it:

```bash
python -m pip install -e ".[web]"
uvicorn herbal_almanac.web_app:app --reload
```

Open `http://127.0.0.1:8000`. The web interface uses the same per-user
database path as the CLI. Set `HERBAL_ALMANAC_DATABASE` to use another SQLite
file. See [`documentations/web_gui.md`](documentations/web_gui.md) for setup,
routes, architecture, and tests.

The first GUI milestone is read-only: scraping, translation, and manual
curation remain CLI workflows.

To verify the stylesheet separately, open
`http://127.0.0.1:8000/static/styles.css`. It should return CSS text with
HTTP 200. See the troubleshooting section in
[`documentations/web_gui.md`](documentations/web_gui.md) if the page renders
without styling.

## Architecture

```text
CCRAS DRAVYA
    |
    v
discover -> fetch -> parse -> clean/validate -> optional translation
                                         |
                                         v
                                  SQLite transaction
                                  |- herbs + attributes
                                  |- illness/treatment links
                                  |- normalized Dosha effects
                                  |- additive Migrations 1 & 2
                                         |
                                         +-----------------------+
                                         |                       |
                                         v                       v
                              Typer CLI / JSON / CSV     FastAPI Web Interface
```

See [`documentations/scrapper.md`](documentations/scrapper.md) for scraping
and recovery behavior, [`documentations/cleaning.md`](documentations/cleaning.md)
for record cleanup, and [`documentations/database_schema.md`](documentations/database_schema.md)
for the current/proposed normalized model.

## Tests and CI

Tests are offline: use `sample.html`, `data.txt`, mocked HTTP responses,
fake translators, and temporary SQLite files. Do not call the live source or
translation service from tests.

Run the required scraper regression and then the full suite:

```bash
python -m pytest tests/test_scrapper.py -q
python -m pytest -q
```

The GitHub Actions workflow runs both commands across Python 3.10–3.14.

## Repository and data notes

- `sample.html` is a saved source-page fixture for parser development.
- `data.txt` is a small Sanskrit terminology/reference sample.
- SQLite databases and translation caches are runtime artifacts and are not
  committed; the default database is stored in the platform's user data
  directory.
- The project code is MIT-licensed. CCRAS source material, terminology
  references, and scraped data may have separate copyright, attribution, or
  terms-of-use requirements. Verify redistribution rights independently.


## Roadmap and AI coding-agent handoff

Before implementing planned features, read:

- [SDLC plan](documentations/plan.md)
- [Antigravity handoff — next actions and working protocol](documentations/antigravity_handoff.md)
- [Roadmap addendum — evidence, safety, multilingual access, and staged gates](documentations/roadmap_addendum.md)
- [Clinical, safety, evidence, and multilingual data requirements](documentations/clinical_data_requirements.md)

These documents distinguish current implementation from future requirements. Do not implement later-stage medical-history or symptom-matching features before their prerequisite gates pass.
