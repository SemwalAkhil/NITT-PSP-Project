# Schema Capability Gate (`schema_capability_gate.py`)

## 1. Purpose
The `schema_capability_gate.py` module inspects the SQLite migration ledger and controls access to Stage C features. It ensures graceful degradation on Schema Version 2 databases and prevents corrupted or out-of-order schema states.

## 2. Where it fits
- **Upstream callers:** Called by `web_app.py`, `repository_api.py`, `backfill_engine.py`, `concept_catalog.py`, and `cli.py` before executing Stage C logic.
- **Downstream dependencies:** Queries the `schema_migrations` table directly via standard `sqlite3.Connection`.

## 3. Key functions and classes
- `MigrationError`: Exception raised when the database migration ledger is missing, corrupted, non-sequential, or contains unexpected future versions.
- `FeatureUnavailableError`: Exception raised when Stage C operations are attempted on a valid Schema Version 2 database.
- `validate_schema_migration_ledger(conn)`: Accepts a `sqlite3.Connection`, returns the integer schema version (`2` for `[1, 2]`, `3` for `[1, 2, 3]`); raises `MigrationError` on invalid ledgers.
- `require_stage_c_schema_v3(conn)`: Accepts a connection, returns `None`; raises `FeatureUnavailableError` if version is 2 or `MigrationError` if invalid.
- `stage_c_capability_gate(func)`: Decorator that wraps functions to enforce Schema Version 3 verification before execution.

## 4. Worked example
```python
import sqlite3
from herbal_almanac.schema_capability_gate import validate_schema_migration_ledger, require_stage_c_schema_v3

conn = sqlite3.connect("ayurvedic.db")
version = validate_schema_migration_ledger(conn)
print(f"Active Schema Version: {version}")  # 2 or 3
require_stage_c_schema_v3(conn)            # Raises FeatureUnavailableError if version == 2
conn.close()
```
