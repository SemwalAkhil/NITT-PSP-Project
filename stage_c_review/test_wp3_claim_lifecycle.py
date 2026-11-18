"""
Herbal Almanac — Stage C.2 Work Package 3 (WP-3)
Unit Test Suite for Claim Lifecycle, Interpretation Review & Section-Level Omission Engine
"""

import os
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
import migration_0003_semantic_dravyaguna
from schema_capability_gate import FeatureUnavailableError
from claim_lifecycle import (
    transition_claim_status,
    adjudicate_claim_status_override,
    transition_interpretation_status,
    validate_calibrated_mapping_confidence,
    reconcile_section_omissions,
    _parse_inherited_tag,
    _strip_inherited_tag,
)


# ============================================================================
# Test Fixtures & Base Seed Helpers
# ============================================================================

@pytest.fixture
def v2_db():
    """Provides a fresh temporary SQLite database at schema version 2 ([1, 2])."""
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
def v3_db():
    """Provides a fresh temporary SQLite database upgraded to schema version 3 ([1, 2, 3])."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        almanac = AyurvedicAlmanac(db_path)
        almanac.create_database()
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        migration_0003_semantic_dravyaguna.apply_migration(conn)
        yield conn, db_path
        conn.close()
    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except OSError:
                pass


def _seed_base_evidence(conn: sqlite3.Connection) -> dict[str, int]:
    """Seeds base Herb, Source, Source Record, and Concepts for lifecycle testing."""
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

    # 3. Herb linked to source and record
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

    # 4. Canonical Concepts across domains
    cursor = conn.execute(
        "INSERT INTO dravyaguna_concepts (concept_code, concept_domain, status) VALUES ('RASA_KASHAYA', 'rasa', 'active');"
    )
    rasa_kashaya_id = cursor.lastrowid

    cursor = conn.execute(
        "INSERT INTO dravyaguna_concepts (concept_code, concept_domain, status) VALUES ('RASA_MADHURA', 'rasa', 'active');"
    )
    rasa_madhura_id = cursor.lastrowid

    cursor = conn.execute(
        "INSERT INTO dravyaguna_concepts (concept_code, concept_domain, status) VALUES ('GUNA_LAGHU', 'guna', 'active');"
    )
    guna_laghu_id = cursor.lastrowid

    cursor = conn.execute(
        "INSERT INTO dravyaguna_concepts (concept_code, concept_domain, status) VALUES ('DOSHA_VATA', 'dosha', 'active');"
    )
    dosha_vata_id = cursor.lastrowid

    cursor = conn.execute(
        "INSERT INTO dravyaguna_concepts (concept_code, concept_domain, status) VALUES ('DOSHA_PITTA', 'dosha', 'active');"
    )
    dosha_pitta_id = cursor.lastrowid

    cursor = conn.execute(
        "INSERT INTO dravyaguna_concepts (concept_code, concept_domain, status) VALUES ('EFFECT_DECREASE', 'dosha_effect', 'active');"
    )
    effect_dec_id = cursor.lastrowid

    cursor = conn.execute(
        "INSERT INTO dravyaguna_concepts (concept_code, concept_domain, status) VALUES ('EFFECT_INCREASE', 'dosha_effect', 'active');"
    )
    effect_inc_id = cursor.lastrowid

    return {
        "herb_id": herb_id,
        "source_id": source_id,
        "source_record_id": source_record_id,
        "rasa_kashaya_id": rasa_kashaya_id,
        "rasa_madhura_id": rasa_madhura_id,
        "guna_laghu_id": guna_laghu_id,
        "dosha_vata_id": dosha_vata_id,
        "dosha_pitta_id": dosha_pitta_id,
        "effect_dec_id": effect_dec_id,
        "effect_inc_id": effect_inc_id,
    }


# ============================================================================
# 1. Schema Version 2 & Transaction Contract Guards
# ============================================================================

def test_v2_database_capability_gating_raises_feature_unavailable(v2_db):
    """Calling any WP-3 helper on a v2 database raises FeatureUnavailableError."""
    conn, _ = v2_db
    conn.execute("BEGIN IMMEDIATE;")

    with pytest.raises(FeatureUnavailableError, match="Stage C normalized semantic features require schema version 3"):
        transition_claim_status(conn, 1, 'reviewed', '2025-01-01T00:00:00Z', 'curator_1')

    with pytest.raises(FeatureUnavailableError, match="Stage C normalized semantic features require schema version 3"):
        adjudicate_claim_status_override(
            conn, 1, 'unreviewed', 'curator_admin', 'Adjudicating override reason', '2025-01-01T00:00:00Z'
        )

    with pytest.raises(FeatureUnavailableError, match="Stage C normalized semantic features require schema version 3"):
        transition_interpretation_status(conn, 'concept_claim_mappings', 1, 'reviewed', '2025-01-01T00:00:00Z', 'curator_1')

    with pytest.raises(FeatureUnavailableError, match="Stage C normalized semantic features require schema version 3"):
        reconcile_section_omissions(
            conn,
            herb_id=1,
            source_id=1,
            event_id=1,
            section_domain='dravyaguna_properties',
            parsed_sections={'dravyaguna_properties': True},
            active_relationship_ids=set(),
            now='2025-01-01T00:00:00Z',
        )
    conn.rollback()


def test_transaction_contract_guard_requires_active_transaction(v3_db):
    """Calling any DB-touching WP-3 helper outside an active transaction raises RuntimeError."""
    conn, _ = v3_db
    now = '2025-01-01T00:00:00Z'
    assert not conn.in_transaction

    with pytest.raises(RuntimeError, match="Database connection must have an active transaction"):
        transition_claim_status(conn, 1, 'reviewed', now, 'curator_1')

    with pytest.raises(RuntimeError, match="Database connection must have an active transaction"):
        adjudicate_claim_status_override(
            conn, 1, 'unreviewed', 'curator_admin', 'Administrative override justification', now
        )

    with pytest.raises(RuntimeError, match="Database connection must have an active transaction"):
        transition_interpretation_status(conn, 'concept_claim_mappings', 1, 'reviewed', now, 'curator_1')

    with pytest.raises(RuntimeError, match="Database connection must have an active transaction"):
        reconcile_section_omissions(
            conn,
            herb_id=1,
            source_id=1,
            event_id=1,
            section_domain='dravyaguna_properties',
            parsed_sections={'dravyaguna_properties': True},
            active_relationship_ids=set(),
            now=now,
        )


def test_foreign_keys_pragmas_guard(v3_db):
    """Calling lifecycle helpers when PRAGMA foreign_keys is OFF raises RuntimeError."""
    conn, _ = v3_db
    conn.execute("PRAGMA foreign_keys = OFF;")
    conn.execute("BEGIN IMMEDIATE;")
    now = '2025-01-01T00:00:00Z'

    with pytest.raises(RuntimeError, match="Foreign key enforcement must be enabled"):
        transition_claim_status(conn, 1, 'reviewed', now, 'curator_1')

    conn.rollback()


# ============================================================================
# 2. Routine Claim Transitions & Matrix Enforcement
# ============================================================================

def test_routine_claim_transitions_happy_path(v3_db):
    """Verifies unreviewed -> reviewed -> verified happy path, non-destructive note appending, and audit logging."""
    conn, _ = v3_db
    now1 = '2025-01-01T10:00:00Z'
    now2 = '2025-01-01T11:00:00Z'

    conn.execute("BEGIN IMMEDIATE;")
    ids = _seed_base_evidence(conn)
    cursor = conn.execute(
        """
        INSERT INTO source_claims (source_record_id, claim_type, source_field, source_expression, language_code, normalization_method, verification_status, reviewer_notes, created_by_type, created_by, created_at, updated_at)
        VALUES (?, 'attribute', 'rasa', 'Kashaya', 'sa', 'exact', 'unreviewed', 'Initial ingest note', 'ingest', 'test_loader', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z');
        """,
        (ids["source_record_id"],),
    )
    claim_id = cursor.lastrowid
    conn.commit()

    # Step 1: Transition to reviewed
    conn.execute("BEGIN IMMEDIATE;")
    transition_claim_status(
        conn,
        source_claim_id=claim_id,
        new_status='reviewed',
        now=now1,
        reviewed_by='curator_ak',
        reviewer_notes='Confirmed Kashaya transcription from CCRAS table',
        herb_id=ids["herb_id"],
    )
    conn.commit()

    row = conn.execute(
        "SELECT verification_status, reviewed_by, reviewed_at, reviewer_notes FROM source_claims WHERE source_claim_id = ?",
        (claim_id,),
    ).fetchone()
    assert row[0] == 'reviewed'
    assert row[1] == 'curator_ak'
    assert row[2] == now1
    assert "Initial ingest note | Confirmed Kashaya transcription" in row[3]

    # No audit event required for routine reviewed transition
    event_count = conn.execute("SELECT COUNT(*) FROM source_reconciliation_events;").fetchone()[0]
    assert event_count == 0

    # Step 2: Transition to verified (requires authority_citation)
    conn.execute("BEGIN IMMEDIATE;")
    transition_claim_status(
        conn,
        source_claim_id=claim_id,
        new_status='verified',
        now=now2,
        reviewed_by='expert_curator',
        reviewer_notes='Pharmacopoeial concordance confirmed',
        authority_citation='AFI Part 1, Monograph 14, Haritaki',
        herb_id=ids["herb_id"],
    )
    conn.commit()

    row = conn.execute(
        "SELECT verification_status, reviewed_by, reviewed_at, reviewer_notes FROM source_claims WHERE source_claim_id = ?",
        (claim_id,),
    ).fetchone()
    assert row[0] == 'verified'
    assert row[1] == 'expert_curator'
    assert row[2] == now2
    assert "[AUTHORITY CITATION: AFI Part 1, Monograph 14, Haritaki] Pharmacopoeial concordance confirmed" in row[3]

    # Audit event created in source_reconciliation_events
    event_row = conn.execute(
        "SELECT event_type, snapshot_timestamp, notes, initiated_by FROM source_reconciliation_events WHERE source_id = ?",
        (ids["source_id"],),
    ).fetchone()
    assert event_row[0] == 'manual_adjudication'
    assert event_row[1] == now2
    assert f"[CLAIM_ID: {claim_id}]" in event_row[2]
    assert f"[HERB_ID: {ids['herb_id']}]" in event_row[2]
    assert "[ROUTINE_TRANSITION: reviewed -> verified]" in event_row[2]
    assert event_row[3] == 'expert_curator'


def test_routine_claim_idempotency_noop(v3_db):
    """Same-status transition is an idempotent no-op even without reviewer_by or authority_citation."""
    conn, _ = v3_db
    conn.execute("BEGIN IMMEDIATE;")
    ids = _seed_base_evidence(conn)
    cursor = conn.execute(
        """
        INSERT INTO source_claims (source_record_id, claim_type, source_field, source_expression, language_code, normalization_method, verification_status, reviewed_by, reviewed_at, reviewer_notes, created_by_type, created_by, created_at, updated_at)
        VALUES (?, 'attribute', 'rasa', 'Kashaya', 'sa', 'exact', 'verified', 'dr_sharma', '2025-01-01T00:00:00Z', '[AUTHORITY CITATION: CCRAS]', 'ingest', 'test_loader', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z');
        """,
        (ids["source_record_id"],),
    )
    claim_id = cursor.lastrowid
    conn.commit()

    # Call transition_claim_status with same status 'verified' without reviewer or citation
    conn.execute("BEGIN IMMEDIATE;")
    transition_claim_status(
        conn,
        source_claim_id=claim_id,
        new_status='verified',
        now='2025-01-02T12:00:00Z',
    )
    conn.commit()

    # Verify unchanged
    row = conn.execute("SELECT reviewed_at, reviewer_notes FROM source_claims WHERE source_claim_id = ?", (claim_id,)).fetchone()
    assert row[0] == '2025-01-01T00:00:00Z'
    assert row[1] == '[AUTHORITY CITATION: CCRAS]'


def test_routine_claim_validations_and_rejections(v3_db):
    """Validates rejection of missing reviewed_by, missing citation on verified, non-UTC timestamps, downgrades, and terminal reopening."""
    conn, _ = v3_db
    conn.execute("BEGIN IMMEDIATE;")
    ids = _seed_base_evidence(conn)
    cursor = conn.execute(
        """
        INSERT INTO source_claims (source_record_id, claim_type, source_field, source_expression, language_code, normalization_method, verification_status, created_by_type, created_by, created_at, updated_at)
        VALUES (?, 'attribute', 'rasa', 'Kashaya', 'sa', 'exact', 'unreviewed', 'ingest', 'test_loader', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z');
        """,
        (ids["source_record_id"],),
    )
    claim_id = cursor.lastrowid
    conn.commit()

    conn.execute("BEGIN IMMEDIATE;")
    # Non-UTC timestamp rejection
    with pytest.raises(ValueError, match="UTC offset"):
        transition_claim_status(conn, claim_id, 'reviewed', '2025-01-01 10:00:00', 'curator_1')

    # Missing reviewed_by on reviewed
    with pytest.raises(ValueError, match="requires a non-empty reviewed_by"):
        transition_claim_status(conn, claim_id, 'reviewed', '2025-01-01T00:00:00Z', reviewed_by=None)

    # Missing authority_citation on verified
    with pytest.raises(ValueError, match="strictly requires an explicit authority_citation"):
        transition_claim_status(conn, claim_id, 'verified', '2025-01-01T00:00:00Z', reviewed_by='curator_1', authority_citation=None)

    # Too short authority_citation (< 5 chars)
    with pytest.raises(ValueError, match="strictly requires an explicit authority_citation"):
        transition_claim_status(conn, claim_id, 'verified', '2025-01-01T00:00:00Z', reviewed_by='curator_1', authority_citation='AFI')

    conn.rollback()

    # Promote to reviewed
    conn.execute("BEGIN IMMEDIATE;")
    transition_claim_status(conn, claim_id, 'reviewed', '2025-01-01T00:00:00Z', 'curator_1')
    conn.commit()

    conn.execute("BEGIN IMMEDIATE;")
    # Routine downgrade: reviewed -> unreviewed
    with pytest.raises(ValueError, match="Status downgrade from 'reviewed' to 'unreviewed'"):
        transition_claim_status(conn, claim_id, 'unreviewed', '2025-01-01T00:00:00Z')

    # Promote to verified
    transition_claim_status(conn, claim_id, 'verified', '2025-01-01T00:00:00Z', 'curator_1', authority_citation='CCRAS Dravya Vol 1')
    conn.commit()

    conn.execute("BEGIN IMMEDIATE;")
    # Routine downgrade: verified -> reviewed
    with pytest.raises(ValueError, match="Status downgrade from 'verified' to 'reviewed'"):
        transition_claim_status(conn, claim_id, 'reviewed', '2025-01-01T00:00:00Z')

    # Routine downgrade: verified -> unreviewed
    with pytest.raises(ValueError, match="Status downgrade from 'verified' to 'unreviewed'"):
        transition_claim_status(conn, claim_id, 'unreviewed', '2025-01-01T00:00:00Z')

    # Routine terminal transition to rejected
    transition_claim_status(conn, claim_id, 'rejected', '2025-01-01T00:00:00Z', reviewer_notes='Invalid reading')
    conn.commit()

    conn.execute("BEGIN IMMEDIATE;")
    # Rejection of routine terminal reopening: rejected -> reviewed
    with pytest.raises(ValueError, match="Cannot transition terminal claim .* to 'reviewed' in routine pipelines"):
        transition_claim_status(conn, claim_id, 'reviewed', '2025-01-01T00:00:00Z', reviewed_by='curator_1')

    conn.rollback()


# ============================================================================
# 3. Trigger-Order Hazard Defense & Selective Reopening
# ============================================================================

def test_trigger_order_hazard_defense_and_selective_reopening(v3_db):
    """Comprehensive test of trg_cascade_claim_supersession defense, lineage tagging, reclassification, and selective reopening.

    Setup:
    - Claim C1 with 3 child mappings:
      - M1: unreviewed
      - M2: verified
      - M3: independently rejected (without inherited tag)
    - 2 child Dosha assertions:
      - A1: reviewed
      - A2: independently rejected (without inherited tag)
    """
    conn, _ = v3_db
    conn.execute("BEGIN IMMEDIATE;")
    ids = _seed_base_evidence(conn)

    # 1. Parent claim C1 (initially unreviewed)
    cursor = conn.execute(
        """
        INSERT INTO source_claims (source_record_id, claim_type, source_field, source_expression, language_code, normalization_method, verification_status, created_by_type, created_by, created_at, updated_at)
        VALUES (?, 'composite', 'dravyaguna_profile', 'Haritaki properties', 'sa', 'exact', 'unreviewed', 'ingest', 'test_loader', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z');
        """,
        (ids["source_record_id"],),
    )
    claim_id = cursor.lastrowid

    # 2. Child mappings M1, M2, M3
    # M1: unreviewed
    c_m1 = conn.execute(
        """
        INSERT INTO concept_claim_mappings (source_claim_id, concept_id, mapping_type, mapping_method, verification_status)
        VALUES (?, ?, 'exact', 'lexicon_exact', 'unreviewed');
        """,
        (claim_id, ids["rasa_kashaya_id"]),
    )
    m1_id = c_m1.lastrowid

    # M2: verified
    c_m2 = conn.execute(
        """
        INSERT INTO concept_claim_mappings (source_claim_id, concept_id, mapping_type, mapping_method, verification_status, reviewed_by, reviewed_at, reviewer_notes)
        VALUES (?, ?, 'exact', 'human_expert', 'verified', 'dr_ayush', '2025-01-01T00:00:00Z', '[CITATION: Bhavaprakasha]');
        """,
        (claim_id, ids["rasa_madhura_id"]),
    )
    m2_id = c_m2.lastrowid

    # M3: independently rejected
    c_m3 = conn.execute(
        """
        INSERT INTO concept_claim_mappings (source_claim_id, concept_id, mapping_type, mapping_method, verification_status, reviewed_by, reviewed_at, reviewer_notes)
        VALUES (?, ?, 'exact', 'heuristic', 'rejected', 'validator_bot', '2025-01-01T00:00:00Z', 'Heuristic false positive');
        """,
        (claim_id, ids["guna_laghu_id"]),
    )
    m3_id = c_m3.lastrowid

    # 3. Child Dosha assertions A1, A2
    # A1: reviewed
    c_a1 = conn.execute(
        """
        INSERT INTO dosha_claim_assertions (source_claim_id, dosha_concept_id, effect_concept_id, mapping_method, verification_status, reviewed_by, reviewed_at, reviewer_notes)
        VALUES (?, ?, ?, 'rule_normalizer', 'reviewed', 'dr_ayush', '2025-01-01T00:00:00Z', 'Pacifies Vata');
        """,
        (claim_id, ids["dosha_vata_id"], ids["effect_dec_id"]),
    )
    a1_id = c_a1.lastrowid

    # A2: independently rejected
    c_a2 = conn.execute(
        """
        INSERT INTO dosha_claim_assertions (source_claim_id, dosha_concept_id, effect_concept_id, mapping_method, verification_status, reviewed_by, reviewed_at, reviewer_notes)
        VALUES (?, ?, ?, 'rule_normalizer', 'rejected', 'validator_bot', '2025-01-01T00:00:00Z', 'Incorrect dosha increase');
        """,
        (claim_id, ids["dosha_pitta_id"], ids["effect_inc_id"]),
    )
    a2_id = c_a2.lastrowid

    conn.commit()

    # Step A: Transition parent claim to 'superseded' via transition_claim_status()
    now_sup = '2025-01-02T10:00:00Z'
    conn.execute("BEGIN IMMEDIATE;")
    transition_claim_status(
        conn,
        source_claim_id=claim_id,
        new_status='superseded',
        now=now_sup,
        reviewed_by='ingest_pipeline',
        reviewer_notes='Newer monograph snapshot received',
        herb_id=ids["herb_id"],
    )
    conn.commit()

    # Check parent claim is superseded
    parent_status = conn.execute("SELECT verification_status FROM source_claims WHERE source_claim_id = ?", (claim_id,)).fetchone()[0]
    assert parent_status == 'superseded'

    # Check M3 and A2 remain independently rejected (without inherited tag)
    m3_row = conn.execute("SELECT verification_status, reviewer_notes FROM concept_claim_mappings WHERE mapping_id = ?", (m3_id,)).fetchone()
    assert m3_row[0] == 'rejected'
    assert _parse_inherited_tag(m3_row[1], claim_id) is None
    assert m3_row[1] == 'Heuristic false positive'

    a2_row = conn.execute("SELECT verification_status, reviewer_notes FROM dosha_claim_assertions WHERE dosha_assertion_id = ?", (a2_id,)).fetchone()
    assert a2_row[0] == 'rejected'
    assert _parse_inherited_tag(a2_row[1], claim_id) is None
    assert a2_row[1] == 'Incorrect dosha increase'

    # Check M1, M2, A1 became superseded and carry [INHERITED_FROM_CLAIM:{claim_id}:PRIOR=...]
    m1_row = conn.execute("SELECT verification_status, reviewer_notes FROM concept_claim_mappings WHERE mapping_id = ?", (m1_id,)).fetchone()
    assert m1_row[0] == 'superseded'
    assert _parse_inherited_tag(m1_row[1], claim_id) == 'unreviewed'

    m2_row = conn.execute("SELECT verification_status, reviewer_notes FROM concept_claim_mappings WHERE mapping_id = ?", (m2_id,)).fetchone()
    assert m2_row[0] == 'superseded'
    assert _parse_inherited_tag(m2_row[1], claim_id) == 'verified'
    assert '[CITATION: Bhavaprakasha]' in m2_row[1]

    a1_row = conn.execute("SELECT verification_status, reviewer_notes FROM dosha_claim_assertions WHERE dosha_assertion_id = ?", (a1_id,)).fetchone()
    assert a1_row[0] == 'superseded'
    assert _parse_inherited_tag(a1_row[1], claim_id) == 'reviewed'
    assert 'Pacifies Vata' in a1_row[1]

    # Step B: Reclassify parent claim from 'superseded' to 'rejected' via adjudicate_claim_status_override()
    now_rej = '2025-01-03T11:00:00Z'
    conn.execute("BEGIN IMMEDIATE;")
    adjudicate_claim_status_override(
        conn,
        source_claim_id=claim_id,
        new_status='rejected',
        now=now_rej,
        authorized_curator_id='curator_chief',
        adjudication_reason='Source record confirmed corrupt and factually erroneous',
        herb_id=ids["herb_id"],
    )
    conn.commit()

    parent_status = conn.execute("SELECT verification_status FROM source_claims WHERE source_claim_id = ?", (claim_id,)).fetchone()[0]
    assert parent_status == 'rejected'

    # Verify M1, M2, A1 became 'rejected' while preserving their original PRIOR tags
    m1_row = conn.execute("SELECT verification_status, reviewer_notes FROM concept_claim_mappings WHERE mapping_id = ?", (m1_id,)).fetchone()
    assert m1_row[0] == 'rejected'
    assert _parse_inherited_tag(m1_row[1], claim_id) == 'unreviewed'

    m2_row = conn.execute("SELECT verification_status, reviewer_notes FROM concept_claim_mappings WHERE mapping_id = ?", (m2_id,)).fetchone()
    assert m2_row[0] == 'rejected'
    assert _parse_inherited_tag(m2_row[1], claim_id) == 'verified'

    a1_row = conn.execute("SELECT verification_status, reviewer_notes FROM dosha_claim_assertions WHERE dosha_assertion_id = ?", (a1_id,)).fetchone()
    assert a1_row[0] == 'rejected'
    assert _parse_inherited_tag(a1_row[1], claim_id) == 'reviewed'

    # M3 and A2 still remain independently rejected
    assert conn.execute("SELECT verification_status FROM concept_claim_mappings WHERE mapping_id = ?", (m3_id,)).fetchone()[0] == 'rejected'
    assert conn.execute("SELECT verification_status FROM dosha_claim_assertions WHERE dosha_assertion_id = ?", (a2_id,)).fetchone()[0] == 'rejected'

    # Step C: Reopen parent claim from 'rejected' to 'verified' via adjudicate_claim_status_override()
    now_reopen = '2025-01-04T12:00:00Z'
    conn.execute("BEGIN IMMEDIATE;")
    adjudicate_claim_status_override(
        conn,
        source_claim_id=claim_id,
        new_status='verified',
        now=now_reopen,
        authorized_curator_id='curator_chief',
        adjudication_reason='Adjudicated classical authenticity re-established by CCRAS committee',
        authority_citation='CCRAS Statutory Pharmacopoeia Vol 2, p. 88',
        herb_id=ids["herb_id"],
    )
    conn.commit()

    # Verify parent is verified
    parent_status = conn.execute("SELECT verification_status FROM source_claims WHERE source_claim_id = ?", (claim_id,)).fetchone()[0]
    assert parent_status == 'verified'

    # 1. M3 and A2 MUST remain 'rejected' (never revived!)
    m3_final = conn.execute("SELECT verification_status, reviewer_notes FROM concept_claim_mappings WHERE mapping_id = ?", (m3_id,)).fetchone()
    assert m3_final[0] == 'rejected'
    assert m3_final[1] == 'Heuristic false positive'

    a2_final = conn.execute("SELECT verification_status, reviewer_notes FROM dosha_claim_assertions WHERE dosha_assertion_id = ?", (a2_id,)).fetchone()
    assert a2_final[0] == 'rejected'
    assert a2_final[1] == 'Incorrect dosha increase'

    # 2. M1 (whose PRIOR was 'unreviewed') MUST be restored to 'unreviewed' (never auto-promoted to 'reviewed'!)
    m1_final = conn.execute("SELECT verification_status, reviewer_notes FROM concept_claim_mappings WHERE mapping_id = ?", (m1_id,)).fetchone()
    assert m1_final[0] == 'unreviewed'
    assert _parse_inherited_tag(m1_final[1], claim_id) is None

    # 3. M2 (PRIOR=verified) MUST be restored to 'reviewed' (NEVER auto-verified) and clean notes
    m2_final = conn.execute("SELECT verification_status, reviewer_notes FROM concept_claim_mappings WHERE mapping_id = ?", (m2_id,)).fetchone()
    assert m2_final[0] == 'reviewed'
    assert _parse_inherited_tag(m2_final[1], claim_id) is None
    assert m2_final[1] == '[CITATION: Bhavaprakasha]'

    # 4. A1 (PRIOR=reviewed) MUST be restored to 'reviewed' and clean notes
    a1_final = conn.execute("SELECT verification_status, reviewer_notes FROM dosha_claim_assertions WHERE dosha_assertion_id = ?", (a1_id,)).fetchone()
    assert a1_final[0] == 'reviewed'
    assert _parse_inherited_tag(a1_final[1], claim_id) is None
    assert a1_final[1] == 'Pacifies Vata'


# ============================================================================
# 4. Independent Child Interpretation Review Helper
# ============================================================================

def test_independent_child_interpretation_review(v3_db):
    """Verifies child review constraints against parent claim status and promotion to reviewed/verified."""
    conn, _ = v3_db
    conn.execute("BEGIN IMMEDIATE;")
    ids = _seed_base_evidence(conn)

    # 1. Parent claim unreviewed
    c_claim = conn.execute(
        """
        INSERT INTO source_claims (source_record_id, claim_type, source_field, source_expression, language_code, normalization_method, verification_status, created_by_type, created_by, created_at, updated_at)
        VALUES (?, 'attribute', 'rasa', 'Kashaya', 'sa', 'exact', 'unreviewed', 'ingest', 'test_loader', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z');
        """,
        (ids["source_record_id"],),
    )
    claim_id = c_claim.lastrowid

    # 2. Child mapping unreviewed
    c_map = conn.execute(
        """
        INSERT INTO concept_claim_mappings (source_claim_id, concept_id, mapping_type, mapping_method, verification_status)
        VALUES (?, ?, 'exact', 'lexicon_exact', 'unreviewed');
        """,
        (claim_id, ids["rasa_kashaya_id"]),
    )
    mapping_id = c_map.lastrowid

    # 3. Child assertion unreviewed
    c_asst = conn.execute(
        """
        INSERT INTO dosha_claim_assertions (source_claim_id, dosha_concept_id, effect_concept_id, mapping_method, verification_status)
        VALUES (?, ?, ?, 'rule_normalizer', 'unreviewed');
        """,
        (claim_id, ids["dosha_vata_id"], ids["effect_dec_id"]),
    )
    assertion_id = c_asst.lastrowid
    conn.commit()

    now = '2025-01-01T12:00:00Z'
    conn.execute("BEGIN IMMEDIATE;")
    # Parent is unreviewed -> child promotion to reviewed or verified is blocked
    with pytest.raises(ValueError, match="is in status 'unreviewed'. Parent must be 'reviewed' or 'verified'"):
        transition_interpretation_status(conn, 'concept_claim_mappings', mapping_id, 'reviewed', now, reviewed_by='curator_1')

    with pytest.raises(ValueError, match="is in status 'unreviewed'. Parent must be 'reviewed' or 'verified'"):
        transition_interpretation_status(conn, 'dosha_claim_assertions', assertion_id, 'verified', now, reviewed_by='curator_1', authority_citation='AFI 1.1')

    # Promoting parent claim to reviewed
    transition_claim_status(conn, claim_id, 'reviewed', now, reviewed_by='curator_1')
    conn.commit()

    # Now child promotion to reviewed succeeds
    conn.execute("BEGIN IMMEDIATE;")
    transition_interpretation_status(
        conn,
        table_name='concept_claim_mappings',
        record_id=mapping_id,
        new_status='reviewed',
        now=now,
        reviewed_by='curator_2',
        reviewer_notes='Confirmed Kashaya mapping',
        herb_id=ids["herb_id"],
    )
    conn.commit()

    m_row = conn.execute("SELECT verification_status, reviewed_by, reviewer_notes FROM concept_claim_mappings WHERE mapping_id = ?", (mapping_id,)).fetchone()
    assert m_row[0] == 'reviewed'
    assert m_row[1] == 'curator_2'
    assert m_row[2] == 'Confirmed Kashaya mapping'

    # Now promote child mapping to verified with citation
    conn.execute("BEGIN IMMEDIATE;")
    transition_interpretation_status(
        conn,
        table_name='concept_claim_mappings',
        record_id=mapping_id,
        new_status='verified',
        now=now,
        reviewed_by='expert_1',
        reviewer_notes='Treatise citation verified',
        authority_citation='Caraka Samhita Sutrasthana 26.40',
        herb_id=ids["herb_id"],
    )
    conn.commit()

    m_row = conn.execute("SELECT verification_status, reviewer_notes FROM concept_claim_mappings WHERE mapping_id = ?", (mapping_id,)).fetchone()
    assert m_row[0] == 'verified'
    assert "[CITATION: Caraka Samhita Sutrasthana 26.40] Treatise citation verified" in m_row[1]

    # Verify audit event in source_reconciliation_events
    ev = conn.execute(
        "SELECT event_type, notes FROM source_reconciliation_events WHERE notes LIKE '%[CHILD_TABLE: concept_claim_mappings]%';"
    ).fetchone()
    assert ev[0] == 'manual_adjudication'
    assert f"[CLAIM_ID: {claim_id}]" in ev[1]
    assert f"[CHILD_ID: {mapping_id}]" in ev[1]


# ============================================================================
# 5. Calibrated Mapping Confidence Enforcer
# ============================================================================

def test_calibrated_mapping_confidence_validation():
    """Validates calibrated mapping confidence rules per ADR Decision 4 (Section 5)."""
    # 1. lexicon_exact strictly requires mapping_confidence = None
    validate_calibrated_mapping_confidence('lexicon_exact', None)  # passes

    with pytest.raises(ValueError, match="strictly requires mapping_confidence=None"):
        validate_calibrated_mapping_confidence('lexicon_exact', 1.0)

    with pytest.raises(ValueError, match="strictly requires mapping_confidence=None"):
        validate_calibrated_mapping_confidence('lexicon_exact', 0.95)

    with pytest.raises(ValueError, match="strictly requires mapping_confidence=None"):
        validate_calibrated_mapping_confidence('lexicon_exact', 0.0)

    # 2. Probabilistic / fuzzy / normalizer methods
    validate_calibrated_mapping_confidence('rule_normalizer', 0.85)
    validate_calibrated_mapping_confidence('human_expert', 1.0)
    validate_calibrated_mapping_confidence('heuristic', 0.5)
    validate_calibrated_mapping_confidence('rule_normalizer', None)

    # Out of range values
    with pytest.raises(ValueError, match="out of range"):
        validate_calibrated_mapping_confidence('rule_normalizer', -0.1)

    with pytest.raises(ValueError, match="out of range"):
        validate_calibrated_mapping_confidence('heuristic', 1.2)

    # Invalid method name
    with pytest.raises(ValueError, match="Unknown mapping_method"):
        validate_calibrated_mapping_confidence('machine_ai_model', 0.8)


# ============================================================================
# 6. Section-Level Omission Detection Engine
# ============================================================================

def test_section_level_omission_engine(v3_db):
    """Verifies omission engine behavior under complete snapshots vs partial/skipped snapshots."""
    conn, _ = v3_db
    conn.execute("BEGIN IMMEDIATE;")
    ids = _seed_base_evidence(conn)

    # 1. Create a claim, mapping, and active relationship for dravyaguna_properties
    cursor = conn.execute(
        """
        INSERT INTO source_claims (source_record_id, claim_type, source_field, source_expression, language_code, normalization_method, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at)
        VALUES (?, 'attribute', 'rasa', 'Kashaya', 'sa', 'exact', 'reviewed', 'curator_1', '2025-01-01T00:00:00Z', 'ingest', 'test_loader', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z');
        """,
        (ids["source_record_id"],),
    )
    claim_id = cursor.lastrowid

    c_map = conn.execute(
        """
        INSERT INTO concept_claim_mappings (source_claim_id, concept_id, mapping_type, mapping_method, verification_status)
        VALUES (?, ?, 'exact', 'lexicon_exact', 'reviewed');
        """,
        (claim_id, ids["rasa_kashaya_id"]),
    )
    mapping_id = c_map.lastrowid

    # Active relationship in herb_dravyaguna_properties
    c_prop = conn.execute(
        """
        INSERT INTO herb_dravyaguna_properties (herb_id, mapping_id, source_presence_status)
        VALUES (?, ?, 'active');
        """,
        (ids["herb_id"], mapping_id),
    )
    prop_id = c_prop.lastrowid

    # 2. Create an incomplete snapshot reconciliation event
    c_ev_incomp = conn.execute(
        """
        INSERT INTO source_reconciliation_events (source_id, event_type, snapshot_timestamp, extraction_status, is_complete_snapshot, initiated_by)
        VALUES (?, 'snapshot_reconciliation', '2025-01-01T00:00:00Z', 'in_progress', 0, 'crawler_batch');
        """,
        (ids["source_id"],),
    )
    incomp_event_id = c_ev_incomp.lastrowid

    # 3. Create a complete snapshot reconciliation event
    c_ev_comp = conn.execute(
        """
        INSERT INTO source_reconciliation_events (source_id, event_type, snapshot_timestamp, extraction_status, is_complete_snapshot, initiated_by)
        VALUES (?, 'snapshot_reconciliation', '2025-01-02T00:00:00Z', 'completed', 1, 'crawler_batch');
        """,
        (ids["source_id"],),
    )
    comp_event_id = c_ev_comp.lastrowid
    conn.commit()

    now = '2025-01-02T12:00:00Z'

    # Case A: Incomplete event -> Completeness gate skips flagging
    conn.execute("BEGIN IMMEDIATE;")
    res = reconcile_section_omissions(
        conn,
        herb_id=ids["herb_id"],
        source_id=ids["source_id"],
        event_id=incomp_event_id,
        section_domain='dravyaguna_properties',
        parsed_sections={'dravyaguna_properties': True},
        active_relationship_ids=set(),  # prop_id is omitted from active IDs
        now=now,
    )
    conn.commit()
    assert res == {"flagged_candidate_omissions": 0, "skipped_incomplete": 1}

    # Relationship remains active
    status = conn.execute("SELECT source_presence_status FROM herb_dravyaguna_properties WHERE herb_property_id = ?", (prop_id,)).fetchone()[0]
    assert status == 'active'

    # Case B: Complete event BUT parsed_sections['dravyaguna_properties'] is False -> Skips flagging
    conn.execute("BEGIN IMMEDIATE;")
    res = reconcile_section_omissions(
        conn,
        herb_id=ids["herb_id"],
        source_id=ids["source_id"],
        event_id=comp_event_id,
        section_domain='dravyaguna_properties',
        parsed_sections={'dravyaguna_properties': False},
        active_relationship_ids=set(),
        now=now,
    )
    conn.commit()
    assert res == {"flagged_candidate_omissions": 0, "skipped_incomplete": 1}
    assert conn.execute("SELECT source_presence_status FROM herb_dravyaguna_properties WHERE herb_property_id = ?", (prop_id,)).fetchone()[0] == 'active'

    # Case C: Complete event AND parsed_sections is True AND prop_id is attested in active_relationship_ids -> Stays active
    conn.execute("BEGIN IMMEDIATE;")
    res = reconcile_section_omissions(
        conn,
        herb_id=ids["herb_id"],
        source_id=ids["source_id"],
        event_id=comp_event_id,
        section_domain='dravyaguna_properties',
        parsed_sections={'dravyaguna_properties': True},
        active_relationship_ids={prop_id},
        now=now,
    )
    conn.commit()
    assert res == {"flagged_candidate_omissions": 0, "skipped_incomplete": 0}
    assert conn.execute("SELECT source_presence_status FROM herb_dravyaguna_properties WHERE herb_property_id = ?", (prop_id,)).fetchone()[0] == 'active'

    # Case D: Complete event AND parsed_sections is True AND prop_id is MISSING from active_relationship_ids -> Transitions to candidate_omission
    conn.execute("BEGIN IMMEDIATE;")
    res = reconcile_section_omissions(
        conn,
        herb_id=ids["herb_id"],
        source_id=ids["source_id"],
        event_id=comp_event_id,
        section_domain='dravyaguna_properties',
        parsed_sections={'dravyaguna_properties': True},
        active_relationship_ids=set(),  # empty set -> prop_id is omitted
        now=now,
    )
    conn.commit()
    assert res == {"flagged_candidate_omissions": 1, "skipped_incomplete": 0}

    # Relationship is now candidate_omission
    status = conn.execute("SELECT source_presence_status FROM herb_dravyaguna_properties WHERE herb_property_id = ?", (prop_id,)).fetchone()[0]
    assert status == 'candidate_omission'

    # omissions_flagged on event was incremented
    flagged = conn.execute("SELECT omissions_flagged FROM source_reconciliation_events WHERE event_id = ?", (comp_event_id,)).fetchone()[0]
    assert flagged == 1


# ============================================================================
# 7. Additional Granular Tests: Admin Downgrades, Edge Cases, & Other Domains
# ============================================================================

def test_admin_override_downgrades_and_validations(v3_db):
    """Verifies administrative status downgrades (reviewed->unreviewed, verified->reviewed/unreviewed) and validation guards."""
    conn, _ = v3_db
    conn.execute("BEGIN IMMEDIATE;")
    ids = _seed_base_evidence(conn)
    cursor = conn.execute(
        """
        INSERT INTO source_claims (source_record_id, claim_type, source_field, source_expression, language_code, normalization_method, verification_status, created_by_type, created_by, created_at, updated_at)
        VALUES (?, 'attribute', 'rasa', 'Kashaya', 'sa', 'exact', 'unreviewed', 'ingest', 'test_loader', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z');
        """,
        (ids["source_record_id"],),
    )
    claim_id = cursor.lastrowid
    now = '2025-01-01T12:00:00Z'

    # Promote to reviewed via routine
    transition_claim_status(conn, claim_id, 'reviewed', now, reviewed_by='curator_1')
    conn.commit()

    conn.execute("BEGIN IMMEDIATE;")
    # Validation guard: curator_id empty
    with pytest.raises(ValueError, match="requires a non-empty authorized_curator_id"):
        adjudicate_claim_status_override(conn, claim_id, 'unreviewed', '  ', 'Valid reason 12345', now)

    # Validation guard: reason too short
    with pytest.raises(ValueError, match="requires a substantial adjudication_reason"):
        adjudicate_claim_status_override(conn, claim_id, 'unreviewed', 'curator_admin', 'short', now)

    # Successful downgrade: reviewed -> unreviewed
    adjudicate_claim_status_override(
        conn, claim_id, 'unreviewed', 'curator_admin', 'Manual review found ambiguous reading, rolling back', now
    )
    conn.commit()

    row = conn.execute("SELECT verification_status, reviewer_notes FROM source_claims WHERE source_claim_id = ?", (claim_id,)).fetchone()
    assert row[0] == 'unreviewed'
    assert "[ADMIN OVERRIDE: reviewed -> unreviewed]" in row[1]

    # Promote to verified
    conn.execute("BEGIN IMMEDIATE;")
    transition_claim_status(conn, claim_id, 'reviewed', now, reviewed_by='curator_1')
    transition_claim_status(conn, claim_id, 'verified', now, reviewed_by='curator_1', authority_citation='CCRAS Dravya Vol 1')
    conn.commit()

    # Admin downgrade: verified -> reviewed
    conn.execute("BEGIN IMMEDIATE;")
    adjudicate_claim_status_override(
        conn, claim_id, 'reviewed', 'curator_admin', 'Treatise citation questioned, downgrading to reviewed', now
    )
    conn.commit()
    assert conn.execute("SELECT verification_status FROM source_claims WHERE source_claim_id = ?", (claim_id,)).fetchone()[0] == 'reviewed'

    # Admin downgrade: reviewed -> unreviewed
    conn.execute("BEGIN IMMEDIATE;")
    adjudicate_claim_status_override(
        conn, claim_id, 'unreviewed', 'curator_admin', 'Further inquiry required, reverting to unreviewed', now
    )
    conn.commit()
    assert conn.execute("SELECT verification_status FROM source_claims WHERE source_claim_id = ?", (claim_id,)).fetchone()[0] == 'unreviewed'


def test_child_interpretation_independent_terminal_strips_tag(v3_db):
    """When an inheriting child is independently rejected or superseded, any inherited lineage tag is cleanly stripped."""
    conn, _ = v3_db
    conn.execute("BEGIN IMMEDIATE;")
    ids = _seed_base_evidence(conn)
    cursor = conn.execute(
        """
        INSERT INTO source_claims (source_record_id, claim_type, source_field, source_expression, language_code, normalization_method, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at)
        VALUES (?, 'composite', 'dravyaguna_profile', 'Haritaki', 'sa', 'exact', 'reviewed', 'curator_1', '2025-01-01T00:00:00Z', 'ingest', 'test_loader', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z');
        """,
        (ids["source_record_id"],),
    )
    claim_id = cursor.lastrowid

    # Create child with existing inherited tag
    c_map = conn.execute(
        """
        INSERT INTO concept_claim_mappings (source_claim_id, concept_id, mapping_type, mapping_method, verification_status, reviewer_notes)
        VALUES (?, ?, 'exact', 'lexicon_exact', 'superseded', '[INHERITED_FROM_CLAIM:1:PRIOR=reviewed] Original mapping notes');
        """,
        (claim_id, ids["rasa_kashaya_id"]),
    )
    map_id = c_map.lastrowid
    conn.commit()

    # Independently reject child via transition_interpretation_status
    now = '2025-01-02T12:00:00Z'
    conn.execute("BEGIN IMMEDIATE;")
    transition_interpretation_status(
        conn,
        table_name='concept_claim_mappings',
        record_id=map_id,
        new_status='rejected',
        now=now,
        reviewed_by='curator_independent',
        reviewer_notes='Confirmed textual misattribution',
    )
    conn.commit()

    row = conn.execute("SELECT verification_status, reviewer_notes FROM concept_claim_mappings WHERE mapping_id = ?", (map_id,)).fetchone()
    assert row[0] == 'rejected'
    # Tag MUST be stripped!
    assert _parse_inherited_tag(row[1], claim_id) is None
    assert 'Confirmed textual misattribution' in row[1]


def test_omission_engine_dosha_effects_and_validation_errors(v3_db):
    """Tests omission engine on dosha_effects domain, and verifies error handling on missing/invalid arguments."""
    conn, _ = v3_db
    conn.execute("BEGIN IMMEDIATE;")
    ids = _seed_base_evidence(conn)

    cursor = conn.execute(
        """
        INSERT INTO source_claims (source_record_id, claim_type, source_field, source_expression, language_code, normalization_method, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at)
        VALUES (?, 'attribute', 'dosha', 'Vatashamana', 'sa', 'exact', 'reviewed', 'curator_1', '2025-01-01T00:00:00Z', 'ingest', 'test_loader', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z');
        """,
        (ids["source_record_id"],),
    )
    claim_id = cursor.lastrowid

    c_asst = conn.execute(
        """
        INSERT INTO dosha_claim_assertions (source_claim_id, dosha_concept_id, effect_concept_id, mapping_method, verification_status)
        VALUES (?, ?, ?, 'rule_normalizer', 'reviewed');
        """,
        (claim_id, ids["dosha_vata_id"], ids["effect_dec_id"]),
    )
    asst_id = c_asst.lastrowid

    # Active relationship in herb_dosha_effects
    c_eff = conn.execute(
        """
        INSERT INTO herb_dosha_effects (herb_id, dosha_assertion_id, source_presence_status)
        VALUES (?, ?, 'active');
        """,
        (ids["herb_id"], asst_id),
    )
    eff_id = c_eff.lastrowid

    c_ev = conn.execute(
        """
        INSERT INTO source_reconciliation_events (source_id, event_type, snapshot_timestamp, extraction_status, is_complete_snapshot, initiated_by)
        VALUES (?, 'snapshot_reconciliation', '2025-01-02T00:00:00Z', 'completed', 1, 'batch_worker');
        """,
        (ids["source_id"],),
    )
    event_id = c_ev.lastrowid
    conn.commit()

    now = '2025-01-02T12:00:00Z'
    conn.execute("BEGIN IMMEDIATE;")
    # Unknown section_domain raises ValueError
    with pytest.raises(ValueError, match="Unknown section_domain"):
        reconcile_section_omissions(
            conn,
            herb_id=ids["herb_id"],
            source_id=ids["source_id"],
            event_id=event_id,
            section_domain='nonexistent_domain',
            parsed_sections={'nonexistent_domain': True},
            active_relationship_ids=set(),
            now=now,
        )

    # Missing event_id raises KeyError
    with pytest.raises(KeyError, match="Reconciliation event 99999 not found"):
        reconcile_section_omissions(
            conn,
            herb_id=ids["herb_id"],
            source_id=ids["source_id"],
            event_id=99999,
            section_domain='dosha_effects',
            parsed_sections={'dosha_effects': True},
            active_relationship_ids=set(),
            now=now,
        )

    # Mismatched source_id raises ValueError
    with pytest.raises(ValueError, match="belongs to source"):
        reconcile_section_omissions(
            conn,
            herb_id=ids["herb_id"],
            source_id=9999,
            event_id=event_id,
            section_domain='dosha_effects',
            parsed_sections={'dosha_effects': True},
            active_relationship_ids=set(),
            now=now,
        )

    # Omission detection flags eff_id as candidate_omission when omitted from active_relationship_ids
    res = reconcile_section_omissions(
        conn,
        herb_id=ids["herb_id"],
        source_id=ids["source_id"],
        event_id=event_id,
        section_domain='dosha_effects',
        parsed_sections={'dosha_effects': True},
        active_relationship_ids=set(),
        now=now,
    )
    conn.commit()

    assert res == {"flagged_candidate_omissions": 1, "skipped_incomplete": 0}
    assert conn.execute("SELECT source_presence_status FROM herb_dosha_effects WHERE herb_dosha_effect_id = ?", (eff_id,)).fetchone()[0] == 'candidate_omission'

