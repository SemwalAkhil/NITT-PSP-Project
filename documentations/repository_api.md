# Repository API & Presentation Services (`repository_api.py`)

## 1. Purpose
The `repository_api.py` module provides read-only presentation queries for normalized Stage C Dravyaguna profiles and multi-source Virya reconciliation. It enforces schema gating and multi-concept quarantine so that ambiguous claims never corrupt presentation cards.

## 2. Where it fits
- **Upstream callers:** Called by `web_app.py` in the `/herbs/{id}` detail route and `/stage-c/reconciliation/{id}` dashboard route, as well as REST endpoints.
- **Downstream dependencies:** Calls `schema_capability_gate.py` to verify Schema Version 3, `concept_catalog.py` for label resolution, and executes `migrations/virya_reconciliation.sql`.

## 3. Key functions and classes
- `ViryaPairwiseDivergenceRecord`: `TypedDict` structure detailing pairwise comparisons between herb sources (botanical identity basis, virya claims, plant parts, and divergence status).
- `herb_dravyaguna_profile(connection, herb_id, language="en", include_disputed=False, include_provisional=False)`: Queries normalized properties, parts, preparations, and indications; returns structured dictionary with canonical labels.
- `reconcile_herb_virya(connection, herb_id)`: Executes the Virya reconciliation query against peer monographs; returns 4-tier agreement and divergence statistics.

## 4. Worked example
```python
import sqlite3
from herbal_almanac.repository_api import herb_dravyaguna_profile, reconcile_herb_virya

conn = sqlite3.connect("ayurvedic.db")
conn.execute("PRAGMA foreign_keys = ON;")
profile = herb_dravyaguna_profile(conn, herb_id=1, language="en")
reconciliation = reconcile_herb_virya(conn, herb_id=1)
print("Properties count:", len(profile["properties"]))
print("Virya pairs:", reconciliation["summary_counts"]["total_reconciled_pairs"])
conn.close()
```
