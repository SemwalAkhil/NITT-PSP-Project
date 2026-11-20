# Semantic Backfill Engine (`backfill_engine.py`)

## 1. Purpose
The `backfill_engine.py` module migrates Stage B legacy source claims into Stage C normalized Dravyaguna concepts and relationships. It grounds raw text claims against the canonical catalog without altering underlying historical records.

## 2. Where it fits
- **Upstream callers:** Called by `AyurvedicAlmanac.run_stage_c_backfill()`, the `upgrade-stage-c` CLI command, and migration scripts.
- **Downstream dependencies:** Calls `concept_catalog` for canonical concepts and `schema_capability_gate` to ensure Schema Version 3.

## 3. Key functions and classes
- `capture_stage_b_table_snapshot(conn)`: Accepts a `sqlite3.Connection`, returns a `dict[str, int]` row-count mapping; snapshots Stage B tables to verify row counts remain invariant.
- `verify_stage_b_row_invariance(before, after)`: Accepts two row-count snapshots, returns `None`; asserts that no Stage B legacy records were dropped or modified.
- `run_stage_c_semantic_backfill(connection, now=None)`: Accepts an active `sqlite3.Connection` and optional ISO timestamp, returns a metrics dictionary; parses claims and seeds concept mappings, properties, dosha assertions, parts, preparations, and indications.

## 4. Worked example
```python
import sqlite3
from herbal_almanac.backfill_engine import run_stage_c_semantic_backfill

conn = sqlite3.connect("ayurvedic.db")
conn.execute("PRAGMA foreign_keys = ON;")
with conn:
    metrics = run_stage_c_semantic_backfill(conn)
    print("Mapped claims:", metrics["inserted_mappings"])
conn.close()
```
