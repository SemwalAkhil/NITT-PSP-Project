# Claim Lifecycle & Omission Engine (`claim_lifecycle.py`)

## 1. Purpose
The `claim_lifecycle.py` module manages the review and curation workflow for botanical assertions and semantic mappings. It provides audit-safe state transitions (superseding, restoring, and rejecting claims) while maintaining complete historical lineage.

## 2. Where it fits
- **Upstream callers:** Called by curator tooling, repository review APIs, and data reconciliation processes.
- **Downstream dependencies:** Calls `schema_capability_gate` to ensure Schema Version 3 and enforces foreign-key constraints across `source_claims` and `concept_claim_mappings`.

## 3. Key functions and classes
- `supersede_source_claim(connection, old_claim_id, new_claim_id, reviewer, now=None)`: Accepts a database connection, claim IDs, reviewer name, and optional timestamp, returns `None`; marks an old claim as superseded and links correction lineage.
- `restore_source_claim(connection, claim_id, reviewer, now=None)`: Accepts a database connection, claim ID, reviewer name, and optional timestamp, returns `None`; restores a rejected or superseded claim back to its prior reviewed status.
- `reject_source_claim(connection, claim_id, reviewer, notes, now=None)`: Accepts a database connection, claim ID, reviewer identity, review note, and optional timestamp, returns `None`; marks an assertion as rejected and deactivates dependent property rows.
- `review_concept_claim_mapping(connection, mapping_id, new_status, reviewer, confidence=None, now=None)`: Accepts a connection, mapping ID, status string, reviewer, optional confidence, and timestamp, returns `None`; updates human-verified mapping decisions.

## 4. Worked example
```python
import sqlite3
from herbal_almanac.claim_lifecycle import review_concept_claim_mapping

conn = sqlite3.connect("ayurvedic.db")
conn.execute("PRAGMA foreign_keys = ON;")
with conn:
    review_concept_claim_mapping(conn, mapping_id=42, new_status="reviewed", reviewer="Expert Curator")
conn.close()
```
