"""Herbal Almanac — Stage C.2 Work Package 5 (WP-5)
Unit Test Suite for Repository API & Presentation Services

Tests:
1. Schema v2 capability gating (FeatureUnavailableError)
2. Herb not found error handling (KeyError)
3. Active Dravyaguna profile resolution & multilingual labels (en vs hi, Devanagari/IAST)
4. Disputed mapping filtering & visibility (include_disputed=False vs True)
5. Provisional concept quarantine (include_provisional=False vs True)
6. Virya reconciliation multi-tier divergence & summary counts
7. Active concept filtering in Virya reconciliation (ADR Section 9.B.3)
8. Inspection DB invariance check (remains strictly at version 2)
"""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import sys
import tempfile
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
from herbal_almanac.schema_capability_gate import FeatureUnavailableError, get_schema_version
from herbal_almanac.concept_catalog import seed_canonical_concept_catalog
from herbal_almanac.repository_api import (
    herb_dravyaguna_profile,
    reconcile_herb_virya,
    ViryaReconciliationReport,
)


# ============================================================================
# Fixtures & Helpers
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
def v3_db(v2_db):
    """Provides a fresh temporary SQLite database migrated to Schema Version 3 ([1, 2, 3])."""
    conn, db_path = v2_db
    migration_0003_semantic_dravyaguna.apply_migration(conn)
    seed_canonical_concept_catalog(conn)
    yield conn, db_path


def _cid(conn: sqlite3.Connection, concept_code: str) -> int:
    """Helper to fetch concept_id for a given canonical concept_code."""
    row = conn.execute(
        "SELECT concept_id FROM dravyaguna_concepts WHERE concept_code = ?",
        (concept_code,),
    ).fetchone()
    assert row is not None, f"Concept code {concept_code} not found in seeded catalog"
    return row[0]


def _source_id(conn: sqlite3.Connection, source_key: str = "CCRAS_DRAVYA") -> int:
    """Helper to fetch or create source_id for a given source_key."""
    row = conn.execute("SELECT source_id FROM sources WHERE source_key = ?", (source_key,)).fetchone()
    if row is not None:
        return row[0]
    conn.execute("INSERT INTO sources (source_key, publisher) VALUES (?, 'Govt of India')", (source_key,))
    return conn.execute("SELECT source_id FROM sources WHERE source_key = ?", (source_key,)).fetchone()[0]


# ============================================================================
# Tests: Capability Gating & Error Handling
# ============================================================================

def test_wp5_capability_gating_raises_on_v2(v2_db):
    """Calling Stage C semantic APIs on Schema v2 raises FeatureUnavailableError."""
    conn, _ = v2_db
    assert get_schema_version(conn) == 2

    # Insert a dummy Stage B herb
    conn.execute(
        "INSERT INTO herbs (id, english_name, source, source_record_id) VALUES (1, 'Tulsi', 'CCRAS_DRAVYA', 101)"
    )
    conn.commit()

    with pytest.raises(FeatureUnavailableError, match="Stage C normalized semantic features require schema version 3"):
        herb_dravyaguna_profile(conn, 1)

    with pytest.raises(FeatureUnavailableError, match="Stage C normalized semantic features require schema version 3"):
        reconcile_herb_virya(conn, 1)


def test_wp5_herb_not_found_raises_key_error(v3_db):
    """Querying an unknown herb_id raises KeyError."""
    conn, _ = v3_db
    with pytest.raises(KeyError, match="Herb with id 9999 not found"):
        herb_dravyaguna_profile(conn, 9999)

    with pytest.raises(KeyError, match="Herb with id 9999 not found"):
        reconcile_herb_virya(conn, 9999)


# ============================================================================
# Tests: Dravyaguna Profile Resolution & Multilingual Presentation
# ============================================================================

def test_wp5_dravyaguna_profile_multilingual_and_sanskrit(v3_db):
    """Test full Dravyaguna profile resolution with multilingual labels and Sanskrit references."""
    conn, _ = v3_db
    now = "2026-11-18T12:00:00Z"
    s_id = _source_id(conn, "CCRAS_DRAVYA")

    # 1. Setup provenance: source_record, herb, legacy_herb_map
    conn.execute("INSERT INTO source_records (source_record_id, source_id, external_record_key) VALUES (101, ?, '101')", (s_id,))
    conn.execute("INSERT INTO herbs (id, english_name, botanical_name, source, source_record_id) VALUES (1, 'Ginger', 'Zingiber officinale', 'CCRAS_DRAVYA', 101)")
    conn.execute("INSERT INTO legacy_herb_map (legacy_herb_id, herb_id, created_at) VALUES (1, 1, ?)", (now,))

    # 2. Retrieve canonical concept IDs from seeded catalog
    cid_katu = _cid(conn, "RASA_KATU")
    cid_rhizome = _cid(conn, "PART_RHIZOME")
    cid_kapha = _cid(conn, "DOSHA_KAPHA")
    cid_decrease = _cid(conn, "EFFECT_DECREASE")
    cid_churna = _cid(conn, "PREP_CHURNA")
    cid_kasa = _cid(conn, "IND_KASA")

    # 3. Create claims and mappings
    # Claim 1: Rasa = Katu on Rhizome
    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (1, 101, 'property', 'Rasa', 'Katu', 'reviewed', 'Dr. Sharma', ?, 'ingest', 'loader', ?, ?)", (now, now, now))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_confidence, mapping_method, verification_status, created_at) VALUES (1, 1, ?, 'exact', 1.0, 'lexicon_exact', 'reviewed', ?)", (cid_katu, now))
    conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (1, 1, 1, ?, 'active', ?)", (cid_rhizome, now))

    # Claim 2: Dosha = Kapha Shamana
    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (2, 101, 'dosha_effect', 'Dosha', 'Kapha-shamana', 'reviewed', 'Dr. Sharma', ?, 'ingest', 'loader', ?, ?)", (now, now, now))
    conn.execute("INSERT INTO dosha_claim_assertions (dosha_assertion_id, source_claim_id, dosha_concept_id, effect_concept_id, mapping_confidence, mapping_method, verification_status, created_at) VALUES (1, 2, ?, ?, 1.0, 'rule_normalizer', 'reviewed', ?)", (cid_kapha, cid_decrease, now))
    conn.execute("INSERT INTO herb_dosha_effects (herb_dosha_effect_id, herb_id, dosha_assertion_id, source_presence_status, created_at) VALUES (1, 1, 1, 'active', ?)", (now,))

    # Claim 3: Plant Part = Rhizome
    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (3, 101, 'plant_part', 'Part', 'Rhizome', 'reviewed', 'Dr. Sharma', ?, 'ingest', 'loader', ?, ?)", (now, now, now))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_confidence, mapping_method, verification_status, created_at) VALUES (2, 3, ?, 'exact', 1.0, 'lexicon_exact', 'reviewed', ?)", (cid_rhizome, now))
    conn.execute("INSERT INTO herb_plant_parts (herb_part_id, herb_id, mapping_id, source_presence_status, created_at) VALUES (1, 1, 2, 'active', ?)", (now,))

    # Claim 4: Preparation = Churna on Rhizome
    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (4, 101, 'preparation', 'Form', 'Churna', 'reviewed', 'Dr. Sharma', ?, 'ingest', 'loader', ?, ?)", (now, now, now))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_confidence, mapping_method, verification_status, created_at) VALUES (3, 4, ?, 'exact', 1.0, 'lexicon_exact', 'reviewed', ?)", (cid_churna, now))
    conn.execute("INSERT INTO herb_preparations (herb_preparation_id, herb_id, prep_mapping_id, part_mapping_id, source_presence_status, created_at) VALUES (1, 1, 3, 2, 'active', ?)", (now,))

    # Claim 5: Indication = Kasa
    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (5, 101, 'indication', 'Indication', 'Kasa', 'reviewed', 'Dr. Sharma', ?, 'ingest', 'loader', ?, ?)", (now, now, now))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_confidence, mapping_method, verification_status, created_at) VALUES (4, 5, ?, 'exact', 1.0, 'lexicon_exact', 'reviewed', ?)", (cid_kasa, now))
    conn.execute("INSERT INTO herb_indications (herb_indication_id, herb_id, mapping_id, source_presence_status, created_at) VALUES (1, 1, 4, 'active', ?)", (now,))

    conn.commit()

    # 4. Resolve profile in English
    profile_en = herb_dravyaguna_profile(conn, 1, language="en")
    assert profile_en["herb_id"] == 1
    assert profile_en["english_name"] == "Ginger"
    assert profile_en["botanical_name"] == "Zingiber officinale"
    assert profile_en["language"] == "en"

    # Check Properties
    assert len(profile_en["properties"]) == 1
    prop = profile_en["properties"][0]
    assert prop["concept_code"] == "RASA_KATU"
    assert "Pungent" in prop["display_label"]
    assert prop["canonical_sanskrit_deva"] == "कटु"
    assert prop["canonical_sanskrit_iast"] == "Kaṭu"
    assert prop["part_concept_code"] == "PART_RHIZOME"
    assert prop["part_display_label"] == "Rhizome"
    assert prop["is_disputed"] is False

    # Check Dosha Effects
    assert len(profile_en["dosha_effects"]) == 1
    dosha = profile_en["dosha_effects"][0]
    assert dosha["dosha_concept_code"] == "DOSHA_KAPHA"
    assert "Kapha" in dosha["dosha_display_label"]
    assert dosha["effect_concept_code"] == "EFFECT_DECREASE"
    assert "Pacif" in dosha["effect_display_label"]

    # Check Plant Parts
    assert len(profile_en["plant_parts"]) == 1
    part = profile_en["plant_parts"][0]
    assert part["concept_code"] == "PART_RHIZOME"
    assert part["display_label"] == "Rhizome"

    # Check Preparations
    assert len(profile_en["preparations"]) == 1
    prep = profile_en["preparations"][0]
    assert prep["prep_concept_code"] == "PREP_CHURNA"
    assert "Powder" in prep["prep_display_label"]
    assert prep["part_concept_code"] == "PART_RHIZOME"
    assert prep["part_display_label"] == "Rhizome"

    # Check Indications
    assert len(profile_en["indications"]) == 1
    ind = profile_en["indications"][0]
    assert ind["indication_concept_code"] == "IND_KASA"
    assert "Cough" in ind["display_label"]

    # 5. Resolve profile in Hindi
    profile_hi = herb_dravyaguna_profile(conn, 1, language="hi")
    assert "कटु" in profile_hi["properties"][0]["display_label"]


# ============================================================================
# Tests: Disputed Mapping Filtering & Visibility
# ============================================================================

def test_wp5_dravyaguna_profile_disputed_filtering(v3_db):
    """Disputed mappings are excluded by default and exposed when include_disputed=True."""
    conn, _ = v3_db
    now = "2026-11-18T12:00:00Z"
    s_id = _source_id(conn, "CCRAS_DRAVYA")

    conn.execute("INSERT INTO source_records (source_record_id, source_id, external_record_key) VALUES (101, ?, '101')", (s_id,))
    conn.execute("INSERT INTO herbs (id, english_name, source, source_record_id) VALUES (1, 'Disputed Herb', 'CCRAS_DRAVYA', 101)")
    conn.execute("INSERT INTO legacy_herb_map (legacy_herb_id, herb_id, created_at) VALUES (1, 1, ?)", (now,))

    cid_ushna = _cid(conn, "VIRYA_USHNA")

    # Disputed claim mapping
    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (10, 101, 'property', 'Virya', 'Ushna?', 'reviewed', 'Dr. Sharma', ?, 'ingest', 'loader', ?, ?)", (now, now, now))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_confidence, mapping_method, verification_status, created_at) VALUES (10, 10, ?, 'disputed', 0.4, 'lexicon_exact', 'reviewed', ?)", (cid_ushna, now))
    conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (10, 1, 10, NULL, 'active', ?)", (now,))
    conn.commit()

    # Default: include_disputed=False
    profile_default = herb_dravyaguna_profile(conn, 1, include_disputed=False)
    assert len(profile_default["properties"]) == 0

    # Explicit: include_disputed=True
    profile_audit = herb_dravyaguna_profile(conn, 1, include_disputed=True)
    assert len(profile_audit["properties"]) == 1
    assert profile_audit["properties"][0]["is_disputed"] is True
    assert profile_audit["properties"][0]["mapping_type"] == "disputed"


# ============================================================================
# Tests: Provisional Concept Quarantine
# ============================================================================

def test_wp5_dravyaguna_profile_provisional_concept_quarantine(v3_db):
    """Provisional concepts are quarantined by default and visible only when include_provisional=True."""
    conn, _ = v3_db
    now = "2026-11-18T12:00:00Z"
    s_id = _source_id(conn, "CCRAS_DRAVYA")

    conn.execute("INSERT INTO source_records (source_record_id, source_id, external_record_key) VALUES (101, ?, '101')", (s_id,))
    conn.execute("INSERT INTO herbs (id, english_name, source, source_record_id) VALUES (1, 'Experimental Herb', 'CCRAS_DRAVYA', 101)")
    conn.execute("INSERT INTO legacy_herb_map (legacy_herb_id, herb_id, created_at) VALUES (1, 1, ?)", (now,))

    # VIRYA_SNIGDHA is a seeded provisional concept in the canonical catalog
    cid_prov = _cid(conn, "VIRYA_SNIGDHA")
    status_row = conn.execute("SELECT status FROM dravyaguna_concepts WHERE concept_id = ?", (cid_prov,)).fetchone()
    assert status_row[0] == "provisional"

    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (20, 101, 'property', 'Virya', 'Snigdha', 'reviewed', 'Dr. Sharma', ?, 'ingest', 'loader', ?, ?)", (now, now, now))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_confidence, mapping_method, verification_status, created_at) VALUES (20, 20, ?, 'exact', 1.0, 'lexicon_exact', 'reviewed', ?)", (cid_prov, now))
    conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (20, 1, 20, NULL, 'active', ?)", (now,))
    conn.commit()

    # Default: include_provisional=False -> Quarantined
    profile_default = herb_dravyaguna_profile(conn, 1, include_provisional=False)
    assert len(profile_default["properties"]) == 0

    # Explicit: include_provisional=True -> Visible
    profile_prov = herb_dravyaguna_profile(conn, 1, include_provisional=True)
    assert len(profile_prov["properties"]) == 1
    assert profile_prov["properties"][0]["concept_code"] == "VIRYA_SNIGDHA"


# ============================================================================
# Tests: Virya Reconciliation Multi-Tier Divergence & Summary Counts
# ============================================================================

def test_wp5_virya_reconciliation_multi_tier_and_counts(v3_db):
    """Tests the 4-tier Virya reconciliation queries, report generation, and deterministic counts."""
    conn, _ = v3_db
    now = "2026-11-18T12:00:00Z"

    # Setup sources
    s1_id = _source_id(conn, "CCRAS_DRAVYA")
    s2_id = _source_id(conn, "API_VOL_1")

    # Fetch canonical Virya & Plant Part concept IDs
    cid_ushna = _cid(conn, "VIRYA_USHNA")
    cid_shita = _cid(conn, "VIRYA_SHITA")
    cid_root = _cid(conn, "PART_ROOT")

    # Setup herbs: Piper longum (Pippali) CCRAS and API
    conn.execute("INSERT INTO source_records (source_record_id, source_id, external_record_key) VALUES (101, ?, '101')", (s1_id,))
    conn.execute("INSERT INTO source_records (source_record_id, source_id, external_record_key) VALUES (201, ?, '201')", (s2_id,))
    conn.execute("INSERT INTO herbs (id, english_name, botanical_name, source, source_record_id) VALUES (1, 'Pippali (CCRAS)', 'Piper longum L.', 'CCRAS_DRAVYA', 101)")
    conn.execute("INSERT INTO legacy_herb_map (legacy_herb_id, herb_id, created_at) VALUES (1, 1, ?)", (now,))
    conn.execute("INSERT INTO herbs (id, english_name, botanical_name, source, source_record_id) VALUES (2, 'Pippali (API)', 'Piper longum L.', 'API_VOL_1', 201)")
    conn.execute("INSERT INTO legacy_herb_map (legacy_herb_id, herb_id, created_at) VALUES (2, 2, ?)", (now,))

    # 1. Tier 1 Unreviewed Divergence
    # Claim 1 (CCRAS) = Ushna (unreviewed), Claim 2 (API) = Shita (unreviewed)
    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at) VALUES (1, 101, 'property', 'Virya', 'Ushna', 'unreviewed', 'system', 'ingest', ?, ?)", (now, now))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, verification_status, created_at) VALUES (1, 1, ?, 'exact', 'lexicon_exact', 'unreviewed', ?)", (cid_ushna, now))
    conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (1, 1, 1, ?, 'active', ?)", (cid_root, now))

    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at) VALUES (2, 201, 'property', 'Virya', 'Shita', 'unreviewed', 'system', 'ingest', ?, ?)", (now, now))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, verification_status, created_at) VALUES (2, 2, ?, 'exact', 'lexicon_exact', 'unreviewed', ?)", (cid_shita, now))
    conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (2, 2, 2, ?, 'active', ?)", (cid_root, now))
    conn.commit()

    report_t1 = reconcile_herb_virya(conn, 1)
    assert report_t1["target_herb_id"] == 1
    assert report_t1["summary_counts"]["tier_1_unreviewed_divergence_count"] == 1
    assert report_t1["summary_counts"]["tier_2_reviewed_divergence_count"] == 0
    assert report_t1["summary_counts"]["tier_3_verified_disagreement_count"] == 0
    assert report_t1["summary_counts"]["same_claim_mapping_ambiguity_count"] == 0
    assert report_t1["summary_counts"]["total_reconciled_pairs"] == 1
    assert len(report_t1["tier_1_unreviewed_divergence"]) == 1
    row_t1 = report_t1["tier_1_unreviewed_divergence"][0]
    assert row_t1["virya_1"] == "VIRYA_USHNA"
    assert row_t1["virya_2"] == "VIRYA_SHITA"
    assert row_t1["claim_1_reviewed_by"] is None

    # 2. Transition to Tier 2 (Reviewed Divergence with approximation)
    conn.execute("UPDATE source_claims SET verification_status = 'reviewed', reviewed_by = 'Dr. Sharma', reviewed_at = ? WHERE source_claim_id IN (1, 2)", (now,))
    conn.execute("UPDATE concept_claim_mappings SET verification_status = 'reviewed', mapping_type = 'broader', reviewed_by = 'Dr. Patel', reviewed_at = ? WHERE mapping_id = 1", (now,))
    conn.execute("UPDATE concept_claim_mappings SET verification_status = 'reviewed', mapping_type = 'exact', reviewed_by = 'Dr. Patel', reviewed_at = ? WHERE mapping_id = 2", (now,))
    conn.commit()

    report_t2 = reconcile_herb_virya(conn, 1)
    assert report_t2["summary_counts"]["tier_1_unreviewed_divergence_count"] == 0
    assert report_t2["summary_counts"]["tier_2_reviewed_divergence_count"] == 1
    assert report_t2["summary_counts"]["tier_3_verified_disagreement_count"] == 0
    assert report_t2["summary_counts"]["total_reconciled_pairs"] == 1

    # 3. Transition to Tier 3 (Verified Source Disagreement)
    conn.execute("UPDATE source_claims SET verification_status = 'verified', reviewed_by = 'Dr. Sharma', reviewed_at = ? WHERE source_claim_id IN (1, 2)", (now,))
    conn.execute("UPDATE concept_claim_mappings SET verification_status = 'verified', mapping_type = 'exact', reviewed_by = 'Dr. Patel', reviewed_at = ? WHERE mapping_id IN (1, 2)", (now,))
    conn.commit()

    report_t3 = reconcile_herb_virya(conn, 1)
    assert report_t3["summary_counts"]["tier_1_unreviewed_divergence_count"] == 0
    assert report_t3["summary_counts"]["tier_2_reviewed_divergence_count"] == 0
    assert report_t3["summary_counts"]["tier_3_verified_disagreement_count"] == 1
    assert report_t3["summary_counts"]["total_reconciled_pairs"] == 1
    row_t3 = report_t3["tier_3_verified_disagreements"][0]
    assert row_t3["claim_1_reviewed_by"] == "Dr. Sharma"
    assert row_t3["mapping_1_verified_by"] == "Dr. Patel"
    assert row_t3["mapping_1_status"] == "verified"
    assert row_t3["mapping_1_type"] == "exact"

    # 4. Add Query 4 Same-Claim Ambiguity
    # Add a second mapping to claim 1 on herb 1 asserting Shita
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, verification_status, reviewed_by, reviewed_at, created_at) VALUES (3, 1, ?, 'exact', 'lexicon_exact', 'verified', 'Dr. Patel', ?, ?)", (cid_shita, now, now))
    conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (3, 1, 3, ?, 'active', ?)", (cid_root, now))
    conn.commit()

    report_ambig = reconcile_herb_virya(conn, 1)
    assert report_ambig["summary_counts"]["same_claim_mapping_ambiguity_count"] == 1
    assert len(report_ambig["same_claim_ambiguities"]) == 1
    ambig_row = report_ambig["same_claim_ambiguities"][0]
    assert ambig_row["source_claim_id"] == 1
    assert ambig_row["virya_1"] == "VIRYA_USHNA"
    assert ambig_row["virya_2"] == "VIRYA_SHITA"
    assert ambig_row["audit_category"] == "HERB_SAME_SOURCE_CLAIM_MAPPING_AMBIGUITY"
    assert report_ambig["summary_counts"]["total_reconciled_pairs"] == (
        report_ambig["summary_counts"]["tier_1_unreviewed_divergence_count"]
        + report_ambig["summary_counts"]["tier_2_reviewed_divergence_count"]
        + report_ambig["summary_counts"]["tier_3_verified_disagreement_count"]
        + report_ambig["summary_counts"]["same_claim_mapping_ambiguity_count"]
    )


# ============================================================================
# Tests: Active Concept Filtering in Virya Reconciliation (ADR Section 9.B.3)
# ============================================================================

def test_wp5_virya_reconciliation_active_concept_filtering(v3_db):
    """The executor contract must filter out divergence rows involving non-active concepts."""
    conn, _ = v3_db
    now = "2026-11-18T12:00:00Z"
    s_id = _source_id(conn, "CCRAS_DRAVYA")

    conn.execute("INSERT INTO source_records (source_record_id, source_id, external_record_key) VALUES (101, ?, '101')", (s_id,))
    conn.execute("INSERT INTO herbs (id, english_name, source, source_record_id) VALUES (1, 'Herb Alpha', 'CCRAS_DRAVYA', 101)")
    conn.execute("INSERT INTO legacy_herb_map (legacy_herb_id, herb_id, created_at) VALUES (1, 1, ?)", (now,))

    # Concept VIRYA_USHNA is active, Concept VIRYA_SNIGDHA is PROVISIONAL
    cid_ushna = _cid(conn, "VIRYA_USHNA")
    cid_snigdha = _cid(conn, "VIRYA_SNIGDHA")
    assert conn.execute("SELECT status FROM dravyaguna_concepts WHERE concept_id = ?", (cid_snigdha,)).fetchone()[0] == "provisional"

    # Single claim with ambiguous mapping
    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at) VALUES (1, 101, 'property', 'Virya', 'Dual', 'unreviewed', 'system', 'ingest', ?, ?)", (now, now))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, verification_status, created_at) VALUES (1, 1, ?, 'exact', 'lexicon_exact', 'unreviewed', ?)", (cid_ushna, now))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, verification_status, created_at) VALUES (2, 1, ?, 'exact', 'lexicon_exact', 'unreviewed', ?)", (cid_snigdha, now))
    conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (1, 1, 1, NULL, 'active', ?)", (now,))
    conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (2, 1, 2, NULL, 'active', ?)", (now,))
    conn.commit()

    # Since VIRYA_SNIGDHA is provisional, the ambiguity row must be filtered out by executor contract!
    report = reconcile_herb_virya(conn, 1)
    assert report["summary_counts"]["same_claim_mapping_ambiguity_count"] == 0
    assert len(report["same_claim_ambiguities"]) == 0

    # Promote VIRYA_SNIGDHA to active
    conn.execute("UPDATE dravyaguna_concepts SET status = 'active' WHERE concept_id = ?", (cid_snigdha,))
    conn.commit()

    report_active = reconcile_herb_virya(conn, 1)
    assert report_active["summary_counts"]["same_claim_mapping_ambiguity_count"] == 1
    assert len(report_active["same_claim_ambiguities"]) == 1


# ============================================================================
# Tests: Database Protection & Invariance
# ============================================================================

def test_wp5_inspection_db_unmutated_v2():
    """Verify that working database data/inspection.db remains strictly at schema version 2 ([1, 2])."""
    db_path = PROJECT_ROOT / "data" / "inspection.db"
    assert db_path.exists(), "data/inspection.db must exist"
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT version FROM schema_migrations ORDER BY rowid ASC").fetchall()
        versions = [r[0] for r in rows]
        assert versions == [1, 2], f"data/inspection.db must remain at schema version [1, 2], got {versions}"
    finally:
        conn.close()
