# Web Application (`web_app.py`)

## 1. Purpose

`src/herbal_almanac/web_app.py` implements the local web interface and JSON API for Herbal Almanac.

It uses FastAPI for routing, Jinja2 for HTML rendering, and the existing database and repository modules for data retrieval. Users can browse herbs and illnesses, view herb details, explore localized illness terminology, and inspect Stage C semantic information when the database supports it.

The application is designed as a read-oriented exploration layer. It does not implement the ingestion, cleaning, or claim-adjudication workflows.

## 2. Where It Fits in the Architecture

The web application sits above the data-access and presentation modules.

```text
                 Browser / API Client
                         |
                         v
                    web_app.py
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
  database_operator  repository_api  illness_glossary
          |              |              |
          v              v              v
       SQLite       Stage C data    CSV + concept catalog
                         |
                         v
                     herb_view
                         |
                         v
                  Jinja2 templates
```

The actual request path depends on the route:

- Legacy herb and illness data are retrieved through `database_operator.py`.
- Normalized Stage C herb data are retrieved through `repository_api.py`.
- Illness labels and multilingual searches use `illness_glossary.py`.
- Herb-detail presentation structures are prepared by `herb_view.py`.
- HTML pages are rendered from files under `templates/`.
- Static assets are served from `static/`.

## 3. Imports and Dependencies

### Standard-library imports

| Import | Use |
|---|---|
| `math` | Calculates pagination counts |
| `os` | Reads the `HERBAL_ALMANAC_DATABASE` environment variable |
| `Path` | Resolves database, template, and static paths |
| `sqlite3` | Opens SQLite connections for Stage C queries |
| `Any` | Route return and context type annotations |

### FastAPI and Starlette imports

| Import | Use |
|---|---|
| `FastAPI` | Creates the application |
| `HTTPException` | Returns HTTP errors for missing resources and unavailable features |
| `Query` | Defines and validates query parameters |
| `Request` | Supplies request context to HTML templates |
| `Response` | Imported in the current module |
| `HTMLResponse` | Declares HTML route responses |
| `StaticFiles` | Mounts the static asset directory |
| `Jinja2Templates` | Loads and renders HTML templates |

### Internal imports

| Imported symbol | Origin | Responsibility |
|---|---|---|
| `AyurvedicAlmanac` | `database_operator.py` | Legacy database access |
| `default_database_path` | `database_operator.py` | Supplies the default database location |
| `MigrationError` | `schema_capability_gate.py` | Identifies invalid migration-ledger state |
| `validate_schema_migration_ledger` | `schema_capability_gate.py` | Determines the database schema version |
| `herb_dravyaguna_profile` | `repository_api.py` | Retrieves normalized herb semantic data |
| `reconcile_herb_virya` | `repository_api.py` | Builds the Virya reconciliation report |
| `ORDERED_LANGUAGE_CODES` | `illness_glossary.py` | Provides language selector ordering |
| `SUPPORTED_LANGUAGES` | `illness_glossary.py` | Provides language metadata |
| `resolve_illness` | `illness_glossary.py` | Resolves illness labels |
| `search_glossary` | `illness_glossary.py` | Searches multilingual illness terminology |
| `clean_family` | `herb_view.py` | Cleans botanical family display text |
| `format_retrieved` | `herb_view.py` | Formats retrieval dates |
| `dedupe_properties` | `herb_view.py` | Deduplicates property records for display |
| `group_properties_by_domain` | `herb_view.py` | Groups properties into Dravyaguna domains |
| `virya_consensus` | `herb_view.py` | Summarizes Virya agreement |
| `dedupe_dosha_effects` | `herb_view.py` | Builds the Dosha presentation structure |
| `group_attributes` | `herb_view.py` | Groups legacy herb attributes |

`FeatureUnavailableError` is also imported from `schema_capability_gate.py`, but the current route implementation uses `get_database_capability()` and HTTP exceptions for its explicit capability handling.

## 4. Module-Level Paths and Configuration

### `PACKAGE_DIR`

The directory containing the `herbal_almanac` package, resolved from `__file__`.

### `TEMPLATE_DIR`

Points to the package's `templates/` directory.

### `STATIC_DIR`

Points to the package's `static/` directory.

### `STYLESHEET_PATH`

Points to `static/styles.css`. The application factory checks that this file exists before returning the application.

### `PAGE_SIZE`

Set to `12`. Herb and illness listing routes use this value to calculate pagination.

## 5. Helper Functions

### 5.1 `clean_language_param(language: str | None) -> str`

Validates a language query parameter against `SUPPORTED_LANGUAGES`.

**Logic:**

1. Returns `en` when the parameter is missing.
2. Trims whitespace and converts the value to lowercase.
3. Returns the normalized code if supported.
4. Falls back to `en` for an unsupported code.

This prevents arbitrary language values from being passed into template and glossary lookups.

### 5.2 `format_readable_illness(name: str | None) -> str`

Formats transliterated illness terms into readable title-style text without changing the stored database value.

It:

- Returns an empty string for missing or blank input.
- Splits slash-separated alternatives.
- Splits each alternative into words.
- Applies Python's `capitalize()` to each word.
- Rejoins the alternatives with `/`.

Examples:

```python
format_readable_illness("KAsa")
# "Kasa"

format_readable_illness("AgnimAndya")
# "Agnimandya"

format_readable_illness("khAlityam/khalati")
# "Khalityam/Khalati"
```

This is display formatting, not a transliteration engine.

### 5.3 `get_database_capability(conn: sqlite3.Connection) -> dict[str, Any]`

Checks the migration ledger using `validate_schema_migration_ledger()`.

It returns a dictionary containing:

- `version`
- `stage_c_available`
- `is_corrupt_ledger`
- `error`

For a valid version-3 ledger, `stage_c_available` is true. A valid earlier schema version is treated as not having Stage C available.

If migration-ledger validation raises `MigrationError`, or another exception occurs, the function reports the ledger as corrupt/unavailable and includes the error message.

The function does not apply migrations or inspect every Stage C table and constraint.

## 6. Application Factory

### `create_app(database_path: str | Path | None = None) -> FastAPI`

Creates and configures the FastAPI application.

#### Database path selection

The database path is chosen in this order:

1. Use the explicit `database_path` argument, if provided.
2. Otherwise, read `HERBAL_ALMANAC_DATABASE` from the environment.
3. If the environment variable is absent, use `default_database_path()`.

The selected path is stored as:

```python
application.state.database_path
```

#### Application configuration

The factory:

1. Creates the FastAPI application with its title, description, and version.
2. Stores the selected database path.
3. Checks that the packaged stylesheet exists.
4. Mounts the static directory at `/static`.
5. Creates a `Jinja2Templates` instance.
6. Registers template filters and globals.
7. Defines the route handlers.
8. Returns the configured application.

#### Jinja2 filters and globals

Registered filters:

| Name | Function |
|---|---|
| `readable_illness` | `format_readable_illness` |
| `clean_family` | `clean_family` |
| `format_retrieved` | `format_retrieved` |
| `resolve_illness` | `resolve_illness` |

Registered globals:

- `resolve_illness`
- `supported_languages`
- `ordered_language_codes`

The resolver is registered as both a filter and a global so templates can use it in different expression contexts.

#### Internal database helper

The factory defines `get_database()`, which returns an `AyurvedicAlmanac` instance using the configured application database path.

This keeps route handlers tied to the application instance's selected database rather than a hard-coded file.

## 7. HTML Routes

### 7.1 `GET /` — Dashboard

Handler: `dashboard()`

- Validates the requested language.
- Calls `dashboard_summary()` through `AyurvedicAlmanac`.
- Renders `dashboard.html`.

The template context includes the summary, active navigation page, selected language, and language selector metadata.

### 7.2 `GET /guide` — User Guide

Handler: `guide()`

Builds example data for the guide page.

When the configured database file exists, it:

- Opens a database connection through `AyurvedicAlmanac._connection()`.
- Retrieves up to three herb examples.
- Retrieves up to three illness examples ordered by the number of associated treatment records.
- Uses the first example herb as the guide's example herb ID.

If the example-data retrieval fails, the handler falls back to empty example collections.

It renders `guide.html`.

### 7.3 `GET /herbs` — Herb Listing and Search

Handler: `herb_list()`

Query parameters:

- `q`: search text, maximum length 100
- `page`: page number, minimum 1
- `language`: display language

The handler:

1. Validates the language.
2. Searches herbs through `database.search_herbs()`.
3. If no herb matches a non-empty query, checks the illness glossary and database illness search.
4. Redirects to `/illnesses` with HTTP 303 when the query appears to be an illness search.
5. Calculates the total pages using `PAGE_SIZE`.
6. Selects the requested page's records.
7. Renders `herbs.html`.

The redirect allows the global/herb search interface to route illness queries to the illness listing page.

### 7.4 `GET /herbs/{herb_id}` — Herb Detail

Handler: `herb_detail()`

Query parameters:

- `language`
- `include_disputed`
- `include_provisional`

This is the main integration point between the legacy database, normalized Stage C repository API, and herb view-model layer.

#### Processing sequence

1. Validate the requested language.
2. Retrieve the herb using `database.get_herb()`.
3. Return HTTP 404 if the herb does not exist.
4. Open a SQLite connection and enable foreign keys.
5. Call `get_database_capability()` to check Stage C availability.
6. If Stage C is available:
   - Select the semantic profile language. Only `en`, `hi`, and `sa` are passed through; other supported UI languages fall back to `en` for the semantic profile.
   - Call `herb_dravyaguna_profile()`.
   - Call `reconcile_herb_virya()`.
7. Retrieve legacy attributes and Dosha records.
8. Prepare the presentation structures.
9. Retrieve treatment details.
10. Render `herb_detail_semantic.html`.
11. Close the SQLite connection in the `finally` block.

#### Presentation processing

When a semantic profile is available:

- `dedupe_properties()` prepares deduplicated property records.
- `group_properties_by_domain()` creates domain-specific collections.
- `virya_consensus()` creates the Virya summary.
- `dedupe_dosha_effects()` prepares the normalized Dosha view.

When the semantic profile is unavailable:

- Property collections are empty.
- Domain collections are initialized with empty standard domains.
- Virya summary is `None`.
- The Dosha presentation helper receives legacy Dosha data.

In both cases, `group_attributes()` processes the legacy herb attributes.

The template receives the herb, legacy records, semantic profile, reconciliation report, grouped structures, and language metadata.

**Important distinction:** The detail route's fallback path allows legacy herb information to remain available when Stage C is unavailable. It does not mean the normalized Stage C features have been enabled.

### 7.5 `GET /stage-c/reconciliation/{herb_id}` — Virya Reconciliation Page

Handler: `virya_reconciliation_dashboard()`

This route is explicitly Stage C-dependent.

Processing:

1. Retrieve the herb; return 404 if missing.
2. Open a SQLite connection and enable foreign keys.
3. Inspect the migration ledger.
4. Return HTTP 500 if the ledger is corrupt.
5. Return HTTP 501 if Stage C is unavailable.
6. Generate the report using `reconcile_herb_virya()`.
7. Render `virya_reconciliation.html`.
8. Close the connection.

The route presents reconciliation information. It does not adjudicate or modify the underlying claims.

### 7.6 `GET /illnesses` — Illness Listing and Search

Handler: `illness_list()`

Query parameters:

- `q`: search text, maximum length 100
- `page`: page number, minimum 1
- `language`: display language

The handler:

1. Validates the language.
2. Retrieves matching illness summaries using `database.illness_summaries()`.
3. Calculates pagination.
4. Selects the requested page.
5. Renders `illnesses.html`.

### 7.7 `GET /illnesses/{illness_id}` — Illness Detail

Handler: `illness_detail()`

The handler:

1. Validates the language.
2. Retrieves the illness using `database.get_illness()`.
3. Returns HTTP 404 if the illness does not exist.
4. Retrieves associated herbs using `database.herbs_for_illness()`.
5. Renders `illness_detail.html`.

### 7.6 `GET /herbs/add` and `POST /herbs/add` — Add Herb Record
Form interface to insert new plant records (`english_name`, `botanical_name`, `family`, `source`, `source_record_id`, `source_url`). Enforces required fields, HTTP(S) protocol for URLs, and CSRF origin verification (`verify_same_origin`).

### 7.7 `GET /illnesses/add` and `POST /illnesses/add` — Add Illness / Indication
Form interface to insert illness terms. Traps unique constraint violations and renders user-friendly inline error alerts.

### 7.8 `GET /treatments/add` and `POST /treatments/add` — Link Herb to Illness
Form interface providing searchable dropdown menus to link an existing plant record to an illness indication.

### 7.9 `GET /treatments` — Treatments Directory
Paginated directory displaying plant-condition treatment associations with query filtering (`?q=...`).

### 7.10 `GET /attributes` and `GET /herbs/{herb_id}/attributes` — Source Attributes
Comprehensive source attribute explorer displaying field names, values, source citations, language tags, and verification statuses across all herbs or for a single plant.

### 7.11 `GET /records` — Records & Data Hub
Tabbed data hub summarizing records by group (`herbs`, `illnesses`, `treatments`, `attributes`, `doshas`) with live database metrics and export actions.

### 7.12 `GET /stage-c/status` and `POST /stage-c/upgrade` — Stage C Architecture & Status
Visual status dashboard showing schema migration ledger and one-click transaction upgrade to Stage C. Explains why web scraping is executed via the CLI.

### 7.13 CSV and JSON Exports
- `GET /export/herbs.csv` and `GET /export/herbs.json`: Filtered or complete herb records.
- `GET /export/illnesses.csv` and `GET /export/illnesses.json`: Complete condition records.
- `GET /export/treatments.csv` and `GET /export/treatments.json`: Plant-illness treatment links.
- `GET /herbs/{herb_id}/export.csv` and `GET /herbs/{herb_id}/export.json`: Per-herb records including attributes, treatments, and dosha effects.

Exports include formula injection protection (cells starting with `=`, `+`, `-`, or `@` prepended with `'`) and UTF-8 with BOM (`\ufeff`) encoding.

### 7.14 Plant Imagery & Accessibility Architecture
- **Plant Imagery:** Dynamic CCRAS DRAVYA URL generation (`https://dravya.ccras.org.in/resources/views/admin/required/upload/<plant_id>.jpg`) with lazy loading and local SVG fallback (`static/placeholder-herb.svg`).
- **Accessibility (WCAG 2.1 AA):** Landmarks (`role="banner"`, `role="main"`, `role="contentinfo"`), skip link (`.skip-link`), accessibility drawer with text scaling (`sm`, `md`, `lg`, `xl`), contrast mode (normal/high), font switcher (default, clean sans, OpenDyslexic), and dark theme with `localStorage` persistence.

## 8. JSON API Routes

### 8.1 `GET /api/illnesses`

Handler: `api_illness_list()`

Query parameters:

- `q`
- `language`

The route retrieves illness summaries and enriches each result with glossary data:

- English primary label
- English synonyms
- Hindi label
- Sanskrit label
- Selected-language label
- Selected language code
- `kind`
- `matched`
- `origin`
- `verification`

The original database summary fields are retained using dictionary expansion.

### 8.2 `GET /api/illnesses/{illness_id}/herbs`

Handler: `api_illness_herbs()`

Returns herbs associated with the requested illness, enriched with the resolved illness's terminology metadata.

It:

1. Retrieves the illness.
2. Returns HTTP 404 if it does not exist.
3. Retrieves associated herbs.
4. Resolves the illness's English name.
5. Adds English, Hindi, Sanskrit, and selected-language labels, along with provenance and classification metadata, to each herb result.

### 8.3 `GET /api/stage-c/status`

Handler: `api_stage_c_status()`

Returns database capability information.

The response includes:

- `schema_version`
- `stage_c_available`
- `is_corrupt_ledger`
- `ledger`
- `error`

The route separately attempts to retrieve the migration versions ordered by row ID. If that query fails, it returns an empty ledger list.

This endpoint is useful for checking whether the local database advertises Stage C availability.

### 8.4 `GET /api/stage-c/herbs/{herb_id}/profile`

Handler: `api_herb_dravyaguna_profile()`

Query parameters:

- `language`: restricted to `en`, `hi`, or `sa`
- `include_disputed`
- `include_provisional`

The handler:

1. Opens a SQLite connection and enables foreign keys.
2. Checks database capability.
3. Returns HTTP 500 for a corrupt migration ledger.
4. Returns HTTP 501 when Stage C is unavailable.
5. Calls `herb_dravyaguna_profile()` and returns its result.
6. Converts a `KeyError` into HTTP 404.
7. Closes the connection.

### 8.5 `GET /api/stage-c/herbs/{herb_id}/reconciliation`

Handler: `api_herb_virya_reconciliation()`

This endpoint follows the same capability checks as the profile endpoint, then returns the result of `reconcile_herb_virya()`.

It returns HTTP 500 for a corrupt ledger, HTTP 501 when Stage C is unavailable, and HTTP 404 when the repository API raises `KeyError` for the requested herb.

## 9. Stage C Capability Handling

The application does not apply migrations automatically.

It relies on `validate_schema_migration_ledger()` through `get_database_capability()` to decide whether normalized Stage C features are available.

The route behavior differs by endpoint:

| Route | Valid schema without Stage C | Corrupt migration ledger |
|---|---|---|
| `/herbs/{herb_id}` | Uses legacy presentation fallback | Also follows the non-Stage-C fallback path |
| `/stage-c/reconciliation/{herb_id}` | HTTP 501 | HTTP 500 |
| `/api/stage-c/herbs/{herb_id}/profile` | HTTP 501 | HTTP 500 |
| `/api/stage-c/herbs/{herb_id}/reconciliation` | HTTP 501 | HTTP 500 |
| `/api/stage-c/status` | Reports capability state | Reports corruption/error state |

The Stage C error messages explain that normalized semantic features require schema version 3.

A valid migration ledger is a capability check, not a complete audit of all database objects. The application does not run Migration 3 as part of serving a request.

## 10. Application Object and Startup

At module level:

```python
app = create_app()
```

This creates the default FastAPI application when the module is imported.

The module also defines:

### `run() -> None`

Starts the local development server through Uvicorn:

```python
uvicorn.run(
    "herbal_almanac.web_app:app",
    host="127.0.0.1",
    port=8000,
    reload=True,
)
```

When the module is executed directly, the `if __name__ == "__main__"` block calls `run()`.

The server binds to loopback (`127.0.0.1`) and port `8000` in this development configuration.

## 11. Running the Application

From an environment where the package and its dependencies are installed:

```bash
uvicorn herbal_almanac.web_app:app --reload
```

Alternatively:

```bash
python -m herbal_almanac.web_app
```

To select a database explicitly through the environment:

```bash
# Linux/macOS
HERBAL_ALMANAC_DATABASE=/path/to/database.db uvicorn herbal_almanac.web_app:app --reload
```

On Windows PowerShell:

```powershell
$env:HERBAL_ALMANAC_DATABASE = "C:\path\to\database.db"
uvicorn herbal_almanac.web_app:app --reload
```

The default development server is available at:

```text
http://127.0.0.1:8000
```

## 12. Testing Example

The application factory accepts a database path, which makes it possible to test the app against a controlled database.

```python
from fastapi.testclient import TestClient
from herbal_almanac.web_app import create_app

app = create_app("data/demo.db")
client = TestClient(app)

response = client.get("/api/stage-c/status")

print(response.status_code)
print(response.json())
```

A test should use a database prepared for the behavior being tested. Stage C routes require a valid version-3 migration ledger and the corresponding schema.

## 13. Design Boundaries and Limitations

- The web application is an interface over existing data-access and repository functions; it is not the ingestion pipeline.
- The HTML and JSON routes are read-oriented and do not expose claim-adjudication or migration-writing endpoints.
- The application does not automatically apply migrations.
- Stage C routes depend on migration-ledger capability checks.
- A valid migration ledger does not prove that every expected table, index, trigger, or constraint is present.
- Semantic profile localization is limited to English, Hindi, and Sanskrit. Other UI languages use English for the Stage C semantic profile.
- Illness glossary labels retain their own provenance and verification metadata; displaying a translation does not certify it.
- The guide route uses the database operator's `_connection()` helper, which is a private implementation detail.
- The application depends on its packaged templates and stylesheet being present.

The web layer coordinates the modules; it should not become the place where database migrations, source-data cleaning, or claim-review rules are implemented.
