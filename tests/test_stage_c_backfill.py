"""
Herbal Almanac — Stage C.2 Work Package 4 (WP-4)
Unit Test Suite for Semantic Backfill Engine, Migration 3 Ledger Validation, & Invariance Checker
"""

import os
import shutil
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
from herbal_almanac.schema_capability_gate import validate_schema_migration_ledger, get_schema_version
from herbal_almanac.concept_catalog import seed_canonical_concept_catalog
from herbal_almanac.backfill_engine import (
    STAGE_B_TABLES,
    capture_stage_b_table_snapshot,
    verify_stage_b_row_invariance,
    run_stage_c_semantic_backfill,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def v2_db():
    """Provides a fresh temporary SQLite database initialized to Schema Version 2 ([1, 2])."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        almanac = AyurvedicAlmanac(db_path)
        almanac.create_database()
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        yield conn, db_path
        conn.close()
    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except OSError:
                pass


@pytest.fixture
def inspection_db_copy():
    """Provides a temporary, disposable copy of data/inspection.db (v2)."""
    orig_path = PROJECT_ROOT / "data" / "inspection.db"
    assert orig_path.exists(), "data/inspection.db must exist for test copy"
    fd, copy_path = tempfile.mkstemp(suffix="_inspection_copy.db")
    os.close(fd)
    shutil.copy2(orig_path, copy_path)
    try:
        conn = sqlite3.connect(copy_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        yield conn, copy_path
        conn.close()
    finally:
        if os.path.exists(copy_path):
            try:
                os.remove(copy_path)
            except OSError:
                pass


def _seed_stage_b_test_herb_and_claims(conn: sqlite3.Connection) -> dict[str, int]:
    """Seeds a representative Stage B herb, source, record, and various claims."""
    # 1. Source
    cursor = conn.execute(
        """
        INSERT INTO sources (source_key, publisher, title)
        VALUES ('CCRAS_DRAVYA', 'CCRAS', 'CCRAS DRAVYA');
        """
    )
    source_id = cursor.lastrowid

    # 2. Source Record
    cursor = conn.execute(
        """
        INSERT INTO source_records (source_id, external_record_key, retrieved_at)
        VALUES (?, '101', '2025-01-01T00:00:00Z');
        """,
        (source_id,),
    )
    source_record_id = cursor.lastrowid

    # 3. Herb
    cursor = conn.execute(
        """
        INSERT INTO herbs (english_name, botanical_name, source, source_record_id)
        VALUES ('Haritaki', 'Terminalia chebula', 'CCRAS_DRAVYA', 101);
        """
    )
    herb_id = cursor.lastrowid

    # 4. Legacy Herb Map
    conn.execute(
        """
        INSERT INTO legacy_herb_map (legacy_herb_id, herb_id, created_at)
        VALUES (?, ?, '2025-01-01T00:00:00Z');
        """,
        (herb_id, herb_id),
    )

    now = '2025-01-01T00:00:00Z'
    claims_to_seed = [
        # Rasa claims
        ('attribute', 'Rasa.Name', 'Tikta'),
        ('attribute', 'Rasa.Name', 'Madhura/Svadu'),
        ('attribute', 'Rasa.रस (हिन्दी)', 'तिक्त'),
        # Guna claims
        ('attribute', 'Guna.Name', 'Laghu/ Aguru'),
        ('attribute', 'Guna.Name', 'Tikshna'),
        # Virya claims
        ('attribute', 'Virya.Name', 'Ushna Virya'),
        ('attribute', 'Virya.Virya (Diacritical)', 'Uṣṇa vīrya'),
        # Vipaka claims
        ('attribute', 'Vipaka.Name', 'Katu vipaka'),
        # Plant Part claims
        ('attribute', 'Parts Used.Name', 'Leaf'),
        ('attribute', 'Parts Used.Name', 'Root'),
        # Preparation Formulation
        ('attribute', 'Dosage Formulation.Dosage(Form)', 'Churna'),
        ('attribute', 'Dosage Formulation.Dosage(Form)', 'Guggulu'),
        # Dosha claim
        ('attribute', 'Doshakarma.Name', 'KaphaVatahara/KaphaVatashamana'),
    ]

    claim_ids = []
    for c_type, s_field, s_expr in claims_to_seed:
        c = conn.execute(
            """
            INSERT INTO source_claims (
                source_record_id, claim_type, source_field, source_expression,
                language_code, normalization_method, verification_status,
                created_by_type, created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'sa', 'exact', 'unreviewed', 'ingest', 'test_seeder', ?, ?);
            """,
            (source_record_id, c_type, s_field, s_expr, now, now),
        )
        claim_ids.append(c.lastrowid)

    return {
        "herb_id": herb_id,
        "source_id": source_id,
        "source_record_id": source_record_id,
        "claim_ids": claim_ids,
    }


# ============================================================================
# 1. Migration 3 Application & Ledger Validation
# ============================================================================

def test_migration_0003_application_and_ledger_validation(v2_db):
    """Verifies that Migration 3 transitions ledger from [1, 2] to [1, 2, 3] and allows catalog seeding."""
    conn, _ = v2_db

    # Baseline ledger check
    versions_before = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY rowid ASC;").fetchall()]
    assert versions_before == [1, 2]
    assert validate_schema_migration_ledger(conn) == 2
    assert get_schema_version(conn) == 2

    # Apply Migration 3
    migration_0003_semantic_dravyaguna.apply_migration(conn)

    # Validated v3 ledger check
    versions_after = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY rowid ASC;").fetchall()]
    assert versions_after == [1, 2, 3]
    assert validate_schema_migration_ledger(conn) == 3
    assert get_schema_version(conn) == 3

    # Seed catalog via WP-1
    counts = seed_canonical_concept_catalog(conn)
    assert counts["concepts"] == 136
    assert counts["labels"] == 649
    assert counts["sources"] == 136

    # Verify active vs provisional breakdown
    active_count = conn.execute("SELECT COUNT(*) FROM dravyaguna_concepts WHERE status = 'active';").fetchone()[0]
    prov_count = conn.execute("SELECT COUNT(*) FROM dravyaguna_concepts WHERE status = 'provisional';").fetchone()[0]
    assert active_count == 129
    assert prov_count == 7


# ============================================================================
# 2. Stage B Row Invariance Checker
# ============================================================================

def test_stage_b_row_invariance_before_and_after_backfill(v2_db):
    """Verifies that applying Migration 3 and running backfill leaves all 13 Stage B tables 100% unaltered."""
    conn, _ = v2_db
    conn.execute("BEGIN IMMEDIATE;")
    _seed_stage_b_test_herb_and_claims(conn)
    conn.commit()

    # Capture pristine Stage B snapshot
    before_snapshot = capture_stage_b_table_snapshot(conn)
    assert len(before_snapshot) == 13
    for tbl in STAGE_B_TABLES:
        assert tbl in before_snapshot

    # Apply Migration 3 (v3)
    migration_0003_semantic_dravyaguna.apply_migration(conn)

    # Run semantic backfill
    now = '2025-01-01T12:00:00Z'
    conn.execute("BEGIN IMMEDIATE;")
    run_stage_c_semantic_backfill(conn, now)
    conn.commit()

    # Capture post-backfill Stage B snapshot
    after_snapshot = capture_stage_b_table_snapshot(conn)

    # Invariance check: must pass with ZERO mutations
    verify_stage_b_row_invariance(before_snapshot, after_snapshot)


def test_stage_b_invariance_checker_detects_mutations(v2_db):
    """Verifies that verify_stage_b_row_invariance correctly detects any row count or content mutation."""
    conn, _ = v2_db
    before_snapshot = capture_stage_b_table_snapshot(conn)

    # Mutate row count
    mutated_snapshot = {tbl: dict(meta) for tbl, meta in before_snapshot.items()}
    mutated_snapshot["herbs"]["count"] += 1
    with pytest.raises(AssertionError, match="row count mutated"):
        verify_stage_b_row_invariance(before_snapshot, mutated_snapshot)

    # Mutate content hash
    mutated_hash_snapshot = {tbl: dict(meta) for tbl, meta in before_snapshot.items()}
    mutated_hash_snapshot["herbs"]["row_hash"] = "0000000000000000000000000000000000000000000000000000000000000000"
    with pytest.raises(AssertionError, match="content row hash divergence"):
        verify_stage_b_row_invariance(before_snapshot, mutated_hash_snapshot)


# ============================================================================
# 3. Backfill Execution, Mapping Calibration, & Audit Logging
# ============================================================================

def test_semantic_backfill_execution_and_calibrated_mappings(v2_db):
    """Verifies that Stage B claims populate concept_claim_mappings with calibrated NULL confidence and relationship tables."""
    conn, _ = v2_db
    conn.execute("BEGIN IMMEDIATE;")
    ids = _seed_stage_b_test_herb_and_claims(conn)
    conn.commit()

    migration_0003_semantic_dravyaguna.apply_migration(conn)

    now = '2025-01-01T12:00:00Z'
    conn.execute("BEGIN IMMEDIATE;")
    metrics = run_stage_c_semantic_backfill(conn, now)
    conn.commit()

    # Metrics verification
    assert metrics["processed_claims"] >= 13
    assert metrics["inserted_mappings"] > 0
    assert metrics["inserted_properties"] > 0
    assert metrics["inserted_dosha_effects"] > 0
    assert metrics["inserted_plant_parts"] > 0
    assert metrics["inserted_preparations"] > 0

    # Verify Calibrated Mapping Rule in concept_claim_mappings (ADR Decision 4)
    mappings = conn.execute(
        "SELECT mapping_type, mapping_confidence, mapping_method, verification_status FROM concept_claim_mappings;"
    ).fetchall()
    assert len(mappings) > 0
    for m_type, m_conf, m_method, v_status in mappings:
        assert m_type == 'exact'
        assert m_conf is None, "Exact lexical mappings must retain NULL confidence!"
        assert m_method == 'lexicon_exact'
        assert v_status == 'unreviewed'

    # Verify Calibrated Mapping Rule in dosha_claim_assertions
    assertions = conn.execute(
        "SELECT mapping_confidence, mapping_method, verification_status FROM dosha_claim_assertions;"
    ).fetchall()
    assert len(assertions) >= 2  # Kapha + Vata
    for m_conf, m_method, v_status in assertions:
        assert m_conf is None, "Exact lexical mappings must retain NULL confidence!"
        assert m_method == 'lexicon_exact'
        assert v_status == 'unreviewed'

    # Verify relationship tables populated with 'active' status
    props = conn.execute("SELECT source_presence_status FROM herb_dravyaguna_properties;").fetchall()
    assert len(props) > 0
    for (p_status,) in props:
        assert p_status == 'active'

    doshas = conn.execute("SELECT source_presence_status FROM herb_dosha_effects;").fetchall()
    assert len(doshas) >= 2
    for (d_status,) in doshas:
        assert d_status == 'active'

    parts = conn.execute("SELECT source_presence_status FROM herb_plant_parts;").fetchall()
    assert len(parts) >= 2  # Leaf, Root
    for (pt_status,) in parts:
        assert pt_status == 'active'

    preps = conn.execute("SELECT source_presence_status FROM herb_preparations;").fetchall()
    assert len(preps) >= 2  # Churna, Guggulu
    for (pr_status,) in preps:
        assert pr_status == 'active'

    # Verify audit event in source_reconciliation_events
    audit_row = conn.execute(
        "SELECT event_type, extraction_status, is_complete_snapshot, initiated_by, notes FROM source_reconciliation_events WHERE source_id = ?;",
        (ids["source_id"],),
    ).fetchone()
    assert audit_row[0] == 'ingest_batch'
    assert audit_row[1] == 'completed'
    assert audit_row[2] == 1
    assert audit_row[3] == 'stage_c_backfill_engine'
    assert "[STAGE_C_BACKFILL]" in audit_row[4]


# ============================================================================
# 4. Idempotency Guarantee
# ============================================================================

def test_semantic_backfill_idempotency_guarantee(v2_db):
    """Running run_stage_c_semantic_backfill multiple times against the same database inserts 0 duplicate rows."""
    conn, _ = v2_db
    conn.execute("BEGIN IMMEDIATE;")
    _seed_stage_b_test_herb_and_claims(conn)
    conn.commit()

    migration_0003_semantic_dravyaguna.apply_migration(conn)
    now = '2025-01-01T12:00:00Z'

    # Run 1
    conn.execute("BEGIN IMMEDIATE;")
    metrics1 = run_stage_c_semantic_backfill(conn, now)
    conn.commit()
    assert metrics1["inserted_mappings"] > 0
    assert metrics1["inserted_properties"] > 0

    count_mappings_1 = conn.execute("SELECT COUNT(*) FROM concept_claim_mappings;").fetchone()[0]
    count_props_1 = conn.execute("SELECT COUNT(*) FROM herb_dravyaguna_properties;").fetchone()[0]
    count_dosha_1 = conn.execute("SELECT COUNT(*) FROM herb_dosha_effects;").fetchone()[0]
    count_parts_1 = conn.execute("SELECT COUNT(*) FROM herb_plant_parts;").fetchone()[0]
    count_preps_1 = conn.execute("SELECT COUNT(*) FROM herb_preparations;").fetchone()[0]

    # Run 2
    conn.execute("BEGIN IMMEDIATE;")
    metrics2 = run_stage_c_semantic_backfill(conn, now)
    conn.commit()

    # Second run must insert ZERO duplicate semantic rows
    assert metrics2["inserted_mappings"] == 0
    assert metrics2["inserted_properties"] == 0
    assert metrics2["inserted_dosha_effects"] == 0
    assert metrics2["inserted_plant_parts"] == 0
    assert metrics2["inserted_preparations"] == 0
    assert metrics2["inserted_indications"] == 0

    # Row counts must remain completely identical
    assert conn.execute("SELECT COUNT(*) FROM concept_claim_mappings;").fetchone()[0] == count_mappings_1
    assert conn.execute("SELECT COUNT(*) FROM herb_dravyaguna_properties;").fetchone()[0] == count_props_1
    assert conn.execute("SELECT COUNT(*) FROM herb_dosha_effects;").fetchone()[0] == count_dosha_1
    assert conn.execute("SELECT COUNT(*) FROM herb_plant_parts;").fetchone()[0] == count_parts_1
    assert conn.execute("SELECT COUNT(*) FROM herb_preparations;").fetchone()[0] == count_preps_1


# ============================================================================
# 5. Failure Rollback Safety
# ============================================================================

def test_semantic_backfill_rollback_safety_on_error(v2_db, monkeypatch):
    """An exception mid-backfill rolls back all Stage C inserts cleanly, leaving Stage B intact."""
    conn, _ = v2_db
    conn.execute("BEGIN IMMEDIATE;")
    _seed_stage_b_test_herb_and_claims(conn)
    conn.commit()

    migration_0003_semantic_dravyaguna.apply_migration(conn)
    before_snapshot = capture_stage_b_table_snapshot(conn)

    # Seed catalog so dravyaguna_concepts has clean baseline
    seed_canonical_concept_catalog(conn)
    c_count_before = conn.execute("SELECT COUNT(*) FROM concept_claim_mappings;").fetchone()[0]
    assert c_count_before == 0

    # Inject failure during backfill execution
    from herbal_almanac.backfill_engine import _decompose_dosha_expression
    def faulty_decompose(*args, **kwargs):
        raise RuntimeError("Simulated mid-backfill extraction failure!")

    monkeypatch.setattr("herbal_almanac.backfill_engine._decompose_dosha_expression", faulty_decompose)

    now = '2025-01-01T12:00:00Z'
    conn.execute("BEGIN IMMEDIATE;")
    with pytest.raises(RuntimeError, match="Simulated mid-backfill extraction failure!"):
        run_stage_c_semantic_backfill(conn, now)
    conn.rollback()

    # Verify Stage C tables remain completely clean (0 mappings, 0 properties)
    assert conn.execute("SELECT COUNT(*) FROM concept_claim_mappings;").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM herb_dravyaguna_properties;").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM herb_dosha_effects;").fetchone()[0] == 0

    # Verify Stage B tables remain 100% intact
    after_snapshot = capture_stage_b_table_snapshot(conn)
    verify_stage_b_row_invariance(before_snapshot, after_snapshot)


# ============================================================================
# 6. Full End-to-End Test on Copy of data/inspection.db
# ============================================================================

def test_end_to_end_backfill_on_inspection_db_copy(inspection_db_copy):
    """Executes full migration and semantic backfill on a disposable copy of data/inspection.db.

    Proves:
    1. Schema version 2 baseline invariance.
    2. Zero mutations to actual production Stage B data.
    3. Live claims correctly populate Stage C normalized semantic tables.
    4. 100% idempotency on actual scraped production data.
    """
    conn, copy_path = inspection_db_copy

    # 1. Baseline check
    versions_before = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY rowid ASC;").fetchall()]
    assert versions_before == [1, 2]
    assert validate_schema_migration_ledger(conn) == 2
    before_snapshot = capture_stage_b_table_snapshot(conn)

    # 2. Upgrade disposable copy to Schema Version 3
    migration_0003_semantic_dravyaguna.apply_migration(conn)
    versions_after = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY rowid ASC;").fetchall()]
    assert versions_after == [1, 2, 3]
    assert validate_schema_migration_ledger(conn) == 3

    # 3. Seed canonical catalog
    seed_canonical_concept_catalog(conn)

    # 4. Run semantic backfill
    now = '2025-01-01T12:00:00Z'
    conn.execute("BEGIN IMMEDIATE;")
    metrics1 = run_stage_c_semantic_backfill(conn, now)
    conn.commit()

    # Backfill must have processed genuine inspection.db claims
    assert metrics1["processed_claims"] > 0
    assert metrics1["inserted_mappings"] > 0
    assert metrics1["inserted_properties"] > 0
    assert metrics1["inserted_dosha_effects"] > 0
    assert metrics1["inserted_plant_parts"] > 0
    assert metrics1["inserted_preparations"] > 0

    # 5. Verify Stage B legacy invariance across all 13 tables
    after_snapshot = capture_stage_b_table_snapshot(conn)
    verify_stage_b_row_invariance(before_snapshot, after_snapshot)

    # 6. Verify idempotency on second run
    conn.execute("BEGIN IMMEDIATE;")
    metrics2 = run_stage_c_semantic_backfill(conn, now)
    conn.commit()

    assert metrics2["inserted_mappings"] == 0
    assert metrics2["inserted_properties"] == 0
    assert metrics2["inserted_dosha_effects"] == 0
    assert metrics2["inserted_plant_parts"] == 0
    assert metrics2["inserted_preparations"] == 0
    assert metrics2["inserted_indications"] == 0

    # Stage B tables still 100% invariant
    final_snapshot = capture_stage_b_table_snapshot(conn)
    verify_stage_b_row_invariance(before_snapshot, final_snapshot)
