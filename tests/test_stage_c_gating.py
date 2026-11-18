"""
Herbal Almanac — Stage C.2 Work Package 2 (WP-2)
Unit Test Suite for Schema Capability Gating & Migration Ledger Validation
"""

import os
import re
import sqlite3
import tempfile
import sys
from pathlib import Path
import pytest

# Ensure stage_c_review and src are in sys.path
REVIEW_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = REVIEW_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(REVIEW_DIR) not in sys.path:
    sys.path.insert(0, str(REVIEW_DIR))

from herbal_almanac.database_operator import AyurvedicAlmanac
from herbal_almanac.migrations import migration_0003_semantic_dravyaguna
from herbal_almanac.schema_capability_gate import (
    MigrationError,
    FeatureUnavailableError,
    validate_schema_migration_ledger,
    require_stage_c_schema_v3,
    get_schema_version,
)
from herbal_almanac.concept_catalog import (
    seed_canonical_concept_catalog,
    resolve_concept_display_label,
    resolve_concept_sanskrit_references,
)


@pytest.fixture
def temp_db_path():
    """Provides a clean temporary database path."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


# ============================================================================
# 1. Uninitialized Database Tests
# ============================================================================

def test_uninitialized_database_missing_schema_migrations():
    """Verifies that a database lacking schema_migrations raises MigrationError."""
    conn = sqlite3.connect(":memory:")
    
    with pytest.raises(
        MigrationError,
        match="Database schema_migrations ledger table does not exist. Initialize database via create_database\\(\\) first.",
    ):
        validate_schema_migration_ledger(conn)
    
    with pytest.raises(MigrationError):
        require_stage_c_schema_v3(conn)
    
    conn.close()


# ============================================================================
# 2. Valid Schema Version 2 Baseline Tests
# ============================================================================

def test_valid_schema_v2_ledger(temp_db_path):
    """Verifies that a standard Stage B database has ledger [1, 2], returns version 2, and raises FeatureUnavailableError."""
    almanac = AyurvedicAlmanac(temp_db_path)
    almanac.create_database()
    
    conn = sqlite3.connect(temp_db_path)
    try:
        # Ledger validation returns 2
        version = validate_schema_migration_ledger(conn)
        assert version == 2
        assert get_schema_version(conn) == 2
        
        # require_stage_c_schema_v3 fails fast with FeatureUnavailableError
        expected_msg = (
            "Stage C normalized semantic features require schema version 3 "
            "\\(current database version is 2\\). Apply Migration 3 to enable Dravyaguna semantic profiles."
        )
        with pytest.raises(FeatureUnavailableError, match=expected_msg):
            require_stage_c_schema_v3(conn)
    finally:
        conn.close()


# ============================================================================
# 3. Valid Schema Version 3 Baseline Tests
# ============================================================================

def test_valid_schema_v3_ledger(temp_db_path):
    """Verifies that an upgraded Stage C database has ledger [1, 2, 3], returns version 3, and unlocks Stage C."""
    almanac = AyurvedicAlmanac(temp_db_path)
    almanac.create_database()
    
    conn = sqlite3.connect(temp_db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        # Apply Migration 3
        migration_0003_semantic_dravyaguna.apply_migration(conn)
        
        # Ledger validation returns 3
        version = validate_schema_migration_ledger(conn)
        assert version == 3
        assert get_schema_version(conn) == 3
        
        # Capability gate passes cleanly without raising
        require_stage_c_schema_v3(conn)
    finally:
        conn.close()


# ============================================================================
# 4. Malformed, Gapped, Duplicate, and Unsupported Ledger Tests
# ============================================================================

@pytest.mark.parametrize(
    "invalid_versions,expected_ledger_repr",
    [
        ([], "[]"),
        ([1], "[1]"),
        ([1, 3], "[1, 3]"),
        ([2, 3], "[2, 3]"),
        ([2, 1], "[2, 1]"),
        ([1, 3, 2], "[1, 3, 2]"),
        ([1, 2, 2], "[1, 2, 2]"),
        ([1, 2, 3, 3], "[1, 2, 3, 3]"),
        ([0, 1, 2], "[0, 1, 2]"),
        ([-1, 1, 2], "[-1, 1, 2]"),
        ([1, 2, 3, 4], "[1, 2, 3, 4]"),
    ],
)
def test_malformed_and_unsupported_ledgers(invalid_versions, expected_ledger_repr):
    """Verifies that any migration sequence other than [1, 2] or [1, 2, 3] raises MigrationError."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );
    """)
    # If duplicate or out-of-order versions are tested, use a table without INTEGER PRIMARY KEY so rowid preserves insertion order
    if len(invalid_versions) != len(set(invalid_versions)) or invalid_versions != sorted(invalid_versions):
        conn.execute("DROP TABLE schema_migrations;")
        conn.execute("""
            CREATE TABLE schema_migrations (
                version INTEGER,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
        """)
    
    for v in invalid_versions:
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, 'test', '2026-11-19T00:00:00Z');",
            (v,),
        )
    
    expected_msg = (
        f"Unsupported database schema migration ledger {expected_ledger_repr}. "
        f"Expected exact sequence [1, 2] or [1, 2, 3]."
    )
    with pytest.raises(MigrationError, match=re.escape(expected_msg)):
        validate_schema_migration_ledger(conn)
    
    with pytest.raises(MigrationError, match=re.escape(expected_msg)):
        require_stage_c_schema_v3(conn)
    
    conn.close()


# ============================================================================
# 5. Production Database Version 2 Isolation Tests
# ============================================================================

def test_production_database_v2_isolation():
    """Verifies read-only that data/inspection.db is strictly protected at schema version 2."""
    db_path = PROJECT_ROOT / "data" / "inspection.db"
    assert db_path.exists(), f"Production inspection DB {db_path} does not exist!"
    
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        # Validates exact [1, 2]
        version = validate_schema_migration_ledger(conn)
        assert version == 2
        
        # Stage C is unavailable
        with pytest.raises(FeatureUnavailableError):
            require_stage_c_schema_v3(conn)
    finally:
        conn.close()


# ============================================================================
# 6. Default create_database Produces Version 2
# ============================================================================

def test_default_create_database_produces_v2(temp_db_path):
    """Verifies that default database creation initializes to schema version 2, never version 3."""
    almanac = AyurvedicAlmanac(temp_db_path)
    almanac.create_database()
    
    conn = sqlite3.connect(temp_db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT version, name FROM schema_migrations ORDER BY version ASC;")
        ledger = cur.fetchall()
        assert ledger == [
            (1, "core_identity_and_provenance"),
            (2, "normalized_botanical_taxonomy"),
        ], f"Expected exactly migrations 1 & 2, got: {ledger}"
        
        # Verify Stage C tables do not exist
        cur.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'dravyaguna_concepts';")
        assert cur.fetchone() is None, "dravyaguna_concepts should not exist in newly created database!"
    finally:
        conn.close()


# ============================================================================
# 7. Concept Catalog Capability Gating on Version 2 and Uninitialized Databases
# ============================================================================

def test_concept_catalog_capability_gating_v2_and_uninitialized(temp_db_path):
    """Verifies that concept_catalog operations fail fast with FeatureUnavailableError on v2 and MigrationError on uninitialized DB."""
    # 1. Uninitialized database -> MigrationError
    uninit_conn = sqlite3.connect(":memory:")
    with pytest.raises(MigrationError):
        seed_canonical_concept_catalog(uninit_conn)
    with pytest.raises(MigrationError):
        resolve_concept_display_label(uninit_conn, 1)
    with pytest.raises(MigrationError):
        resolve_concept_sanskrit_references(uninit_conn, 1)
    uninit_conn.close()
    
    # 2. Valid Schema Version 2 database -> FeatureUnavailableError (NOT sqlite3.OperationalError!)
    almanac = AyurvedicAlmanac(temp_db_path)
    almanac.create_database()
    
    v2_conn = sqlite3.connect(temp_db_path)
    try:
        with pytest.raises(FeatureUnavailableError):
            seed_canonical_concept_catalog(v2_conn)
        with pytest.raises(FeatureUnavailableError):
            resolve_concept_display_label(v2_conn, 1)
        with pytest.raises(FeatureUnavailableError):
            resolve_concept_sanskrit_references(v2_conn, 1)
    finally:
        v2_conn.close()
