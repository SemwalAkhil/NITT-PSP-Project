"""
Herbal Almanac — Milestone C.1 Stage C Schema Implementation Test Suite
Executable pytest verification for Stage C normalized schema and Migration 3.

Validates the 23 Stage C requirements against an isolated Stage B database:
1. All Stage C table and view creation (exact object set verification).
2. Foreign-key integrity with SQLite foreign-key enforcement enabled.
3. Concept hierarchy cycle prevention.
4. Parent-child domain consistency.
5. Concept domain restrictions.
6. Cross-herb contamination prevention.
7. Dosha composite pairing integrity.
8. Label verification requirements.
9. Citation deletion and modification safeguards.
10. Source-presence status validation.
11. Source reconciliation event integrity.
12. Historical claim preservation & concept-mapped assertion immutability (all 6 fields).
13. Mid-execution failed migration rollback atomicity & trace verification.
14. Successful migration with dynamic UTC ISO-8601 timestamp.
15. Rollback and reapplication idempotence.
16. Stage B deterministic table-level snapshot data preservation.
17. Nullable composite uniqueness via partial unique indexes.
18. Source-claim assertion immutability via dosha assertions without mappings.
19. Forward migration prerequisite check under write lock with clean rollback.
20. Rollback migration prerequisite check under write lock with clean rollback.
21. Two-connection write-lock acquisition and serialization (genuine lock contention and release).
22. Sequential migration prerequisite rejection after another connection has committed a migration.
23. Synchronized concurrent multi-threaded write-lock serialization (deterministic thread events).
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from herbal_almanac.cleaning import PlantRecord
from herbal_almanac.database_operator import AyurvedicAlmanac

from herbal_almanac.migrations import migration_0003_semantic_dravyaguna as mig3

DDL_PATH = mig3.DDL_FILE


def snapshot_stage_b_tables(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Captures deterministic snapshots of all legacy Stage B tables."""
    stage_b_tables = [
        "herbs",
        "sources",
        "source_records",
        "source_claims",
        "legacy_herb_map",
        "herb_names",
        "herb_attributes",
        "herb_doshas",
        "illness",
        "treatment",
        "taxa",
        "taxon_relationships",
        "herb_taxa",
    ]
    snapshot = {}
    for table in stage_b_tables:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table,)
        ).fetchone()
        if exists:
            cursor = conn.execute(f"SELECT * FROM {table} ORDER BY rowid")
            cols = [desc[0] for desc in cursor.description]
            snapshot[table] = [dict(zip(cols, row)) for row in cursor.fetchall()]
    return snapshot


@pytest.fixture
def stage_b_db(tmp_path: Path):
    """Initializes an isolated Stage B database seeded with a canonical PlantRecord."""
    db_path = tmp_path / "test_stage_b.db"
    almanac = AyurvedicAlmanac(str(db_path))
    almanac.create_database()

    # Seed genuine Stage B historical record
    record = PlantRecord(
        source="DRAVYA",
        source_record_id=101,
        source_url="https://ccras.nic.in/dravya/101",
        retrieved_at="2026-11-18T12:00:00Z",
        ayurvedic_name="Haritaki",
        botanical_name="Terminalia chebula",
        family="Combretaceae",
        attributes={
            "Rasa": ["Kashaya", "Tikta"],
            "Guna": ["Laghu", "Ruksha"],
            "Virya": ["Ushna"],
            "Vipaka": ["Madhura"],
        },
        dosha_expressions=["Tridoshahara"],
    )
    almanac.insert_record(record)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    yield conn, str(db_path)
    conn.close()


def test_01_all_stage_c_table_creation(stage_b_db):
    """1. Verify creation of all 11 Stage C tables and 2 reporting views with exact object sets."""
    conn, _ = stage_b_db
    conn.isolation_level = None

    stage_b_tables_before = set(
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    )
    stage_b_views_before = set(
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"
        ).fetchall()
    )

    mig3.apply_migration(conn, DDL_PATH)

    current_tables = set(
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    )
    current_views = set(
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"
        ).fetchall()
    )

    expected_stage_c_tables = {
        "dravyaguna_concepts",
        "concept_labels",
        "concept_label_sources",
        "concept_claim_mappings",
        "dosha_claim_assertions",
        "herb_dravyaguna_properties",
        "herb_dosha_effects",
        "herb_plant_parts",
        "herb_preparations",
        "herb_indications",
        "source_reconciliation_events",
    }
    expected_stage_c_views = {
        "v_active_herb_dravyaguna_properties",
        "v_active_herb_dosha_effects",
    }

    # Verify that added tables match exactly expected 11 Stage C tables (no missing, no unexpected)
    added_tables = current_tables - stage_b_tables_before
    assert added_tables == expected_stage_c_tables, f"Mismatch in added tables: {added_tables ^ expected_stage_c_tables}"

    # Verify reporting views match exactly (no missing, no unexpected)
    added_views = current_views - stage_b_views_before
    assert added_views == expected_stage_c_views, f"Mismatch in added views: {added_views ^ expected_stage_c_views}"


def test_02_foreign_key_integrity(stage_b_db):
    """2. Verify foreign-key integrity with SQLite foreign-key enforcement enabled."""
    conn, _ = stage_b_db
    conn.isolation_level = None
    mig3.apply_migration(conn, DDL_PATH)

    now = "2026-11-18T12:00:00Z"
    # Seed concept
    conn.execute(
        "INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, status, created_at) "
        "VALUES (100, 'virya.ushna', 'virya', 'active', ?)",
        (now,),
    )
    # Seed claim mapping with non-existent source_claim_id -> must fail
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO concept_claim_mappings (source_claim_id, concept_id, mapping_type, mapping_method, created_at) "
            "VALUES (99999, 100, 'exact', 'lexicon_exact', ?)",
            (now,),
        )

    # Deleting concept with dependent label must be restricted
    conn.execute(
        "INSERT INTO concept_labels (concept_label_id, concept_id, language_code, script_code, label_text, normalized_label, label_type, translation_origin, created_at) "
        "VALUES (1, 100, 'sa', 'Deva', 'Uṣṇa', 'usna', 'canonical_sanskrit', 'classical_lexicon', ?)",
        (now,),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM dravyaguna_concepts WHERE concept_id = 100")


def test_03_concept_hierarchy_cycle_prevention(stage_b_db):
    """3. Verify concept hierarchy cycle prevention (self-parent and recursive cycle)."""
    conn, _ = stage_b_db
    conn.isolation_level = None
    mig3.apply_migration(conn, DDL_PATH)
    now = "2026-11-18T12:00:00Z"

    # Self-parenting check constraint
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, parent_concept_id, created_at) "
            "VALUES (201, 'rasa.madhura', 'rasa', 201, ?)",
            (now,),
        )

    # Insert valid hierarchy: 201 -> 202 -> 203
    conn.execute(
        "INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) "
        "VALUES (201, 'rasa.madhura', 'rasa', ?)",
        (now,),
    )
    conn.execute(
        "INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, parent_concept_id, created_at) "
        "VALUES (202, 'rasa.madhura_sub1', 'rasa', 201, ?)",
        (now,),
    )
    conn.execute(
        "INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, parent_concept_id, created_at) "
        "VALUES (203, 'rasa.madhura_sub2', 'rasa', 202, ?)",
        (now,),
    )

    # Updating 201's parent to 203 creates a cycle: 201 -> 202 -> 203 -> 201
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("UPDATE dravyaguna_concepts SET parent_concept_id = 203 WHERE concept_id = 201")
    assert "cycle" in str(exc_info.value).lower()


def test_04_parent_child_domain_consistency(stage_b_db):
    """4. Verify parent-child domain consistency and domain alteration blocks."""
    conn, _ = stage_b_db
    conn.isolation_level = None
    mig3.apply_migration(conn, DDL_PATH)
    now = "2026-11-18T12:00:00Z"

    conn.execute(
        "INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) "
        "VALUES (301, 'virya.ushna', 'virya', ?)",
        (now,),
    )
    # Child with different domain ('rasa' child pointing to 'virya' parent) must fail
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute(
            "INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, parent_concept_id, created_at) "
            "VALUES (302, 'rasa.tikta', 'rasa', 301, ?)",
            (now,),
        )
    assert "domain" in str(exc_info.value).lower()


def test_05_concept_domain_restrictions(stage_b_db):
    """5. Verify concept domain restrictions via CHECK constraints."""
    conn, _ = stage_b_db
    conn.isolation_level = None
    mig3.apply_migration(conn, DDL_PATH)
    now = "2026-11-18T12:00:00Z"

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) "
            "VALUES (401, 'invalid.code', 'unknown_domain', ?)",
            (now,),
        )


def test_06_cross_herb_contamination_prevention(stage_b_db):
    """6. Verify cross-herb mapping contamination prevention."""
    conn, _ = stage_b_db
    conn.isolation_level = None
    mig3.apply_migration(conn, DDL_PATH)
    now = "2026-11-18T12:00:00Z"

    # In stage_b_db, herb 1 exists with source_record_id = 1
    # Create herb 2 with a different source_record_id = 2
    source_id = conn.execute("SELECT source_id FROM sources LIMIT 1").fetchone()[0]
    conn.execute("INSERT INTO source_records (source_record_id, source_id, external_record_key) VALUES (2, ?, 'REC2')", (source_id,))
    conn.execute("INSERT INTO herbs (id, english_name, source, source_record_id) VALUES (2, 'Bibhitaki', 'DRAVYA', 2)")
    conn.execute("INSERT INTO legacy_herb_map (legacy_herb_id, herb_id, created_at) VALUES (2, 2, ?)", (now,))

    # Seed concept and mapping for Herb 1's claim (claim 1 belongs to record 1)
    conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (501, 'virya.ushna', 'virya', ?)", (now,))
    claim_id_1 = conn.execute("SELECT source_claim_id FROM source_claims WHERE source_record_id = 1 LIMIT 1").fetchone()[0]
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, created_at) VALUES (1, ?, 501, 'exact', 'lexicon_exact', ?)", (claim_id_1, now))

    # Attempt to attach Herb 1's mapping (mapping_id = 1) to Herb 2 (herb_id = 2) -> must fail!
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("INSERT INTO herb_dravyaguna_properties (herb_id, mapping_id, source_presence_status, created_at) VALUES (2, 1, 'active', ?)", (now,))
    assert "source record" in str(exc_info.value).lower()


def test_07_dosha_composite_pairing_integrity(stage_b_db):
    """7. Verify dosha composite pairing integrity and domain enforcement."""
    conn, _ = stage_b_db
    conn.isolation_level = None
    mig3.apply_migration(conn, DDL_PATH)
    now = "2026-11-18T12:00:00Z"

    conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (601, 'dosha.vata', 'dosha', ?)", (now,))
    conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (602, 'dosha_effect.shamana', 'dosha_effect', ?)", (now,))
    claim_id = conn.execute("SELECT source_claim_id FROM source_claims LIMIT 1").fetchone()[0]

    # Inverted pairing: effect concept as dosha and dosha concept as effect -> must fail
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute(
            "INSERT INTO dosha_claim_assertions (source_claim_id, dosha_concept_id, effect_concept_id, mapping_method, created_at) "
            "VALUES (?, 602, 601, 'rule_normalizer', ?)",
            (claim_id, now),
        )
    assert "domain" in str(exc_info.value).lower()


def test_08_label_verification_requirements(stage_b_db):
    """8. Verify multilingual label verification requirements."""
    conn, _ = stage_b_db
    conn.isolation_level = None
    mig3.apply_migration(conn, DDL_PATH)
    now = "2026-11-18T12:00:00Z"

    conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (701, 'virya.ushna', 'virya', ?)", (now,))

    # 1. Machine-generated labels cannot be verified
    conn.execute(
        "INSERT INTO concept_labels (concept_label_id, concept_id, language_code, script_code, label_text, normalized_label, label_type, translation_origin, verification_status, created_at) "
        "VALUES (10, 701, 'sa', 'Deva', 'MachineLabel', 'machinelabel', 'canonical_sanskrit', 'machine_generated', 'unreviewed', ?)",
        (now,),
    )
    conn.execute(
        "INSERT INTO concept_label_sources (label_source_id, concept_label_id, authority_citation, citation_type, verified_by, verified_at, created_at) "
        "VALUES (10, 10, 'Pharmacopoeia p.12', 'academic_lexicon', 'Dr. Sharma', ?, ?)",
        (now, now),
    )
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("UPDATE concept_labels SET verification_status = 'verified', verified_by = 'Dr. Sharma', verified_at = ? WHERE concept_label_id = 10", (now,))
    assert "machine-generated" in str(exc_info.value).lower()

    # 2. Verifying human curated label without verified_by or verified_at fails
    conn.execute("UPDATE concept_labels SET translation_origin = 'human_curated' WHERE concept_label_id = 10")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE concept_labels SET verification_status = 'verified', verified_by = NULL, reviewed_by = NULL WHERE concept_label_id = 10")

    # 3. Verifying without qualifying citation fails
    conn.execute("DELETE FROM concept_label_sources WHERE label_source_id = 10")
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("UPDATE concept_labels SET verification_status = 'verified', verified_by = 'Dr. Sharma', verified_at = ? WHERE concept_label_id = 10", (now,))
    assert "citation" in str(exc_info.value).lower()


def test_09_citation_deletion_and_modification_safeguards(stage_b_db):
    """9. Verify citation deletion and modification safeguards on verified labels."""
    conn, _ = stage_b_db
    conn.isolation_level = None
    mig3.apply_migration(conn, DDL_PATH)
    now = "2026-11-18T12:00:00Z"

    conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (801, 'virya.sheeta', 'virya', ?)", (now,))
    conn.execute(
        "INSERT INTO concept_labels (concept_label_id, concept_id, language_code, script_code, label_text, normalized_label, label_type, translation_origin, verification_status, created_at) "
        "VALUES (20, 801, 'sa', 'Deva', 'Śīta', 'sita', 'canonical_sanskrit', 'classical_lexicon', 'unreviewed', ?)",
        (now,),
    )
    conn.execute(
        "INSERT INTO concept_label_sources (label_source_id, concept_label_id, authority_citation, citation_type, verified_by, verified_at, created_at) "
        "VALUES (20, 20, 'Charaka Samhita Sutra 26', 'classical_text', 'Dr. Sharma', ?, ?)",
        (now, now),
    )
    conn.execute("UPDATE concept_labels SET verification_status = 'verified', verified_by = 'Dr. Sharma', verified_at = ? WHERE concept_label_id = 20", (now,))

    # Deleting the last verified citation must be blocked
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("DELETE FROM concept_label_sources WHERE label_source_id = 20")
    assert "last valid verified citation" in str(exc_info.value).lower()

    # Emptying the authority citation on a verified label must be blocked
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE concept_label_sources SET authority_citation = '' WHERE label_source_id = 20")


def test_10_source_presence_status_validation(stage_b_db):
    """10. Verify source-presence status validation across domain property tables."""
    conn, _ = stage_b_db
    conn.isolation_level = None
    mig3.apply_migration(conn, DDL_PATH)
    now = "2026-11-18T12:00:00Z"

    conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (901, 'virya.ushna', 'virya', ?)", (now,))
    claim_id = conn.execute("SELECT source_claim_id FROM source_claims LIMIT 1").fetchone()[0]
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, created_at) VALUES (901, ?, 901, 'exact', 'lexicon_exact', ?)", (claim_id, now))

    # Invalid status should be rejected by CHECK constraint
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO herb_dravyaguna_properties (herb_id, mapping_id, source_presence_status, created_at) VALUES (1, 901, 'invalid_status', ?)", (now,))

    # Valid statuses succeed
    for valid_status in ('active', 'candidate_omission', 'confirmed_omission'):
        conn.execute("INSERT INTO herb_dravyaguna_properties (herb_id, mapping_id, source_presence_status, created_at) VALUES (1, 901, ?, ?)", (valid_status, now))
        conn.execute("DELETE FROM herb_dravyaguna_properties WHERE herb_id = 1 AND mapping_id = 901")


def test_11_source_reconciliation_event_integrity(stage_b_db):
    """11. Verify source reconciliation event integrity and complete snapshot enforcement."""
    conn, _ = stage_b_db
    conn.isolation_level = None
    mig3.apply_migration(conn, DDL_PATH)
    now = "2026-11-18T12:00:00Z"
    source_id = conn.execute("SELECT source_id FROM sources LIMIT 1").fetchone()[0]

    # Incomplete extraction marked as complete snapshot must fail trigger and CHECK
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("""
        INSERT INTO source_reconciliation_events (source_id, event_type, snapshot_timestamp, extraction_status, is_complete_snapshot, initiated_by)
        VALUES (?, 'snapshot_reconciliation', ?, 'failed', 1, 'test_runner')
        """, (source_id, now))
    assert "incomplete or failed" in str(exc_info.value).lower()

    # Valid completed snapshot succeeds
    conn.execute("""
    INSERT INTO source_reconciliation_events (source_id, event_type, snapshot_timestamp, extraction_status, is_complete_snapshot, initiated_by)
    VALUES (?, 'snapshot_reconciliation', ?, 'completed', 1, 'test_runner')
    """, (source_id, now))

    # Updating completed event to failed status while is_complete_snapshot=1 must fail
    event_id = conn.execute("SELECT event_id FROM source_reconciliation_events ORDER BY event_id DESC LIMIT 1").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE source_reconciliation_events SET extraction_status = 'failed' WHERE event_id = ?", (event_id,))


def test_12_historical_claim_preservation(stage_b_db):
    """12. Verify source-claim assertion immutability for concept-mapped claims and provenance preservation."""
    conn, _ = stage_b_db
    conn.isolation_level = None
    mig3.apply_migration(conn, DDL_PATH)
    now = "2026-11-18T12:00:00Z"

    # Seed an active mapping tied to claim 1
    conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (1001, 'virya.ushna', 'virya', ?)", (now,))
    claim_id = conn.execute("SELECT source_claim_id FROM source_claims LIMIT 1").fetchone()[0]
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, created_at) VALUES (1001, ?, 1001, 'exact', 'lexicon_exact', ?)", (claim_id, now))
    conn.execute("INSERT INTO herb_dravyaguna_properties (herb_id, mapping_id, source_presence_status, created_at) VALUES (1, 1001, 'active', ?)", (now,))

    # Explicitly verify that all 6 assertion-defining fields are protected against in-place modification
    # 1. source_expression
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("UPDATE source_claims SET source_expression = 'Altered Virya' WHERE source_claim_id = ?", (claim_id,))
    assert "evidence immutability error" in str(exc_info.value).lower()

    # 2. source_field
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("UPDATE source_claims SET source_field = 'Rasa' WHERE source_claim_id = ?", (claim_id,))
    assert "evidence immutability error" in str(exc_info.value).lower()

    # 3. claim_type
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("UPDATE source_claims SET claim_type = 'botanical_identity' WHERE source_claim_id = ?", (claim_id,))
    assert "evidence immutability error" in str(exc_info.value).lower()

    # 4. source_record_id
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("UPDATE source_claims SET source_record_id = 999 WHERE source_claim_id = ?", (claim_id,))
    assert "evidence immutability error" in str(exc_info.value).lower()

    # 5. language_code
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("UPDATE source_claims SET language_code = 'en' WHERE source_claim_id = ?", (claim_id,))
    assert "evidence immutability error" in str(exc_info.value).lower()

    # 6. normalization_method
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("UPDATE source_claims SET normalization_method = 'manual_override' WHERE source_claim_id = ?", (claim_id,))
    assert "evidence immutability error" in str(exc_info.value).lower()

    # Verify review metadata can still be updated when allowed
    conn.execute(
        "UPDATE source_claims SET verification_status = 'reviewed', reviewed_by = 'Dr. Sharma', reviewed_at = ? WHERE source_claim_id = ?",
        (now, claim_id),
    )
    row_reviewed = conn.execute("SELECT verification_status, reviewed_by FROM source_claims WHERE source_claim_id = ?", (claim_id,)).fetchone()
    assert row_reviewed["verification_status"] == "reviewed"
    assert row_reviewed["reviewed_by"] == "Dr. Sharma"

    # Verify supersession workflow is permitted
    orig_claim = conn.execute("SELECT * FROM source_claims WHERE source_claim_id = ?", (claim_id,)).fetchone()
    conn.execute(
        "UPDATE source_claims SET verification_status = 'superseded', updated_at = ? WHERE source_claim_id = ?",
        (now, claim_id),
    )
    conn.execute(
        """
        INSERT INTO source_claims (
            source_record_id, claim_type, source_field, source_expression,
            language_code, retrieved_at, verification_status, created_by_type,
            created_by, created_at, updated_at, supersedes_claim_id
        ) VALUES (?, ?, ?, 'Sheeta', ?, ?, 'unreviewed', 'ingest', 'test_curator', ?, ?, ?)
        """,
        (orig_claim["source_record_id"], orig_claim["claim_type"], orig_claim["source_field"],
         orig_claim["language_code"], orig_claim["retrieved_at"], now, now, claim_id),
    )

    # Historical source claim remains available for audit
    superseded_claim = conn.execute("SELECT source_expression, verification_status FROM source_claims WHERE source_claim_id = ?", (claim_id,)).fetchone()
    assert superseded_claim["source_expression"] == orig_claim["source_expression"]
    assert superseded_claim["verification_status"] == "superseded"
    new_claim = conn.execute("SELECT source_expression, supersedes_claim_id FROM source_claims WHERE supersedes_claim_id = ?", (claim_id,)).fetchone()
    assert new_claim["source_expression"] == "Sheeta"
    assert new_claim["supersedes_claim_id"] == claim_id

    # Mutating sources.source_key when active dependent herbs exist must be blocked
    source_id = conn.execute("SELECT source_id FROM sources LIMIT 1").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("UPDATE sources SET source_key = 'MUTATED' WHERE source_id = ?", (source_id,))
    assert "source_key" in str(exc_info.value).lower()


def test_13_failed_migration_rollback(stage_b_db, tmp_path: Path):
    """13. Verify transactional atomicity and clean rollback on failed migration."""
    conn, _ = stage_b_db
    conn.isolation_level = None

    # Capture initial Stage B table snapshot
    initial_stage_b = snapshot_stage_b_tables(conn)

    # Test invalid trailing SQL statement rejection
    with pytest.raises(RuntimeError) as exc_info:
        mig3.execute_statements(conn, "CREATE TABLE test_temp (id INT); SELECT * FROM")
    assert "Incomplete trailing SQL statement" in str(exc_info.value)

    # Test rejection of active transaction
    conn.execute("BEGIN IMMEDIATE;")
    with pytest.raises(RuntimeError) as exc_info:
        mig3.apply_migration(conn, DDL_PATH)
    assert "active transaction" in str(exc_info.value)
    conn.rollback()

    # Test mid-execution migration failure atomicity with temporary DDL file
    faulty_ddl = tmp_path / "faulty_stage_c.sql"
    faulty_ddl.write_text(
        "CREATE TABLE canary_migration_atomicity_test (id INTEGER PRIMARY KEY, note TEXT);\n"
        "INSERT INTO canary_migration_atomicity_test (id, note) VALUES (1, 'canary_row');\n"
        "THIS IS INTENTIONALLY INVALID SQL STATEMENT THAT CAUSES MID_EXECUTION FAILURE;\n",
        encoding="utf-8",
    )

    executed_statements = []
    conn.set_trace_callback(executed_statements.append)

    # Calls apply_migration using the faulty DDL file -> must raise sqlite3.OperationalError for syntax error
    with pytest.raises(sqlite3.OperationalError) as exc_info:
        mig3.apply_migration(conn, ddl_path=faulty_ddl)
    conn.set_trace_callback(None)

    # 1. Assert expected syntax error
    assert any("syntax error" in str(arg).lower() for arg in exc_info.value.args)

    # 2. Verify canary statements were actually executed before the failure occurred
    assert any("CREATE TABLE canary_migration_atomicity_test" in s for s in executed_statements)
    assert any("INSERT INTO canary_migration_atomicity_test" in s for s in executed_statements)

    # 3. After failure, verify rollback:
    # - Canary table does not exist
    assert conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='canary_migration_atomicity_test'").fetchone() is None

    # - Schema version remains 2
    v = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
    assert v == 2

    # - No Migration 3 ledger row exists
    row_v3 = conn.execute("SELECT 1 FROM schema_migrations WHERE version = 3").fetchone()
    assert row_v3 is None

    # - Stage B data remains 100% unchanged
    assert snapshot_stage_b_tables(conn) == initial_stage_b

    # - No transaction remains unexpectedly open
    assert not conn.in_transaction


def test_14_successful_migration(stage_b_db):
    """14. Verify successful atomic migration records schema version 3 with dynamic UTC ISO-8601 timestamp."""
    conn, _ = stage_b_db
    conn.isolation_level = None
    mig3.apply_migration(conn, DDL_PATH)

    v = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
    assert v == 3
    row = conn.execute("SELECT name, applied_at FROM schema_migrations WHERE version = 3").fetchone()
    assert row["name"] == "semantic_dravyaguna"
    
    applied_at = row["applied_at"]
    assert applied_at is not None and len(applied_at.strip()) > 0

    # Verify applied_at represents a valid UTC ISO-8601 timestamp
    assert applied_at.endswith("Z") or "+00:00" in applied_at
    parsed_dt = datetime.fromisoformat(applied_at.replace("Z", "+00:00"))
    assert parsed_dt.tzinfo == timezone.utc

    # Verify dynamically generated at execution time (within 60 seconds of now)
    now_utc = datetime.now(timezone.utc)
    diff_seconds = abs((now_utc - parsed_dt).total_seconds())
    assert diff_seconds < 60, f"Timestamp {applied_at} was not generated dynamically (diff={diff_seconds}s)"


def test_15_rollback_and_reapplication(stage_b_db):
    """15. Verify rollback and reapplication idempotence."""
    conn, _ = stage_b_db
    conn.isolation_level = None

    # Forward migration
    mig3.apply_migration(conn, DDL_PATH)
    assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 3

    # Rollback
    mig3.rollback_migration(conn)
    assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 2
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "dravyaguna_concepts" not in tables
    assert "source_reconciliation_events" not in tables

    # Reapplication
    mig3.apply_migration(conn, DDL_PATH)
    assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 3
    tables_reapplied = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "dravyaguna_concepts" in tables_reapplied
    assert "source_reconciliation_events" in tables_reapplied


def test_16_stage_b_data_preservation(stage_b_db):
    """16. Verify 100% preservation of Stage B data and legacy tables through upgrade and rollback."""
    conn, _ = stage_b_db
    conn.isolation_level = None

    # Capture complete deterministic table snapshot of all Stage B tables
    initial_stage_b = snapshot_stage_b_tables(conn)

    # Migrate forward
    mig3.apply_migration(conn, DDL_PATH)
    # Stage B tables remain 100% identical after forward migration
    assert snapshot_stage_b_tables(conn) == initial_stage_b

    # Rollback
    mig3.rollback_migration(conn)
    # Stage B tables remain 100% identical after rollback
    assert snapshot_stage_b_tables(conn) == initial_stage_b

    # Re-apply
    mig3.apply_migration(conn, DDL_PATH)
    assert snapshot_stage_b_tables(conn) == initial_stage_b


def test_17_nullable_composite_uniqueness(stage_b_db):
    """17. Verify nullable composite uniqueness via partial unique indexes and constraints.
    
    Proves:
    1. Duplicate unspecified-part properties are rejected.
    2. Duplicate unspecified-part preparations are rejected.
    3. Different specified plant parts remain valid.
    4. Identical specified-part relationships remain rejected.
    """
    conn, _ = stage_b_db
    conn.isolation_level = None
    mig3.apply_migration(conn, DDL_PATH)
    now = "2026-11-18T12:00:00Z"

    # Seed concepts: virya, plant parts, and preparation form
    conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (101, 'virya.ushna', 'virya', ?)", (now,))
    conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (102, 'plant_part.fruit', 'plant_part', ?)", (now,))
    conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (103, 'plant_part.root', 'plant_part', ?)", (now,))
    conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (104, 'preparation_form.churna', 'preparation_form', ?)", (now,))

    # Seed source claims on record 1
    sr_id = conn.execute("SELECT source_record_id FROM source_records LIMIT 1").fetchone()[0]
    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at) VALUES (201, ?, 'attribute', 'Virya', 'Ushna', 'unreviewed', 'ingest', 'dravya_v1', ?, ?)", (sr_id, now, now))
    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at) VALUES (202, ?, 'attribute', 'Part', 'Fruit', 'unreviewed', 'ingest', 'dravya_v1', ?, ?)", (sr_id, now, now))
    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at) VALUES (203, ?, 'attribute', 'Part', 'Root', 'unreviewed', 'ingest', 'dravya_v1', ?, ?)", (sr_id, now, now))
    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at) VALUES (204, ?, 'attribute', 'Form', 'Churna', 'unreviewed', 'ingest', 'dravya_v1', ?, ?)", (sr_id, now, now))

    # Seed concept mappings
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, created_at) VALUES (301, 201, 101, 'exact', 'lexicon_exact', ?)", (now,))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, created_at) VALUES (302, 202, 102, 'exact', 'lexicon_exact', ?)", (now,))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, created_at) VALUES (303, 203, 103, 'exact', 'lexicon_exact', ?)", (now,))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, created_at) VALUES (304, 204, 104, 'exact', 'lexicon_exact', ?)", (now,))

    # --- herb_dravyaguna_properties Tests ---
    # 1. Duplicate unspecified-part properties are rejected
    conn.execute("INSERT INTO herb_dravyaguna_properties (herb_id, mapping_id, part_concept_id, created_at) VALUES (1, 301, NULL, ?)", (now,))
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("INSERT INTO herb_dravyaguna_properties (herb_id, mapping_id, part_concept_id, created_at) VALUES (1, 301, NULL, ?)", (now,))
    assert "unique" in str(exc_info.value).lower()

    # 3. Different specified plant parts remain valid
    conn.execute("INSERT INTO herb_dravyaguna_properties (herb_id, mapping_id, part_concept_id, created_at) VALUES (1, 301, 102, ?)", (now,))
    conn.execute("INSERT INTO herb_dravyaguna_properties (herb_id, mapping_id, part_concept_id, created_at) VALUES (1, 301, 103, ?)", (now,))

    # 4. Identical specified-part relationships remain rejected
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("INSERT INTO herb_dravyaguna_properties (herb_id, mapping_id, part_concept_id, created_at) VALUES (1, 301, 102, ?)", (now,))
    assert "unique" in str(exc_info.value).lower()

    # --- herb_preparations Tests ---
    # 2. Duplicate unspecified-part preparations are rejected
    conn.execute("INSERT INTO herb_preparations (herb_id, prep_mapping_id, part_mapping_id, created_at) VALUES (1, 304, NULL, ?)", (now,))
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("INSERT INTO herb_preparations (herb_id, prep_mapping_id, part_mapping_id, created_at) VALUES (1, 304, NULL, ?)", (now,))
    assert "unique" in str(exc_info.value).lower()

    # 3. Different specified plant parts remain valid
    conn.execute("INSERT INTO herb_preparations (herb_id, prep_mapping_id, part_mapping_id, created_at) VALUES (1, 304, 302, ?)", (now,))
    conn.execute("INSERT INTO herb_preparations (herb_id, prep_mapping_id, part_mapping_id, created_at) VALUES (1, 304, 303, ?)", (now,))

    # 4. Identical specified-part relationships remain rejected
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("INSERT INTO herb_preparations (herb_id, prep_mapping_id, part_mapping_id, created_at) VALUES (1, 304, 302, ?)", (now,))
    assert "unique" in str(exc_info.value).lower()


def test_18_source_claim_immutability_via_dosha_assertion(stage_b_db):
    """18. Verify source-claim assertion immutability for dosha-asserted claims without concept mappings.
    
    Verifies that:
    - Protected source fields cannot be modified when referenced by dosha_claim_assertions.
    - Verification/reviewer metadata can still be updated when allowed.
    - Supersession remains possible.
    - The original claim remains available for historical audit.
    - A replacement claim can reference the original through supersedes_claim_id.
    """
    conn, _ = stage_b_db
    conn.isolation_level = None
    mig3.apply_migration(conn, DDL_PATH)
    now = "2026-11-18T12:00:00Z"

    # Seed dosha concepts
    conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (601, 'dosha.pitta', 'dosha', ?)", (now,))
    conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (602, 'dosha_effect.vardhana', 'dosha_effect', ?)", (now,))

    # Seed source claim solely for dosha assertion (no concept_claim_mappings row)
    sr_id = conn.execute("SELECT source_record_id FROM source_records LIMIT 1").fetchone()[0]
    conn.execute(
        """
        INSERT INTO source_claims (
            source_claim_id, source_record_id, claim_type, source_field,
            source_expression, language_code, retrieved_at, verification_status,
            created_by_type, created_by, created_at, updated_at
        ) VALUES (777, ?, 'dosha', 'Doshakarma', 'Pitta vardhana', 'sa', ?, 'unreviewed', 'ingest', 'dravya_v1', ?, ?)
        """,
        (sr_id, now, now, now),
    )

    # Associate via dosha_claim_assertions ONLY (no mapping row exists)
    conn.execute(
        """
        INSERT INTO dosha_claim_assertions (
            dosha_assertion_id, source_claim_id, dosha_concept_id, effect_concept_id,
            mapping_method, verification_status, created_at
        ) VALUES (777, 777, 601, 602, 'rule_normalizer', 'unreviewed', ?)
        """,
        (now,),
    )
    # Confirm no mapping exists for claim 777
    assert conn.execute("SELECT COUNT(*) FROM concept_claim_mappings WHERE source_claim_id = 777").fetchone()[0] == 0

    # Explicitly test all 6 protected assertion-defining fields
    # 1. source_expression
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("UPDATE source_claims SET source_expression = 'Vata shamana' WHERE source_claim_id = 777")
    assert "evidence immutability error" in str(exc_info.value).lower()

    # 2. source_field
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("UPDATE source_claims SET source_field = 'Virya' WHERE source_claim_id = 777")
    assert "evidence immutability error" in str(exc_info.value).lower()

    # 3. claim_type
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("UPDATE source_claims SET claim_type = 'attribute' WHERE source_claim_id = 777")
    assert "evidence immutability error" in str(exc_info.value).lower()

    # 4. source_record_id
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("UPDATE source_claims SET source_record_id = 999 WHERE source_claim_id = 777")
    assert "evidence immutability error" in str(exc_info.value).lower()

    # 5. language_code
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("UPDATE source_claims SET language_code = 'en' WHERE source_claim_id = 777")
    assert "evidence immutability error" in str(exc_info.value).lower()

    # 6. normalization_method
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        conn.execute("UPDATE source_claims SET normalization_method = 'manual' WHERE source_claim_id = 777")
    assert "evidence immutability error" in str(exc_info.value).lower()

    # Verification / reviewer metadata can still be updated
    conn.execute(
        "UPDATE source_claims SET verification_status = 'reviewed', reviewed_by = 'Dr. Patel', reviewed_at = ? WHERE source_claim_id = 777",
        (now,),
    )
    assert conn.execute("SELECT verification_status FROM source_claims WHERE source_claim_id = 777").fetchone()[0] == "reviewed"

    # Supersession remains possible
    conn.execute("UPDATE source_claims SET verification_status = 'superseded', updated_at = ? WHERE source_claim_id = 777", (now,))
    conn.execute(
        """
        INSERT INTO source_claims (
            source_claim_id, source_record_id, claim_type, source_field,
            source_expression, language_code, retrieved_at, verification_status,
            created_by_type, created_by, created_at, updated_at, supersedes_claim_id
        ) VALUES (778, ?, 'dosha', 'Doshakarma', 'Pitta shamana', 'sa', ?, 'unreviewed', 'ingest', 'dravya_v1', ?, ?, 777)
        """,
        (sr_id, now, now, now),
    )

    # Historical audit preservation
    orig_row = conn.execute("SELECT source_expression, verification_status FROM source_claims WHERE source_claim_id = 777").fetchone()
    assert orig_row["source_expression"] == "Pitta vardhana"
    assert orig_row["verification_status"] == "superseded"
    new_row = conn.execute("SELECT source_expression, supersedes_claim_id FROM source_claims WHERE source_claim_id = 778").fetchone()
    assert new_row["source_expression"] == "Pitta shamana"
    assert new_row["supersedes_claim_id"] == 777


def test_19_forward_migration_prerequisite_validation(tmp_path: Path):
    """19. Verify forward migration prerequisite check under write lock rolls back cleanly on version mismatch."""
    db_path = tmp_path / "test_prereq_forward.db"
    conn = sqlite3.connect(str(db_path))
    conn.isolation_level = None
    conn.execute("PRAGMA foreign_keys = ON;")
    
    # Initialize a database at schema version 1 (not version 2)
    conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL);")
    conn.execute("INSERT INTO schema_migrations (version, name, applied_at) VALUES (1, 'core_identity_and_provenance', '2026-11-18T10:00:00Z');")
    
    # Attempting to apply Migration 3 must fail the prerequisite (expected 2, got 1)
    with pytest.raises(RuntimeError) as exc_info:
        mig3.apply_migration(conn, DDL_PATH)
    assert "expected version 2, got 1" in str(exc_info.value)
    
    # Verify no Stage C tables or views were created
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "dravyaguna_concepts" not in tables
    assert "concept_labels" not in tables
    assert "source_reconciliation_events" not in tables
    views = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall()]
    assert "v_active_herb_dravyaguna_properties" not in views
    
    # Verify migration ledger remains unchanged at version 1
    v = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
    assert v == 1
    assert conn.execute("SELECT 1 FROM schema_migrations WHERE version = 3").fetchone() is None
    
    # Verify transaction is closed after failure
    assert not conn.in_transaction
    conn.close()


def test_20_rollback_migration_prerequisite_validation(stage_b_db):
    """20. Verify rollback migration prerequisite check under write lock rolls back cleanly on version mismatch."""
    conn, _ = stage_b_db
    conn.isolation_level = None
    
    # Database is currently at version 2 (prerequisite for rollback is version 3)
    v_initial = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
    assert v_initial == 2
    initial_snapshot = snapshot_stage_b_tables(conn)
    
    # Attempting rollback at version 2 must fail the prerequisite (expected 3, got 2)
    with pytest.raises(RuntimeError) as exc_info:
        mig3.rollback_migration(conn)
    assert "expected version 3, got 2" in str(exc_info.value)
    
    # Verify existing schema objects and Stage B data remain completely unchanged
    assert snapshot_stage_b_tables(conn) == initial_snapshot
    assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 2
    
    # Verify transaction is closed after failure
    assert not conn.in_transaction


def test_21_two_connection_version_check_under_write_lock(stage_b_db):
    """21. Genuinely verify SQLite write-lock acquisition, contention, and serialization across two connections.
    
    Validates the 8-step write-lock serialization protocol:
    1. Open two connections to the same temporary database.
    2. Configure a short, explicit busy timeout for deterministic testing.
    3. Have connection 1 acquire BEGIN IMMEDIATE and retain the write lock.
    4. Have connection 2 attempt to acquire BEGIN IMMEDIATE (and apply_migration).
    5. Verify connection 2 cannot acquire the lock while connection 1 holds it.
    6. Release connection 1's transaction.
    7. Verify connection 2 can subsequently acquire the lock and read the schema version under write lock.
    8. Ensure both connections are cleanly closed and no transaction is left open.
    """
    conn1, db_path = stage_b_db
    conn1.isolation_level = None
    
    # 1. Open second connection to the same temporary database
    conn2 = sqlite3.connect(db_path, timeout=0.05)
    conn2.isolation_level = None
    
    # 2. Configure short, explicit busy timeout for deterministic testing (50ms)
    conn2.execute("PRAGMA busy_timeout = 50;")
    
    try:
        # Initial state check
        assert conn1.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 2
        assert conn2.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 2
        
        # 3. Have connection 1 acquire BEGIN IMMEDIATE and retain the write lock
        conn1.execute("BEGIN IMMEDIATE;")
        assert conn1.in_transaction
        
        # 4 & 5. Have connection 2 attempt to acquire BEGIN IMMEDIATE and verify contention
        with pytest.raises(sqlite3.OperationalError) as exc_info:
            conn2.execute("BEGIN IMMEDIATE;")
        assert "locked" in str(exc_info.value).lower() or "busy" in str(exc_info.value).lower()
        assert not conn2.in_transaction
        
        # Also verify apply_migration fails immediately when attempting BEGIN IMMEDIATE on locked database
        with pytest.raises(sqlite3.OperationalError) as exc_mig:
            mig3.apply_migration(conn2, DDL_PATH)
        assert "locked" in str(exc_mig.value).lower() or "busy" in str(exc_mig.value).lower()
        assert not conn2.in_transaction
        
        # 6. Release connection 1's transaction
        conn1.rollback()
        assert not conn1.in_transaction
        
        # 7. Verify connection 2 can subsequently acquire the lock and read schema version under write lock
        conn2.execute("BEGIN IMMEDIATE;")
        assert conn2.in_transaction
        v2 = conn2.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        assert v2 == 2
        conn2.rollback()
        assert not conn2.in_transaction
        
    finally:
        # 8. Ensure both connections are cleanly closed and no transaction is left open
        if conn1.in_transaction:
            conn1.rollback()
        if conn2.in_transaction:
            conn2.rollback()
        conn2.close()
        assert not conn1.in_transaction


def test_22_sequential_migration_rejection_on_upgraded_database(stage_b_db):
    """22. Verify that sequential migration attempt rejects an already-upgraded database under write lock."""
    conn1, db_path = stage_b_db
    conn1.isolation_level = None
    
    conn2 = sqlite3.connect(db_path)
    conn2.isolation_level = None
    conn2.execute("PRAGMA foreign_keys = ON;")
    
    try:
        # Initial state: database at version 2
        assert conn1.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 2
        assert conn2.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 2
        
        # Connection 1 successfully applies Migration 3
        mig3.apply_migration(conn1, DDL_PATH)
        assert conn1.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 3
        
        # Connection 2 attempts to apply Migration 3:
        # Under BEGIN IMMEDIATE write lock, it reads version 3 and rejects with expected version 2, got 3
        with pytest.raises(RuntimeError) as exc_info:
            mig3.apply_migration(conn2, DDL_PATH)
        assert "expected version 2, got 3" in str(exc_info.value)
        assert not conn2.in_transaction
        
        # Connection 1 rolls back Migration 3 to version 2
        mig3.rollback_migration(conn1)
        assert conn1.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 2
        
        # Connection 2 attempts to rollback Migration 3:
        # Under BEGIN IMMEDIATE write lock, it reads version 2 and rejects with expected version 3, got 2
        with pytest.raises(RuntimeError) as exc_info:
            mig3.rollback_migration(conn2)
        assert "expected version 3, got 2" in str(exc_info.value)
        assert not conn2.in_transaction
    finally:
        conn2.close()


def test_23_concurrent_thread_write_lock_serialization(stage_b_db):
    """23. Verify actual multi-threaded write-lock serialization using synchronized threading events."""
    _, db_path = stage_b_db
    
    ev_locked = threading.Event()
    ev_attempted = threading.Event()
    ev_released = threading.Event()
    thread_outcomes = {}
    
    def worker_holder():
        c1 = sqlite3.connect(db_path, timeout=1.0)
        c1.isolation_level = None
        try:
            c1.execute("BEGIN IMMEDIATE;")
            ev_locked.set()
            # Wait until worker_contender attempts to acquire the lock and catches OperationalError
            if not ev_attempted.wait(timeout=5.0):
                thread_outcomes["holder_error"] = "timeout waiting for contender attempt"
                return
            c1.rollback()
            ev_released.set()
        finally:
            c1.close()
            
    def worker_contender():
        # Wait until worker_holder holds BEGIN IMMEDIATE write lock
        if not ev_locked.wait(timeout=5.0):
            thread_outcomes["contender_error"] = "timeout waiting for holder write lock"
            return
            
        c2 = sqlite3.connect(db_path, timeout=0.05)
        c2.isolation_level = None
        c2.execute("PRAGMA busy_timeout = 50;")
        try:
            try:
                c2.execute("BEGIN IMMEDIATE;")
                thread_outcomes["contender_status"] = "unexpectedly_acquired"
            except sqlite3.OperationalError as e:
                thread_outcomes["contender_status"] = "locked"
                thread_outcomes["contender_error_msg"] = str(e)
            
            ev_attempted.set()
            
            # Wait until worker_holder releases write lock
            if not ev_released.wait(timeout=5.0):
                thread_outcomes["contender_error"] = "timeout waiting for holder release"
                return
                
            # Now contender can acquire write lock and read schema version
            c2.execute("BEGIN IMMEDIATE;")
            v = c2.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            thread_outcomes["contender_version"] = v
            c2.rollback()
        finally:
            c2.close()
            
    t1 = threading.Thread(target=worker_holder)
    t2 = threading.Thread(target=worker_contender)
    t1.start()
    t2.start()
    t1.join(timeout=5.0)
    t2.join(timeout=5.0)
    
    assert not t1.is_alive(), "Worker holder thread hung or timed out"
    assert not t2.is_alive(), "Worker contender thread hung or timed out"
    assert thread_outcomes.get("contender_status") == "locked"
    assert "locked" in thread_outcomes.get("contender_error_msg", "").lower()
    assert thread_outcomes.get("contender_version") == 2
