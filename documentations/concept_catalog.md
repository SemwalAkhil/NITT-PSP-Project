# Canonical Concept Catalog (`concept_catalog.py`)

## 1. Purpose
The `concept_catalog.py` module defines and seeds the authoritative Dravyaguna concept catalog across 11 pharmacological domains. It provides standardized concept codes, prefix validators, and 640+ multilingual lexical labels in Sanskrit, Hindi, and English.

## 2. Where it fits
- **Upstream callers:** Called during Stage C migration (`migration_0003_semantic_dravyaguna.py`), by `backfill_engine.py` during mapping, and by `repository_api.py` for label resolution.
- **Downstream dependencies:** Calls `schema_capability_gate.py` to verify Schema Version 3 before database operations.

## 3. Key functions and classes
- `validate_concept_code_prefix(concept_code, concept_domain)`: Accepts code and domain strings, returns `None`; raises `ValueError` if code violates domain prefix rules (e.g. `RASA_` for `rasa`).
- `normalize_label(label)`: Accepts a label string, returns cleaned text with stripped punctuation and normalized whitespace for indexing.
- `seed_canonical_concept_catalog(connection, now=None)`: Accepts a `sqlite3.Connection`, returns row count inserted; idempotently inserts 136 canonical concepts and multilingual labels.
- `resolve_concept_display_label(connection, concept_id, language)`: Accepts connection, concept ID, and language code, returns display string; falls back to English or concept code if language label is missing.

## 4. Worked example
```python
import sqlite3
from herbal_almanac.concept_catalog import validate_concept_code_prefix, seed_canonical_concept_catalog

validate_concept_code_prefix("RASA_TIKTA", "rasa")  # Validates prefix pattern

conn = sqlite3.connect("ayurvedic.db")
conn.execute("PRAGMA foreign_keys = ON;")
with conn:
    count = seed_canonical_concept_catalog(conn)
    print(f"Seeded concepts: {count}")
conn.close()
```
