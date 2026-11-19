# Web GUI

## Purpose

The optional local web interface lets a user browse an existing Herbal
Almanac SQLite database in a browser. It is a read-only presentation layer
built with FastAPI, Uvicorn, and Jinja2. It reuses
`AyurvedicAlmanac`; it does not duplicate scraping, parsing, cleaning, or
persistence logic.

## Installation and startup

Install the optional web dependencies from the repository root:

```bash
python -m pip install -e ".[web]"
```

Start the development server:

```bash
uvicorn herbal_almanac.web_app:app --reload
```

Open `http://127.0.0.1:8000`. Stop the server with Ctrl+C.

The web application uses the same platform default database path as the CLI.
To select a different database, set `HERBAL_ALMANAC_DATABASE` before
starting the server:

Windows PowerShell:

```powershell
$env:HERBAL_ALMANAC_DATABASE = "C:\\path\\to\\AyurvedicDB.db"
uvicorn herbal_almanac.web_app:app --reload
```

Linux/macOS:

```bash
export HERBAL_ALMANAC_DATABASE=/path/to/AyurvedicDB.db
uvicorn herbal_almanac.web_app:app --reload
```

The application factory `create_app(database_path)` accepts an explicit path
for tests and embedding. The module-level `app` uses the environment variable
or the package's normal per-user database location.

## First milestone screens

- **Overview (`/`):** lightweight counts for herbs, illness terms, treatment
  links, and flexible attributes, the six most recently inserted herb
  records, and frequent conditions ranked by linked herb count with direct
  links to condition details. Includes dual search inputs for herbs and conditions,
  and a prominent "New here? Read the guide" callout linking to `/guide`.
- **User guide & reference (`/guide`):** an introductory primer and domain reference for first-time visitors, completely decoupled from database access (renders identically with, without, or on empty databases). Features:
  - Table of contents with keyboard-focusable in-page anchor links (`#what-is-this`, `#how-to-use`, `#glossary`, `#data-sources`, `#limits`).
  - Plain-English explanations of the platform and 3 numbered workflow guides with direct links to `/herbs`, `/illnesses`, and `/stage-c/reconciliation/{id}`.
  - A comprehensive 19-term glossary (`<dl>`) defining classical Dravyaguna concepts (Rasa, Guna, Virya, Vipaka, Prabhava, Doshas, Karma, Part used, Kalpana, Indications), botanical nomenclature, and architectural constructs (Claims, Concepts, Provenance, Virya Reconciliation, Epistemic status labels, Scraped transliteration vs. resolved names).
  - Attribution for CCRAS DRAVYA, the curated concept catalog (136 concepts), Gemini Deep Research translations, and the 15 supported Indian regional languages rendered with native scripts.
  - Ethical research boundaries and medical disclaimers, with cross-links from illness disclaimers and reconciliation views.
- **Herb explorer (`/herbs`):** search using the existing ranked
  `search_herbs()` behavior, with 12 results displayed per page and query
  preservation across pagination controls. If an entered query yields no matching
  herbs but matches an illness term or synonym in the multilingual glossary, the
  route automatically redirects (HTTP 303) to `/illnesses?q=...`.
- **Herb detail (`/herbs/{herb_id}`):** version-aware botanical profile.
  - *On Schema Version 2 databases:* displays an informative capability degradation banner (`"Stage C Semantic Dravyaguna features require Schema Version 3"`), while rendering the full legacy botanical profile, source attributes, Dosha effects, and illness links.
  - *On Schema Version 3 databases:* dynamically unlocks normalized Stage C Dravyaguna property cards (Rasa, Guna, Virya, Vipaka, Prabhava, Karma), officinal plant parts (Prayojyāṅga), multilingual labels via `?language=<code>`, canonical Sanskrit script (Devanagari) and IAST transliterations, preparations, clinical indications, and a Virya consensus indicator pill linking to the reconciliation dashboard.
- **Virya reconciliation dashboard (`/stage-c/reconciliation/{herb_id}`):** an interactive 4-tier audit dashboard displaying classical source agreement, candidate divergence (unreviewed / reviewed), and verified contradictions across botanical peers. Returns HTTP 501 on Schema Version 2.
- **Illness explorer (`/illnesses`):** searchable, paginated directory of illness terms featuring:
  - **15-Language Selector:** One-click language switching between English, हिन्दी, संस्कृतम्, and 12 regional Indic scripts (Assamese, Bengali, Gujarati, Kannada, Malayalam, Marathi, Nepali, Odia, Punjabi, Tamil, Telugu, Urdu) with accessible `aria-label` and `<span lang="...">` attributes. Selected language persists across pagination and entity links via `?language=<code>`.
  - **Multilingual Search:** Matches queries across English names, clinical synonyms (e.g., "piles", "fever"), and all 15 native Indic scripts (e.g., "खांसी", "बुखार", "बवासीर") using `database_operator.py` and `illness_glossary.py`.
  - **Structured Heading Hierarchy:** Displays the readable English name as primary heading, the selected language term beneath it, and the original scraped transliteration in small code tags (`Original term · <code>...</code>`).
  - **Ethical Disclaimers:** Preserves the mandatory CCRAS DRAVYA medical research disclaimer on every page, and renders an explicit translation notice on non-English views: *"Translations are machine-generated (Gemini) and not clinically verified."*
- **Illness detail (`/illnesses/{illness_id}`):** condition profile listing all associated herbs with links to `/herbs/{herb_id}`, distinguishing between scraped and manually curated links, with preserved language selection across navigation.
- **Display-only illness name formatting (`readable_illness` Jinja filter):** transliterated illness names from source databases often contain internal Harvard-Kyoto/ITRANS capitals (e.g. `KAsa`, `AgnimAndya`, `khAlityam/khalati`). The `format_readable_illness` presentation helper and Jinja filter formats these into readable title case (`Kasa`, `Agnimandya`, `Khalityam/Khalati`) in presentation templates without modifying underlying SQLite records.

## Illness & Stage C REST API Endpoints

The web application exposes read-only REST API endpoints:

- `GET /api/illnesses?q=`: returns ranked list of condition objects matching the query:
  ```json
  [
    {
      "id": 1,
      "english_name": "Cough",
      "original_name": "KAsa",
      "label": "खांसी",
      "language": "hi",
      "hindi": "खांसी",
      "sanskrit": "कासः",
      "herb_count": 5,
      "origin": "catalog",
      "verification": "curated",
      "kind": "disease"
    }
  ]
  ```
- `GET /api/illnesses/{illness_id}/herbs`: returns list of associated herb objects enriched with multilingual metadata and link source (`scraped` vs `manual`). Returns HTTP 404 for unknown illness IDs.
- `GET /api/stage-c/status`: reports schema version, migration ledger sequence, and Stage C feature availability.
- `GET /api/stage-c/herbs/{herb_id}/profile`: returns localized Dravyaguna semantic profile JSON with optional `language` (`en`, `hi`, `sa`), `include_disputed`, and `include_provisional` query parameters. Returns HTTP 501 on Schema Version 2, HTTP 500 on corrupted ledgers.
- `GET /api/stage-c/herbs/{herb_id}/reconciliation`: returns 4-tier Virya reconciliation report JSON with summary counts and pairwise divergence records. Returns HTTP 501 on Schema Version 2, HTTP 500 on corrupted ledgers.

Unknown herb IDs return HTTP 404. Search input is capped at 100 characters.
The UI does not infer missing botanical data or reinterpret source claims.
Machine-generated and unverified values retain their status labels where
available.

## Architecture and boundaries

```text
Browser
   |
   v
FastAPI routes (web_app.py)
   |
   v
AyurvedicAlmanac read methods
   |
   v
SQLite database
   |
   v
Jinja2 templates + local CSS
```

The routes call the existing database operator. The database read helpers
include `dashboard_summary()`, `get_herb()`, `get_illness()`, `illness_summaries()`,
and `herbs_for_illness()`. Each helper uses the database operator's managed connection
lifecycle with parameterized SQL queries.

The web interface is intentionally read-only in this milestone. It does not
start scraping or translation work, write manual curation, or expose migration
controls. Scraping remains available through the existing CLI.

The herb search currently reuses `search_herbs()`, which ranks the available
herb rows in Python before the route slices the requested page. This preserves
the CLI's exact/fuzzy matching behavior; if datasets grow substantially, a
dedicated indexed paginated search can be introduced without changing the
templates.

Templates and CSS are package data under `templates/` and `static/`, so
they are included in built wheels. The stylesheet is served at
`/static/styles.css`; the application checks that the CSS file exists during
startup, and the HTML uses a versioned stylesheet URL to reduce stale browser
cache issues.

### Troubleshooting a page without styling

1. Open `http://127.0.0.1:8000/static/styles.css` directly. It should display
   CSS text, not an HTML 404/error page.
2. In browser Developer Tools → Network, reload the page and inspect the
   `styles.css` request. It should return HTTP 200 with a `text/css`
   content type.
3. From the current repository checkout, reinstall the optional web extra and
   restart Uvicorn:

   ```bash
   python -m pip install -e ".[web]"
   uvicorn herbal_almanac.web_app:app --reload
   ```

4. Hard-refresh the browser (Ctrl+Shift+R). If the direct CSS URL still fails,
   check that the server is running the updated checkout and that
   `src/herbal_almanac/static/styles.css` exists in that checkout.

The page does not require a JavaScript framework or external font/image
requests.

## Verification

Install development dependencies (which include the web test client):

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/test_web_app.py -q
python -m pytest tests/test_scrapper.py -q
python -m pytest -q
```

The tests use a temporary SQLite database and FastAPI's in-process test client.
They do not access the network or the user's default database.
