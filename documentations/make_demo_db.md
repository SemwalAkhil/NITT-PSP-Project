# Demo Database Generator (`make_demo_db.py`)

## 1. Purpose
The `make_demo_db.py` script synthesizes a complete, standalone SQLite demo database strictly offline from local test fixtures. It enables immediate evaluation of both Stage B provenance records and Stage C semantic profiles without live network access.

## 2. Where it fits
- **Upstream callers:** Invoked from the terminal by evaluators or imported by automated integration tests (`tests/test_demo_db.py`).
- **Downstream dependencies:** Calls `scrapper.py` (`parse_plant`), `database_operator.py` (`AyurvedicAlmanac`), and `backfill_engine.py`.

## 3. Key functions and classes
- `build_demo_database(database_path=None, sample_path=None)`: Parses `sample.html`, creates baseline tables, adds manual treatments, applies Stage C upgrade, and backfills semantic concepts; returns the absolute `Path` of the created database.
- `main()`: Command-line entry point that parses `--database` arguments, generates the database, and prints copy-paste Web GUI startup commands.

## 4. Worked example
```bash
# Generate the demo database offline (defaults to data/demo.db)
python scripts/make_demo_db.py

# Launch the Web GUI pointing to the generated demo database
HERBAL_ALMANAC_DATABASE=data/demo.db uvicorn herbal_almanac.web_app:app
```

## 5. Demo Evaluation Notes
- **Zero-Network Synthesis:** Builds Schema Version 3 directly from `sample.html` in under 2 seconds without external HTTP requests.
- **Multi-Tier Exploration:** Contains both automated CCRAS DRAVYA scraped records (`source='CCRAS_DRAVYA'`) and manual curations (`source='manual'`), allowing immediate testing of provenance separation.
- **Stage C Verification:** Ships fully upgraded with 136 seeded canonical concepts, 640+ multilingual labels, and backfilled Dravyaguna property chips and Virya reconciliation metrics.
- **Git Safety:** Writes by default to `data/demo.db`, which is ignored by Git (`*.db` in `.gitignore`), preventing accidental check-ins.
