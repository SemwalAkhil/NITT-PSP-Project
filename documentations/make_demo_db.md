# Demo Database Generator (`scripts/make_demo_db.py`)

## 1. Purpose and Overview

`scripts/make_demo_db.py` is a standalone utility designed to synthesize a complete, self-contained, and fully populated SQLite demo database strictly offline. It enables instructors, evaluators, and developers to explore the entire application—including both legacy Stage B provenance tables and advanced Stage C semantic Dravyaguna features—without requiring live network connectivity to the CCRAS DRAVYA portal.

## 2. Inputs and Parameters

The script can be executed directly as a CLI tool or imported programmatically:

- **CLI Options:**
  - `--database` / `-d` (`str`, optional): Path to the target SQLite database file. Defaults to `data/demo.db` (which is gitignored by `*.db`).
- **Programmatic Arguments (`build_demo_database`):**
  - `database_path` (`Path | str | None`): Destination database path.
  - `sample_path` (`Path | str | None`): Custom path to the HTML source fixture (defaults to `sample.html` in the repository root).
- **Environment Prerequisites:**
  - Standard Python 3.10+ virtual environment with `herbal_almanac` installed (`pip install -e ".[web]"`).

## 3. Outputs and Artifacts

1. **SQLite Database File:**
   - Schema Version: **3** (`[1, 2, 3]` in `schema_migrations`).
   - Plant Records: 1 CCRAS DRAVYA plant record parsed from `sample.html`.
   - Attributes & Claims: Vernacular names, botanical classification, morphology, Rasa, Guna, Virya, Vipaka, and Doshakarma.
   - Manual Curations: 2 manual illnesses ("Digestive Weakness", "Chronic Fatigue") and 2 manual treatment relationships (`treatment.source = 'manual'`).
   - Concept Catalog: 136 canonical concepts and 649 multilingual labels (Hindi, English, Sanskrit Devanagari, and IAST).
   - Semantic Mappings: Backfilled `concept_claim_mappings`, `herb_dravyaguna_properties`, and directional `herb_dosha_effects`.
2. **Standard Output:**
   - Displays the absolute path of the generated database.
   - Outputs copy-paste launch commands for Linux/macOS and Windows PowerShell to start the FastAPI web GUI.

## 4. Execution Workflow

```
[sample.html]
      │
      ▼
parse_plant() ───► PlantRecord ───► AyurvedicAlmanac.insert_record()
                                                │
                                                ▼
                                    [Schema Version 2 Baseline]
                                    - herbs, attributes, claims
                                    - scraped treatment links
                                                │
                                                ▼
                                    AyurvedicAlmanac.add_illness()
                                    AyurvedicAlmanac.add_treatment()
                                    - manual illness & treatments
                                                │
                                                ▼
                                    AyurvedicAlmanac.upgrade_to_stage_c()
                                    - Migration 3 DDL & 44 triggers
                                    - Canonical Concept Catalog seeded
                                                │
                                                ▼
                                    AyurvedicAlmanac.run_stage_c_backfill()
                                    - Semantic concept mappings
                                    - Dravyaguna properties & Doshas
                                                │
                                                ▼
                                    [Ready Demo Database (v3)]
```

## 5. Verification

The generator is covered by automated offline unit tests in `tests/test_demo_db.py`:
- `test_build_demo_database_offline`: Generates a database in `tmp_path`, verifying schema ledger `[1, 2, 3]`, plant row presence, manual illnesses (`machine_generated = 0`), manual treatment links (`source = 'manual'`), and Stage C concept/property rows.
- `test_make_demo_db_cli_invocation`: Executes the script via `subprocess.run` with a temporary path and asserts that the launch command is printed to stdout.

Verification command:
```bash
python -m pytest tests/test_demo_db.py -q
```
