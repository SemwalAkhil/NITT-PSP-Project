"""
Herbal Almanac — Offline Demo Database Generator Unit Tests.

Verifies:
1. build_demo_database builds a self-contained SQLite database completely offline.
2. Ingests sample.html plant records, manual illnesses, and manual treatment relationships.
3. Upgrades successfully to Stage C (Schema Version 3) and runs semantic backfill.
4. CLI execution of scripts/make_demo_db.py prints database path and launch command.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from herbal_almanac.schema_capability_gate import validate_schema_migration_ledger
from scripts.make_demo_db import build_demo_database

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "make_demo_db.py"


def test_build_demo_database_offline(tmp_path: Path):
    """Proves build_demo_database creates a complete Schema v3 database with manual and semantic records."""
    db_file = tmp_path / "demo_test.db"
    returned_path = build_demo_database(database_path=db_file)

    assert returned_path.resolve() == db_file.resolve()
    assert db_file.is_file(), "Demo database file was not created!"

    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        # 1. Verify Schema Version 3
        version = validate_schema_migration_ledger(conn)
        assert version == 3

        # 2. Verify Ingested Plant Record
        herb = conn.execute("SELECT * FROM herbs WHERE id = 1;").fetchone()
        assert herb is not None
        assert herb["original_name"] is not None

        # 3. Verify 2 Manual Illnesses
        illnesses = conn.execute(
            "SELECT english_name, machine_generated, verification_status FROM illness WHERE english_name IN ('Digestive Weakness', 'Chronic Fatigue');"
        ).fetchall()
        assert len(illnesses) == 2
        for ill in illnesses:
            assert ill["machine_generated"] == 0
            assert ill["verification_status"] == "verified"

        # 4. Verify 2 Manual Treatment Links
        treatments = conn.execute(
            "SELECT * FROM treatment WHERE herb_id = 1 AND source = 'manual';"
        ).fetchall()
        assert len(treatments) == 2

        # 5. Verify Stage C Concept Catalog Seeding
        concept_count = conn.execute("SELECT COUNT(*) FROM dravyaguna_concepts;").fetchone()[0]
        assert concept_count == 136

        # 6. Verify Stage C Semantic Backfill
        mapping_count = conn.execute("SELECT COUNT(*) FROM concept_claim_mappings;").fetchone()[0]
        assert mapping_count > 0

        prop_count = conn.execute("SELECT COUNT(*) FROM herb_dravyaguna_properties;").fetchone()[0]
        assert prop_count > 0

    finally:
        conn.close()


def test_make_demo_db_cli_invocation(tmp_path: Path):
    """Proves scripts/make_demo_db.py can be invoked via CLI and outputs launch instructions."""
    db_file = tmp_path / "cli_demo.db"
    cmd = [
        sys.executable,
        str(SCRIPT_PATH),
        "--database",
        str(db_file),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"make_demo_db.py CLI failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"

    assert db_file.is_file(), "CLI failed to create demo database!"
    output = res.stdout
    assert f"HERBAL_ALMANAC_DATABASE={db_file.resolve()} uvicorn herbal_almanac.web_app:app" in output
