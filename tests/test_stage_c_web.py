"""Herbal Almanac — Stage C.2 Work Package 6 (WP-6)
Unit & Integration Test Suite for Web Application GUI Routing & Presentation Services

Tests:
1. Version 2 baseline behavior: legacy detail views + feature unavailability banner
2. Version 2 API endpoints: returns 501 FeatureUnavailableError
3. Version 3 status & capability detection
4. Version 3 enhanced semantic herb detail page with Dravyaguna properties & Sanskrit terms
5. Version 3 multilingual language query parameter (en vs hi)
6. Version 3 Virya reconciliation GUI dashboard
7. Version 3 JSON API endpoints (/api/stage-c/herbs/{id}/profile & reconciliation)
8. Missing herb 404 error handling across HTML and API routes
9. Inspection DB protection check (remains strictly at schema version 2)
"""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent

from herbal_almanac.database_operator import AyurvedicAlmanac
from herbal_almanac.migrations import migration_0003_semantic_dravyaguna
from herbal_almanac.concept_catalog import seed_canonical_concept_catalog
from herbal_almanac.web_app import create_app as create_stage_c_app, get_database_capability


# ============================================================================
# Fixtures & Helpers
# ============================================================================

@pytest.fixture
def v2_setup(tmp_path):
    """Provides a temporary, fresh Version 2 SQLite database and TestClient."""
    db_path = tmp_path / "test_v2.db"
    almanac = AyurvedicAlmanac(db_path)
    almanac.create_database()

    app = create_stage_c_app(db_path)
    client = TestClient(app)
    return client, almanac, db_path


@pytest.fixture
def v3_setup(tmp_path):
    """Provides a temporary, fresh Version 3 SQLite database with seeded catalog and TestClient."""
    db_path = tmp_path / "test_v3.db"
    almanac = AyurvedicAlmanac(db_path)
    almanac.create_database()

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    migration_0003_semantic_dravyaguna.apply_migration(conn)
    seed_canonical_concept_catalog(conn)
    conn.close()

    app = create_stage_c_app(db_path)
    client = TestClient(app)
    return client, almanac, db_path


def _cid(conn: sqlite3.Connection, concept_code: str) -> int:
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


def _seed_semantic_herb_fixtures(db_path: Path) -> int:
    """Seeds a representative Stage C herb with Dravyaguna properties and reconciliation data."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    now = "2026-11-19T12:00:00Z"

    # Fetch source IDs
    s_id = _source_id(conn, "CCRAS_DRAVYA")
    s2_id = _source_id(conn, "API_VOL_1")

    # Source records & Herbs
    conn.execute("INSERT INTO source_records (source_record_id, source_id, external_record_key) VALUES (101, ?, '101')", (s_id,))
    conn.execute("INSERT INTO source_records (source_record_id, source_id, external_record_key) VALUES (201, ?, '201')", (s2_id,))

    conn.execute("INSERT INTO herbs (id, english_name, botanical_name, family, source, source_record_id) VALUES (1, 'Pippali (CCRAS)', 'Piper longum L.', 'Piperaceae', 'CCRAS_DRAVYA', 101)")
    conn.execute("INSERT INTO legacy_herb_map (legacy_herb_id, herb_id, created_at) VALUES (1, 1, ?)", (now,))

    conn.execute("INSERT INTO herbs (id, english_name, botanical_name, family, source, source_record_id) VALUES (2, 'Pippali (API)', 'Piper longum L.', 'Piperaceae', 'API_VOL_1', 201)")
    conn.execute("INSERT INTO legacy_herb_map (legacy_herb_id, herb_id, created_at) VALUES (2, 2, ?)", (now,))

    # Concept IDs
    cid_katu = _cid(conn, "RASA_KATU")
    cid_ushna = _cid(conn, "VIRYA_USHNA")
    cid_shita = _cid(conn, "VIRYA_SHITA")
    cid_root = _cid(conn, "PART_ROOT")
    cid_kapha = _cid(conn, "DOSHA_KAPHA")
    cid_decrease = _cid(conn, "EFFECT_DECREASE")
    cid_churna = _cid(conn, "PREP_CHURNA")
    cid_kasa = _cid(conn, "IND_KASA")

    # 1. Properties: Rasa Katu & Virya Ushna on Root
    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (1, 101, 'property', 'Rasa', 'Katu', 'reviewed', 'Dr. Sharma', ?, 'ingest', 'loader', ?, ?)", (now, now, now))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_confidence, mapping_method, verification_status, created_at) VALUES (1, 1, ?, 'exact', 1.0, 'lexicon_exact', 'reviewed', ?)", (cid_katu, now))
    conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (1, 1, 1, ?, 'active', ?)", (cid_root, now))

    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (2, 101, 'property', 'Virya', 'Ushna', 'reviewed', 'Dr. Sharma', ?, 'ingest', 'loader', ?, ?)", (now, now, now))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_confidence, mapping_method, verification_status, created_at) VALUES (2, 2, ?, 'exact', 1.0, 'lexicon_exact', 'reviewed', ?)", (cid_ushna, now))
    conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (2, 1, 2, ?, 'active', ?)", (cid_root, now))

    # 2. Competing claim for Virya Shita on Herb 2 (Divergence with Herb 1)
    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at) VALUES (3, 201, 'property', 'Virya', 'Shita', 'unreviewed', 'system', 'ingest', ?, ?)", (now, now))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_confidence, mapping_method, verification_status, created_at) VALUES (3, 3, ?, 'exact', 1.0, 'lexicon_exact', 'unreviewed', ?)", (cid_shita, now))
    conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (3, 2, 3, ?, 'active', ?)", (cid_root, now))

    # 3. Dosha Effect
    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (4, 101, 'dosha_effect', 'Dosha', 'Kapha-shamana', 'reviewed', 'Dr. Sharma', ?, 'ingest', 'loader', ?, ?)", (now, now, now))
    conn.execute("INSERT INTO dosha_claim_assertions (dosha_assertion_id, source_claim_id, dosha_concept_id, effect_concept_id, mapping_confidence, mapping_method, verification_status, created_at) VALUES (1, 4, ?, ?, 1.0, 'rule_normalizer', 'reviewed', ?)", (cid_kapha, cid_decrease, now))
    conn.execute("INSERT INTO herb_dosha_effects (herb_dosha_effect_id, herb_id, dosha_assertion_id, source_presence_status, created_at) VALUES (1, 1, 1, 'active', ?)", (now,))

    # 4. Preparation & Part
    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (5, 101, 'preparation', 'Form', 'Churna', 'reviewed', 'Dr. Sharma', ?, 'ingest', 'loader', ?, ?)", (now, now, now))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_confidence, mapping_method, verification_status, created_at) VALUES (4, 5, ?, 'exact', 1.0, 'lexicon_exact', 'reviewed', ?)", (cid_churna, now))
    conn.execute("INSERT INTO herb_preparations (herb_preparation_id, herb_id, prep_mapping_id, part_mapping_id, source_presence_status, created_at) VALUES (1, 1, 4, NULL, 'active', ?)", (now,))

    # 4b. Officinal Plant Part
    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (7, 101, 'plant_part', 'Part', 'Mula', 'reviewed', 'Dr. Sharma', ?, 'ingest', 'loader', ?, ?)", (now, now, now))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_confidence, mapping_method, verification_status, created_at) VALUES (6, 7, ?, 'exact', 1.0, 'lexicon_exact', 'reviewed', ?)", (cid_root, now))
    conn.execute("INSERT INTO herb_plant_parts (herb_part_id, herb_id, mapping_id, source_presence_status, created_at) VALUES (1, 1, 6, 'active', ?)", (now,))

    # 5. Indication
    conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (6, 101, 'indication', 'Indication', 'Kasa', 'reviewed', 'Dr. Sharma', ?, 'ingest', 'loader', ?, ?)", (now, now, now))
    conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_confidence, mapping_method, verification_status, created_at) VALUES (5, 6, ?, 'exact', 1.0, 'lexicon_exact', 'reviewed', ?)", (cid_kasa, now))
    conn.execute("INSERT INTO herb_indications (herb_indication_id, herb_id, mapping_id, source_presence_status, created_at) VALUES (1, 1, 5, 'active', ?)", (now,))

    conn.commit()
    conn.close()
    return 1


# ============================================================================
# 1. Tests: Schema Version 2 Baseline & Capability Degradation
# ============================================================================

def test_wp6_v2_herb_detail_renders_legacy_plus_unavailability_banner(v2_setup):
    """On Schema Version 2, /herbs/{id} renders legacy views plus an informative capability banner."""
    client, almanac, _ = v2_setup
    herb_id = almanac.add_herb("Tulsi", botanical_name="Ocimum tenuiflorum", family="Lamiaceae")

    response = client.get(f"/herbs/{herb_id}")
    assert response.status_code == 200
    assert "Tulsi" in response.text
    assert "Ocimum tenuiflorum" in response.text
    assert "STAGE C CAPABILITY STATUS" in response.text
    assert "Stage C normalized semantic features require schema version 3 (current database version is 2)" in response.text
    assert "Dravyaguna Properties (Rasa, Guna, Virya, Vipaka, Prabhava, Karma)" not in response.text


def test_wp6_v2_virya_reconciliation_returns_501(v2_setup):
    """On Schema Version 2, accessing /stage-c/reconciliation/{id} returns HTTP 501."""
    client, almanac, _ = v2_setup
    herb_id = almanac.add_herb("Tulsi")

    response = client.get(f"/stage-c/reconciliation/{herb_id}")
    assert response.status_code == 501
    assert "Stage C normalized semantic features require schema version 3" in response.text


def test_wp6_v2_api_status_reports_version_2(v2_setup):
    """GET /api/stage-c/status accurately reports Version 2 and unavailable features."""
    client, _, _ = v2_setup
    response = client.get("/api/stage-c/status")
    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == 2
    assert data["stage_c_available"] is False
    assert data["ledger"] == [1, 2]


def test_wp6_v2_api_profile_and_reconciliation_return_501(v2_setup):
    """On Schema Version 2, calling semantic API endpoints returns HTTP 501."""
    client, almanac, _ = v2_setup
    herb_id = almanac.add_herb("Tulsi")

    resp_prof = client.get(f"/api/stage-c/herbs/{herb_id}/profile")
    assert resp_prof.status_code == 501
    assert "Stage C normalized semantic features require schema version 3" in resp_prof.json()["detail"]

    resp_recon = client.get(f"/api/stage-c/herbs/{herb_id}/reconciliation")
    assert resp_recon.status_code == 501
    assert "Stage C normalized semantic features require schema version 3" in resp_recon.json()["detail"]


# ============================================================================
# 2. Tests: Schema Version 3 Semantic Enhancement
# ============================================================================

def test_wp6_v3_api_status_reports_version_3(v3_setup):
    """GET /api/stage-c/status reports Version 3 and unlocked capability."""
    client, _, _ = v3_setup
    response = client.get("/api/stage-c/status")
    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == 3
    assert data["stage_c_available"] is True
    assert data["ledger"] == [1, 2, 3]


def test_wp6_v3_herb_detail_renders_enhanced_semantic_card(v3_setup):
    """On Schema Version 3, /herbs/{id} renders enhanced Dravyaguna properties and Sanskrit terms."""
    client, _, db_path = v3_setup
    herb_id = _seed_semantic_herb_fixtures(db_path)

    response = client.get(f"/herbs/{herb_id}")
    assert response.status_code == 200
    # Plant identity
    assert "Pippali (CCRAS)" in response.text
    assert "Piper longum L." in response.text
    # Capability banner should NOT be present on v3
    assert "STAGE C CAPABILITY STATUS" not in response.text
    # Semantic model card
    assert "Dravyaguna Properties" in response.text
    assert "RASA_KATU" in response.text
    assert "Pungent" in response.text
    assert "कटु" in response.text  # Sanskrit Devanagari
    assert "Kaṭu" in response.text  # Sanskrit IAST
    # Formulations & indications
    assert "PREP_CHURNA" in response.text
    assert "Cough" in response.text
    # Plant parts
    assert "Used Plant Parts" in response.text
    assert "PART_ROOT" in response.text
    assert "Root" in response.text
    # Virya consensus summary
    assert "Virya Consensus" in response.text
    assert "Inspect Virya Reconciliation ↗" in response.text


def test_wp6_corrupt_ledger_returns_500(v2_setup):
    """When the schema_migrations ledger is corrupted or invalid, endpoints return HTTP 500."""
    client, almanac, db_path = v2_setup
    herb_id = almanac.add_herb("CorruptHerb")

    # Corrupt the ledger: insert version 4 directly (sequence becomes [1, 2, 4])
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO schema_migrations (version, name, applied_at) VALUES (4, 'future_migration', '2026-11-19T00:00:00Z')")
    conn.commit()
    conn.close()

    resp_prof = client.get(f"/api/stage-c/herbs/{herb_id}/profile")
    assert resp_prof.status_code == 500
    assert "Database migration ledger error" in resp_prof.json()["detail"]
    assert "Unsupported database schema migration ledger" in resp_prof.json()["detail"]

    resp_recon = client.get(f"/api/stage-c/herbs/{herb_id}/reconciliation")
    assert resp_recon.status_code == 500
    assert "Database migration ledger error" in resp_recon.json()["detail"]

    resp_gui = client.get(f"/stage-c/reconciliation/{herb_id}")
    assert resp_gui.status_code == 500
    assert "Database migration ledger error" in resp_gui.json()["detail"]


def test_wp6_v3_multilingual_language_parameter(v3_setup):
    """Passing ?language=hi resolves Hindi display labels in the rendered HTML."""
    client, _, db_path = v3_setup
    herb_id = _seed_semantic_herb_fixtures(db_path)

    response = client.get(f"/herbs/{herb_id}?language=hi")
    assert response.status_code == 200
    assert "कटु" in response.text


def test_wp6_v3_virya_reconciliation_dashboard(v3_setup):
    """GET /stage-c/reconciliation/{id} renders the full reconciliation dashboard."""
    client, _, db_path = v3_setup
    herb_id = _seed_semantic_herb_fixtures(db_path)

    response = client.get(f"/stage-c/reconciliation/{herb_id}")
    assert response.status_code == 200
    assert "STAGE C CROSS-SOURCE RECONCILIATION" in response.text
    assert "Summary Statistics" in response.text
    assert "Unreviewed Candidate Divergences" in response.text
    assert "Total Pairs: 1" in response.text


def test_wp6_v3_api_endpoints_return_json(v3_setup):
    """GET /api/stage-c/herbs/{id}/profile & /reconciliation return structured JSON."""
    client, _, db_path = v3_setup
    herb_id = _seed_semantic_herb_fixtures(db_path)

    # Profile API
    resp_prof = client.get(f"/api/stage-c/herbs/{herb_id}/profile")
    assert resp_prof.status_code == 200
    prof = resp_prof.json()
    assert prof["herb_id"] == herb_id
    assert len(prof["properties"]) >= 2
    assert len(prof["dosha_effects"]) == 1
    assert len(prof["preparations"]) == 1
    assert len(prof["indications"]) == 1

    # Reconciliation API
    resp_recon = client.get(f"/api/stage-c/herbs/{herb_id}/reconciliation")
    assert resp_recon.status_code == 200
    recon = resp_recon.json()
    assert recon["target_herb_id"] == herb_id
    assert recon["summary_counts"]["total_reconciled_pairs"] == 1
    assert recon["summary_counts"]["tier_1_unreviewed_divergence_count"] == 1


# ============================================================================
# 3. Tests: Missing Herb & Error Handling (404)
# ============================================================================

def test_wp6_missing_herb_returns_404(v3_setup):
    """Querying an unknown herb returns HTTP 404 across both HTML and JSON routes."""
    client, _, _ = v3_setup

    assert client.get("/herbs/9999").status_code == 404
    assert client.get("/stage-c/reconciliation/9999").status_code == 404
    assert client.get("/api/stage-c/herbs/9999/profile").status_code == 404
    assert client.get("/api/stage-c/herbs/9999/reconciliation").status_code == 404


# ============================================================================
# 4. Tests: Working Database Protection & Invariance
# ============================================================================

def test_wp6_inspection_db_unmutated_v2():
    """Verify that working database data/inspection.db remains strictly at schema version 2 ([1, 2])."""
    db_path = PROJECT_ROOT / "data" / "inspection.db"
    if not db_path.exists():
        pytest.skip("Local-only safeguard: data/inspection.db is not present in this environment.")
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT version FROM schema_migrations ORDER BY rowid ASC").fetchall()
        versions = [r[0] for r in rows]
        assert versions == [1, 2], f"data/inspection.db must remain at schema version [1, 2], got {versions}"
    finally:
        conn.close()
