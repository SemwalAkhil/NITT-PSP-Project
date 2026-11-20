# Database Operator & Schema Reference (`database_operator.py`)

## 1. Purpose
The `database_operator.py` module manages SQLite persistence, connection concurrency, versioned schema migrations, and entity queries. It provides atomic CRUD operations for plant records, treatments, and flexible source attributes.

## 2. Where it fits
- **Upstream callers:** Called by `cli.py`, `scrapper.py`, `web_app.py`, and test fixtures.
- **Downstream dependencies:** Executes SQL against SQLite, calls `cleaning.py` for search key normalization, and coordinates with `migrations/` and `backfill_engine.py`.

## 3. Key functions and classes
- `AyurvedicAlmanac`: Main interface class for database connections, transactions, schema initialization, and searches.
- `create_database()`: Creates baseline application tables (`herbs`, `illness`, `treatment`, `herb_attributes`, `herb_doshas`) and applies versioned migrations.
- `insert_record(record)`: Accepts a `PlantRecord`, returns inserted `int` herb ID; upserts plant identity, claims, and links in an atomic transaction.
- `search_herbs(query)`: Accepts search string, returns ranked list of matching herb dictionaries across English, botanical, and Indic vernacular names.
- `search_illnesses(query)`: Accepts search string, returns ranked list of condition dictionaries with canonical key resolution.
- `upgrade_to_stage_c()`: Applies Migration 3 DDL, seeds the concept catalog, and executes semantic backfill.

## 4. Worked example
```python
from pathlib import Path
from herbal_almanac.database_operator import AyurvedicAlmanac

db = AyurvedicAlmanac(Path("data/ayurvedic.db"))
db.create_database()
herbs = db.search_herbs("Tulsi")
for h in herbs:
    print(h["english_name"], h["botanical_name"])
```

## 5. Database Schema Reference
| Table | Stage / Migration | Purpose |
| :--- | :--- | :--- |
| `herbs` | Legacy Core | Botanical identity, source keys, transliteration, and retrieval timestamps. |
| `illness` | Legacy Core | Clinical conditions, search keys, and machine-generation verification status. |
| `treatment` | Legacy Core | Herb-to-illness relationships; `source` distinguishes scraped from manual links. |
| `herb_attributes` | Legacy Core | Flexible section-qualified attributes, source text, and translation metadata. |
| `herb_doshas` | Legacy Core | Normalized Vata/Pitta/Kapha effects tied to raw Doshakarma statements. |
| `schema_migrations` | Migration 1 | Version ledger tracking applied migrations (`[1, 2]` or `[1, 2, 3]`). |
| `sources` | Migration 1 | Identity of source repositories (e.g. `CCRAS_DRAVYA`, `manual`). |
| `source_records` | Migration 1 | External source record identifiers and retrieval tracking. |
| `source_claims` | Migration 1 | Immutable source assertions with review status and supersession lineage. |
| `legacy_herb_map` | Migration 1 | 1-to-1 surrogate mapping preserving legacy integer herb IDs. |
| `herb_names` | Migration 1 | Multilingual herb names linked to verified claims. |
| `taxa`, `herb_taxa` | Migration 2 | Conservative botanical taxonomy concepts and herb associations. |
| `dravyaguna_concepts`| Migration 3 | Canonical concept ontology across 11 pharmacological domains. |
| `concept_labels` | Migration 3 | Multilingual labels (Sanskrit Devanagari/IAST, Hindi, English). |
| `concept_claim_mappings`| Migration 3 | Grounded mappings linking source claims to canonical concepts. |
| `herb_dravyaguna_properties`| Migration 3 | Normalized properties (Rasa, Guna, Virya, Vipaka, Prabhava, Karma). |
| `herb_dosha_effects` | Migration 3 | Directional Dosha effects linked to verified claims. |
| `herb_plant_parts` | Migration 3 | Officinal plant parts (Prayojyāṅga) linked to concept mappings. |
| `herb_preparations` | Migration 3 | Formulations and dosage forms associated with plant parts. |
| `herb_indications` | Migration 3 | Curated therapeutic indications mapped to clinical concepts. |
