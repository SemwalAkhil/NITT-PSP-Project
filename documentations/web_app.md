# Web Application (`web_app.py`)

## 1. Purpose
The `web_app.py` module implements the optional local browser GUI and read-only REST API using FastAPI and Jinja2 templates. It provides a version-aware interface for exploring herbs, illnesses, Dravyaguna properties, and Virya reconciliation without writing to SQLite.

## 2. Where it fits
- **Upstream callers:** Launched via `uvicorn herbal_almanac.web_app:app` or created with `create_app(db_path)` in test suites.
- **Downstream dependencies:** Calls `database_operator.py` for queries, `repository_api.py` for semantic profiles, `herb_view.py` for view models, and `illness_glossary.py` for localized names.

## 3. Key functions and classes
- `create_app(database_path=None)`: Factory function returning a configured `FastAPI` instance bound to a target SQLite file and static/template assets.
- `get_database_capability(conn)`: Inspects migration ledger to determine whether Stage C semantic features are available (Schema Version 3) or degraded (Version 2).
- `format_readable_illness(name)`: Jinja filter converting Harvard-Kyoto transliterated condition names into title case (e.g. `KAsa` &rarr; `Kasa`).
- `clean_language_param(language)`: Validates `?language=<code>` query parameters against the 15 supported languages, defaulting to `"en"`.

## 4. Worked example
```python
from pathlib import Path
from fastapi.testclient import TestClient
from herbal_almanac.web_app import create_app

app = create_app(Path("data/demo.db"))
client = TestClient(app)
response = client.get("/herbs/1?language=hi")
print(response.status_code)  # 200
```
