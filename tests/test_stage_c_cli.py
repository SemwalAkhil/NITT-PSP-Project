"""
Herbal Almanac — Stage C.2 CLI Integration Tests
Tests for 'upgrade-stage-c' and 'stage-c-status' commands.
"""

import shutil
from pathlib import Path
import sqlite3
import pytest
from typer.testing import CliRunner

from herbal_almanac.cli import app
from herbal_almanac.database_operator import AyurvedicAlmanac


runner = CliRunner()


@pytest.fixture
def sample_v2_db(tmp_path: Path, hermetic_v2_db_path: Path) -> Path:
    """Creates a temporary, disposable copy of the hermetic v2 database for CLI testing."""
    db_path = tmp_path / "cli_test_v2.db"
    shutil.copy2(hermetic_v2_db_path, db_path)
    return db_path


def test_cli_stage_c_status_on_v2(sample_v2_db: Path):
    """'stage-c-status' on a Schema v2 database reports version 2 and inactive status."""
    result = runner.invoke(app, ["stage-c-status", "--database", str(sample_v2_db)])
    assert result.exit_code == 0
    assert "Stage C Status & Capability Report" in result.output
    assert "Schema Version" in result.output
    assert "2" in result.output
    assert "NO" in result.output
    assert "upgrade-stage-c" in result.output
    assert "Schema Version 2" in result.output


def test_cli_upgrade_stage_c_confirmation_abort(sample_v2_db: Path):
    """'upgrade-stage-c' without --yes prompts for confirmation and aborts on 'n'."""
    result = runner.invoke(
        app,
        ["upgrade-stage-c", "--database", str(sample_v2_db)],
        input="n\n",
    )
    assert result.exit_code == 0
    assert "Upgrade aborted by user" in result.output

    # Verify database remains strictly at schema version 2
    conn = sqlite3.connect(sample_v2_db)
    ledger = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()]
    conn.close()
    assert ledger == [1, 2]


def test_cli_upgrade_stage_c_with_yes(sample_v2_db: Path):
    """'upgrade-stage-c' with --yes upgrades to v3, seeds catalog, and runs backfill."""
    result = runner.invoke(
        app,
        ["upgrade-stage-c", "--database", str(sample_v2_db), "--yes"],
    )
    assert result.exit_code == 0
    assert "Stage C Semantic Upgrade Summary" in result.output
    assert "Version 3" in result.output
    assert "Seeded Canonical Concepts" in result.output
    assert "136" in result.output
    assert "Backfilled Properties" in result.output
    assert "Cryptographically Verified" in result.output
    assert "Database successfully upgraded to Stage C." in result.output

    # Verify database ledger is [1, 2, 3]
    conn = sqlite3.connect(sample_v2_db)
    ledger = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()]
    num_concepts = conn.execute("SELECT COUNT(*) FROM dravyaguna_concepts").fetchone()[0]
    num_props = conn.execute("SELECT COUNT(*) FROM herb_dravyaguna_properties").fetchone()[0]
    conn.close()
    assert ledger == [1, 2, 3]
    assert num_concepts == 136
    assert num_props > 0


def test_cli_stage_c_status_on_v3(sample_v2_db: Path):
    """'stage-c-status' on an upgraded v3 database displays concept and mapping counts."""
    # First upgrade
    upg = runner.invoke(app, ["upgrade-stage-c", "--database", str(sample_v2_db), "--yes"])
    assert upg.exit_code == 0

    # Then check status
    result = runner.invoke(app, ["stage-c-status", "--database", str(sample_v2_db)])
    assert result.exit_code == 0
    assert "Stage C Status & Capability Report" in result.output
    assert "Schema Version" in result.output
    assert "3" in result.output
    assert "YES (Version 3)" in result.output
    assert "Canonical Concepts" in result.output
    assert "136" in result.output
    assert "Dravyaguna Properties" in result.output


def test_cli_upgrade_missing_database(tmp_path: Path):
    """'upgrade-stage-c' fails gracefully when the target database does not exist."""
    missing_path = tmp_path / "nonexistent.db"
    result = runner.invoke(app, ["upgrade-stage-c", "--database", str(missing_path), "--yes"])
    assert result.exit_code != 0
    assert "Target database file does not exist" in result.output
