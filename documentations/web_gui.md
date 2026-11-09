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
  links, and flexible attributes, plus the six most recently inserted herb
  records.
- **Herb explorer (`/herbs`):** search using the existing ranked
  `search_herbs()` behavior, with 12 results displayed per page.
- **Herb detail (`/herbs/{herb_id}`):** botanical identity and provenance,
  flexible source attributes, normalized Dosha effects with source expressions,
  and linked illness terms.

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

The routes call the existing database operator. The only new database read
helpers are `dashboard_summary()`, which performs aggregate counts and
returns a small recent-record sample, and `get_herb()`, which retrieves one
herb by ID. Each helper uses the database operator's managed connection
lifecycle.

The web interface is intentionally read-only in this milestone. It does not
start scraping or translation work, write manual curation, or expose migration
controls. Scraping remains available through the existing CLI.

The herb search currently reuses `search_herbs()`, which ranks the available
herb rows in Python before the route slices the requested page. This preserves
the CLI's exact/fuzzy matching behavior; if datasets grow substantially, a
dedicated indexed paginated search can be introduced without changing the
templates.

Templates and CSS are package data under `templates/` and `static/`, so
they are included in built wheels. The page does not require a JavaScript
framework or external font/image requests.

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
