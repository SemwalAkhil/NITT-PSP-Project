"""
Herbal Almanac — Stage C.2 Work Package 1 (WP-1)
Unit Test Suite for Canonical Concept Catalog, Invariant Validation, and Resolution Helpers
"""

import os
import sqlite3
import tempfile
import sys
from pathlib import Path
import pytest

from herbal_almanac.database_operator import AyurvedicAlmanac
from herbal_almanac.migrations import migration_0003_semantic_dravyaguna
from herbal_almanac.concept_catalog import (
    DOMAIN_PREFIX_MAP,
    CANONICAL_CONCEPTS,
    ConceptSeed,
    LabelSeed,
    CitationSeed,
    validate_concept_code_prefix,
    validate_catalog_dataset,
    seed_canonical_concept_catalog,
    resolve_concept_display_label,
    resolve_concept_sanskrit_references,
)


@pytest.fixture
def v3_db():
    """Provides a fresh, temporary SQLite database initialized to schema version 3."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        # Initialize Stage B base schema (v2)
        almanac = AyurvedicAlmanac(db_path)
        almanac.create_database()
        
        # Connect and upgrade to Stage C (v3) via Migration 3
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


# ============================================================================
# 1. Prefix and Regex Validation Tests
# ============================================================================

def test_prefix_and_regex_validation():
    """Tests validate_concept_code_prefix across valid and invalid inputs."""
    # 1. Valid codes across all 11 domains
    for domain, prefix in DOMAIN_PREFIX_MAP.items():
        valid_code = f"{prefix}TEST_CODE_1"
        validate_concept_code_prefix(valid_code, domain)
    
    # 2. Domain prefix mismatch
    with pytest.raises(ValueError, match="invalid for domain 'rasa'. Expected prefix 'RASA_'"):
        validate_concept_code_prefix("GUNA_MADHURA", "rasa")
    
    with pytest.raises(ValueError, match="invalid for domain 'virya'. Expected prefix 'VIRYA_'"):
        validate_concept_code_prefix("RASA_USHNA", "virya")
    
    # 3. Lowercase characters rejected
    with pytest.raises(ValueError, match="does not match required pattern"):
        validate_concept_code_prefix("rasa_madhura", "rasa")
    
    with pytest.raises(ValueError, match="does not match required pattern"):
        validate_concept_code_prefix("Rasa_Madhura", "rasa")
    
    # 4. Missing underscore rejected
    with pytest.raises(ValueError, match="does not match required pattern"):
        validate_concept_code_prefix("RASAMADHURA", "rasa")
    
    # 5. Unknown domain rejected
    with pytest.raises(ValueError, match="Unknown concept domain 'unknown_domain'"):
        validate_concept_code_prefix("RASA_MADHURA", "unknown_domain")
    
    # 6. Empty strings rejected
    with pytest.raises(ValueError, match="Concept code must be a non-empty string"):
        validate_concept_code_prefix("", "rasa")
    
    with pytest.raises(ValueError, match="Concept domain must be a non-empty string"):
        validate_concept_code_prefix("RASA_MADHURA", "")


# ============================================================================
# 2. Complete Domain Coverage and 1:1 Count Parity Tests
# ============================================================================

def test_domain_coverage_and_counts(v3_db):
    """Verifies complete domain coverage and exact 1:1 count parity between Python dataset and SQLite."""
    conn, _ = v3_db
    
    expected_concepts = len(CANONICAL_CONCEPTS)
    expected_labels = sum(len(c.labels) for c in CANONICAL_CONCEPTS)
    expected_sources = sum(len(c.citations) for c in CANONICAL_CONCEPTS)
    
    # Assert exact dataset definition metrics
    assert expected_concepts == 136
    assert expected_labels == 649, f"Expected 649 labels in dataset, got {expected_labels}"
    assert expected_sources == 136
    
    result = seed_canonical_concept_catalog(conn)
    assert result["concepts"] == expected_concepts
    assert result["labels"] == expected_labels, f"Expected {expected_labels} labels, got {result['labels']}"
    assert result["sources"] == expected_sources
    
    # Verify counts per domain
    cur = conn.cursor()
    cur.execute("SELECT concept_domain, COUNT(*), SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END), SUM(CASE WHEN status = 'provisional' THEN 1 ELSE 0 END) FROM dravyaguna_concepts GROUP BY concept_domain;")
    domain_counts = {row[0]: {"total": row[1], "active": row[2], "provisional": row[3]} for row in cur.fetchall()}
    
    expected_domain_counts = {
        "rasa": {"total": 6, "active": 6, "provisional": 0},
        "guna": {"total": 30, "active": 30, "provisional": 0},
        "virya": {"total": 9, "active": 2, "provisional": 7},
        "vipaka": {"total": 3, "active": 3, "provisional": 0},
        "dosha": {"total": 3, "active": 3, "provisional": 0},
        "dosha_effect": {"total": 2, "active": 2, "provisional": 0},
        "prabhava": {"total": 6, "active": 6, "provisional": 0},
        "karma": {"total": 22, "active": 22, "provisional": 0},
        "plant_part": {"total": 16, "active": 16, "provisional": 0},
        "preparation_form": {"total": 15, "active": 15, "provisional": 0},
        "indication": {"total": 24, "active": 24, "provisional": 0},
    }
    
    assert set(domain_counts.keys()) == set(expected_domain_counts.keys()), "Domain mismatch in seeded catalog!"
    
    for domain, expected in expected_domain_counts.items():
        actual = domain_counts[domain]
        assert actual["total"] == expected["total"], f"Domain {domain} total count mismatch: {actual['total']} != {expected['total']}"
        assert actual["active"] == expected["active"], f"Domain {domain} active count mismatch: {actual['active']} != {expected['active']}"
        assert actual["provisional"] == expected["provisional"], f"Domain {domain} provisional count mismatch: {actual['provisional']} != {expected['provisional']}"


# ============================================================================
# 3. Multilingual and Preferred-Label Invariant Tests
# ============================================================================

def test_multilingual_and_preferred_label_invariant(v3_db):
    """Verifies multilingual representation, single-preferred-label invariant, and duplicate protection."""
    conn, _ = v3_db
    seed_canonical_concept_catalog(conn)
    cur = conn.cursor()
    
    # 1. Check that every concept has at least 4 preferred labels: en/Latn, hi/Deva, sa/Deva, sa/Latn
    cur.execute("""
        SELECT c.concept_code,
               SUM(CASE WHEN l.language_code = 'en' AND l.script_code = 'Latn' AND l.is_preferred = 1 THEN 1 ELSE 0 END) AS en_count,
               SUM(CASE WHEN l.language_code = 'hi' AND l.script_code = 'Deva' AND l.is_preferred = 1 THEN 1 ELSE 0 END) AS hi_count,
               SUM(CASE WHEN l.language_code = 'sa' AND l.script_code = 'Deva' AND l.is_preferred = 1 THEN 1 ELSE 0 END) AS sa_deva_count,
               SUM(CASE WHEN l.language_code = 'sa' AND l.script_code = 'Latn' AND l.is_preferred = 1 THEN 1 ELSE 0 END) AS sa_latn_count
        FROM dravyaguna_concepts c
        JOIN concept_labels l ON c.concept_id = l.concept_id
        GROUP BY c.concept_id
        HAVING en_count != 1 OR hi_count != 1 OR sa_deva_count != 1 OR sa_latn_count != 1;
    """)
    defective_concepts = cur.fetchall()
    assert len(defective_concepts) == 0, f"Found concepts violating multilingual representation: {defective_concepts}"
    
    # 2. Check Single-Preferred-Label invariant across all (concept_id, language_code, script_code)
    cur.execute("""
        SELECT concept_id, language_code, script_code, COUNT(*)
        FROM concept_labels
        WHERE is_preferred = 1
        GROUP BY concept_id, language_code, script_code
        HAVING COUNT(*) > 1;
    """)
    multiple_preferred = cur.fetchall()
    assert len(multiple_preferred) == 0, f"Single-preferred-label invariant violated: {multiple_preferred}"
    
    # 3. Validator rejects concept missing preferred label on a required tuple
    missing_preferred_dataset = [
        ConceptSeed(
            "RASA_TEST_NO_PREF", "rasa", "active", None,
            [
                LabelSeed("en", "Latn", "Sweet", "scholarly_translation", "human_curated", is_preferred=0),  # Not preferred!
                LabelSeed("hi", "Deva", "मधुर", "vernacular_equivalent", "human_curated", is_preferred=1),
                LabelSeed("sa", "Deva", "मधुर", "canonical_sanskrit", "classical_lexicon", is_preferred=1),
                LabelSeed("sa", "Latn", "Madhura", "transliteration", "classical_lexicon", is_preferred=1),
            ],
            [CitationSeed("Test citation")]
        )
    ]
    with pytest.raises(ValueError, match="missing required preferred label for \\('en', 'Latn'\\)"):
        validate_catalog_dataset(missing_preferred_dataset)
    
    # 4. Validator rejects multiple preferred labels on same (language, script)
    multiple_preferred_dataset = [
        ConceptSeed(
            "RASA_TEST_MULTI_PREF", "rasa", "active", None,
            [
                LabelSeed("en", "Latn", "Sweet", "scholarly_translation", "human_curated", is_preferred=1),
                LabelSeed("en", "Latn", "Sugary", "scholarly_translation", "human_curated", is_preferred=1),  # Second preferred!
                LabelSeed("hi", "Deva", "मधुर", "vernacular_equivalent", "human_curated", is_preferred=1),
                LabelSeed("sa", "Deva", "मधुर", "canonical_sanskrit", "classical_lexicon", is_preferred=1),
                LabelSeed("sa", "Latn", "Madhura", "transliteration", "classical_lexicon", is_preferred=1),
            ],
            [CitationSeed("Test citation")]
        )
    ]
    with pytest.raises(ValueError, match="Single-preferred-label invariant violated"):
        validate_catalog_dataset(multiple_preferred_dataset)
    
    # 5. Validator rejects duplicate normalized labels within same concept
    duplicate_norm_dataset = [
        ConceptSeed(
            "RASA_TEST_DUP_NORM", "rasa", "active", None,
            [
                LabelSeed("en", "Latn", "Sweet", "scholarly_translation", "human_curated", is_preferred=1),
                LabelSeed("en", "Latn", "sweet", "synonym", "human_curated", is_preferred=0),  # Duplicate normalized!
                LabelSeed("hi", "Deva", "मधुर", "vernacular_equivalent", "human_curated", is_preferred=1),
                LabelSeed("sa", "Deva", "मधुर", "canonical_sanskrit", "classical_lexicon", is_preferred=1),
                LabelSeed("sa", "Latn", "Madhura", "transliteration", "classical_lexicon", is_preferred=1),
            ],
            [CitationSeed("Test citation")]
        )
    ]
    with pytest.raises(ValueError, match="Duplicate normalized label 'sweet' for \\(en, Latn\\)"):
        validate_catalog_dataset(duplicate_norm_dataset)
    
    # 6. Database-level preferred label conflict rejection on incremental seed
    cur.execute("SELECT concept_id FROM dravyaguna_concepts WHERE concept_code = 'RASA_MADHURA';")
    madhura_id = cur.fetchone()[0]
    
    conflict_dataset = [
        ConceptSeed(
            "RASA_MADHURA", "rasa", "active", None,
            [
                LabelSeed("en", "Latn", "Sugary", "scholarly_translation", "human_curated", is_preferred=1),  # Conflicts with existing 'Sweet'!
                LabelSeed("hi", "Deva", "मधुर", "vernacular_equivalent", "human_curated", is_preferred=1),
                LabelSeed("sa", "Deva", "मधुर", "canonical_sanskrit", "classical_lexicon", is_preferred=1),
                LabelSeed("sa", "Latn", "Madhura", "transliteration", "classical_lexicon", is_preferred=1),
            ],
            [CitationSeed("Test citation")]
        )
    ]
    with pytest.raises(ValueError, match="Single-preferred-label database conflict for concept RASA_MADHURA"):
        seed_canonical_concept_catalog(conn, dataset=conflict_dataset)


# ============================================================================
# 4. Parent Hierarchy Validation and Seeding Tests
# ============================================================================

def test_parent_hierarchy_validation_and_seeding(v3_db):
    """Verifies parent concept validation, cycle detection, and hierarchy resolution."""
    conn, _ = v3_db
    
    # 1. Cross-domain parent rejection
    cross_domain_dataset = [
        ConceptSeed(
            "RASA_PARENT", "rasa", "active", None,
            [
                LabelSeed("en", "Latn", "Parent", "scholarly_translation", "human_curated", 1),
                LabelSeed("hi", "Deva", "पैरेंट", "vernacular_equivalent", "human_curated", 1),
                LabelSeed("sa", "Deva", "पैरेंट", "canonical_sanskrit", "classical_lexicon", 1),
                LabelSeed("sa", "Latn", "Parent", "transliteration", "classical_lexicon", 1),
            ],
            [CitationSeed("Citation")]
        ),
        ConceptSeed(
            "GUNA_CHILD", "guna", "active", "RASA_PARENT",  # GUNA referencing RASA!
            [
                LabelSeed("en", "Latn", "Child", "scholarly_translation", "human_curated", 1),
                LabelSeed("hi", "Deva", "चाइल्ड", "vernacular_equivalent", "human_curated", 1),
                LabelSeed("sa", "Deva", "चाइल्ड", "canonical_sanskrit", "classical_lexicon", 1),
                LabelSeed("sa", "Latn", "Child", "transliteration", "classical_lexicon", 1),
            ],
            [CitationSeed("Citation")]
        )
    ]
    with pytest.raises(ValueError, match="in domain 'guna' has parent RASA_PARENT in different domain 'rasa'"):
        validate_catalog_dataset(cross_domain_dataset)
    
    # 2. Self-referential parent rejection
    self_ref_dataset = [
        ConceptSeed(
            "RASA_SELF", "rasa", "active", "RASA_SELF",
            [
                LabelSeed("en", "Latn", "Self", "scholarly_translation", "human_curated", 1),
                LabelSeed("hi", "Deva", "सेल्फ", "vernacular_equivalent", "human_curated", 1),
                LabelSeed("sa", "Deva", "सेल्फ", "canonical_sanskrit", "classical_lexicon", 1),
                LabelSeed("sa", "Latn", "Self", "transliteration", "classical_lexicon", 1),
            ],
            [CitationSeed("Citation")]
        )
    ]
    with pytest.raises(ValueError, match="cannot reference itself as parent"):
        validate_catalog_dataset(self_ref_dataset)
    
    # 3. Cycle detection rejection
    cycle_dataset = [
        ConceptSeed(
            "RASA_A", "rasa", "active", "RASA_B",
            [
                LabelSeed("en", "Latn", "A", "scholarly_translation", "human_curated", 1),
                LabelSeed("hi", "Deva", "ए", "vernacular_equivalent", "human_curated", 1),
                LabelSeed("sa", "Deva", "ए", "canonical_sanskrit", "classical_lexicon", 1),
                LabelSeed("sa", "Latn", "A", "transliteration", "classical_lexicon", 1),
            ],
            [CitationSeed("Citation")]
        ),
        ConceptSeed(
            "RASA_B", "rasa", "active", "RASA_A",
            [
                LabelSeed("en", "Latn", "B", "scholarly_translation", "human_curated", 1),
                LabelSeed("hi", "Deva", "बी", "vernacular_equivalent", "human_curated", 1),
                LabelSeed("sa", "Deva", "बी", "canonical_sanskrit", "classical_lexicon", 1),
                LabelSeed("sa", "Latn", "B", "transliteration", "classical_lexicon", 1),
            ],
            [CitationSeed("Citation")]
        )
    ]
    with pytest.raises(ValueError, match="Cycle detected in parent hierarchy"):
        validate_catalog_dataset(cycle_dataset)
    
    # 4. Valid parent hierarchy resolution in database
    valid_hier_dataset = [
        ConceptSeed(
            "RASA_PARENT_VALID", "rasa", "active", None,
            [
                LabelSeed("en", "Latn", "Parent", "scholarly_translation", "human_curated", 1),
                LabelSeed("hi", "Deva", "पैरेंट", "vernacular_equivalent", "human_curated", 1),
                LabelSeed("sa", "Deva", "पैरेंट", "canonical_sanskrit", "classical_lexicon", 1),
                LabelSeed("sa", "Latn", "Parent", "transliteration", "classical_lexicon", 1),
            ],
            [CitationSeed("Citation")]
        ),
        ConceptSeed(
            "RASA_CHILD_VALID", "rasa", "active", "RASA_PARENT_VALID",
            [
                LabelSeed("en", "Latn", "Child", "scholarly_translation", "human_curated", 1),
                LabelSeed("hi", "Deva", "चाइल्ड", "vernacular_equivalent", "human_curated", 1),
                LabelSeed("sa", "Deva", "चाइल्ड", "canonical_sanskrit", "classical_lexicon", 1),
                LabelSeed("sa", "Latn", "Child", "transliteration", "classical_lexicon", 1),
            ],
            [CitationSeed("Citation")]
        )
    ]
    validate_catalog_dataset(valid_hier_dataset)
    seed_canonical_concept_catalog(conn, dataset=valid_hier_dataset)
    
    cur = conn.cursor()
    cur.execute("SELECT concept_id, parent_concept_id FROM dravyaguna_concepts WHERE concept_code = 'RASA_CHILD_VALID';")
    child_id, parent_id = cur.fetchone()
    cur.execute("SELECT concept_id FROM dravyaguna_concepts WHERE concept_code = 'RASA_PARENT_VALID';")
    expected_parent_id = cur.fetchone()[0]
    assert parent_id == expected_parent_id, "parent_concept_id not resolved properly in database!"


# ============================================================================
# 5. Citation Coverage and Enum Whitelists Tests
# ============================================================================

def test_citation_coverage(v3_db):
    """Verifies authoritative citation coverage and enum validation."""
    conn, _ = v3_db
    seed_canonical_concept_catalog(conn)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT c.concept_id, c.concept_code
        FROM dravyaguna_concepts c
        LEFT JOIN concept_labels l ON c.concept_id = l.concept_id
        LEFT JOIN concept_label_sources s ON l.concept_label_id = s.concept_label_id
        GROUP BY c.concept_id
        HAVING COUNT(s.label_source_id) = 0;
    """)
    missing_citations = cur.fetchall()
    assert len(missing_citations) == 0, f"Concepts missing authoritative citations: {missing_citations}"
    
    # Verify non-empty authority_citation string
    cur.execute("SELECT COUNT(*) FROM concept_label_sources WHERE TRIM(authority_citation) = '';")
    empty_citations = cur.fetchone()[0]
    assert empty_citations == 0, "Found empty authority citations in concept_label_sources!"


# ============================================================================
# 6. DDL Trigger Compatibility Tests
# ============================================================================

def test_ddl_trigger_compatibility(v3_db):
    """Verifies label verification trigger behavior and initial unreviewed status."""
    conn, _ = v3_db
    seed_canonical_concept_catalog(conn)
    cur = conn.cursor()
    
    # 1. All seeded labels must have verification_status = 'unreviewed' with verified_by/at IS NULL
    cur.execute("SELECT COUNT(*) FROM concept_labels WHERE verification_status != 'unreviewed' OR verified_by IS NOT NULL OR verified_at IS NOT NULL;")
    premature_verified = cur.fetchone()[0]
    assert premature_verified == 0, "All seeded labels must start as 'unreviewed' with NULL verification metadata!"
    
    # 2. Direct insert of a verified label MUST be blocked by trg_validate_label_verification_insert
    cur.execute("SELECT concept_id FROM dravyaguna_concepts WHERE concept_code = 'RASA_MADHURA';")
    concept_id = cur.fetchone()[0]
    
    with pytest.raises(sqlite3.IntegrityError, match="Label Verification Error: New labels cannot be inserted directly as verified"):
        conn.execute("""
            INSERT INTO concept_labels (
                concept_id, language_code, script_code, label_text,
                normalized_label, label_type, translation_origin,
                verification_status, verified_by, verified_at, is_preferred
            ) VALUES (?, 'en', 'Latn', 'Direct Verified', 'direct verified', 'scholarly_translation', 'human_curated', 'verified', 'Curator 1', '2026-11-19T00:00:00Z', 0)
        """, (concept_id,))
    
    # 3. Updating an unreviewed label to verified succeeds when verified_by, verified_at, and verified citation exist
    cur.execute("""
        INSERT INTO concept_labels (
            concept_id, language_code, script_code, label_text,
            normalized_label, label_type, translation_origin,
            verification_status, is_preferred
        ) VALUES (?, 'en', 'Latn', 'Verified Candidate', 'verified candidate', 'scholarly_translation', 'human_curated', 'unreviewed', 0);
    """, (concept_id,))
    label_id = cur.lastrowid
    
    # Attempting to update to 'verified' without a verified citation fails
    with pytest.raises(sqlite3.IntegrityError, match="A label cannot be verified without at least one valid verified citation"):
        conn.execute("""
            UPDATE concept_labels
            SET verification_status = 'verified', verified_by = 'Curator 1', verified_at = '2026-11-19T00:00:00Z'
            WHERE concept_label_id = ?
        """, (label_id,))
    
    # Attach a verified citation
    conn.execute("""
        INSERT INTO concept_label_sources (
            concept_label_id, authority_citation, citation_type, verified_by, verified_at
        ) VALUES (?, 'Caraka Samhita, Sutrasthana 26', 'classical_text', 'Curator 1', '2026-11-19T00:00:00Z');
    """, (label_id,))
    
    # Now updating to verified succeeds
    conn.execute("""
        UPDATE concept_labels
        SET verification_status = 'verified', verified_by = 'Curator 1', verified_at = '2026-11-19T00:00:00Z'
        WHERE concept_label_id = ?
    """, (label_id,))
    
    cur.execute("SELECT verification_status FROM concept_labels WHERE concept_label_id = ?", (label_id,))
    assert cur.fetchone()[0] == "verified"


# ============================================================================
# 7. Display Label and Sanskrit Resolution Tests
# ============================================================================

def test_display_label_and_sanskrit_resolution(v3_db):
    """Verifies label resolution priority, fallback to concept_code, and strict quarantine rules."""
    conn, _ = v3_db
    seed_canonical_concept_catalog(conn)
    cur = conn.cursor()
    
    # Find active concept (RASA_MADHURA)
    cur.execute("SELECT concept_id FROM dravyaguna_concepts WHERE concept_code = 'RASA_MADHURA';")
    madhura_id = cur.fetchone()[0]
    
    # 1. Normal English resolution: exposes display_label and display_label_status
    lbl_en = resolve_concept_display_label(conn, madhura_id, language="en")
    assert lbl_en is not None
    assert lbl_en["language_code"] == "en"
    assert lbl_en["label_text"] == "Sweet"
    assert lbl_en["display_label"] == "Sweet"
    assert lbl_en["display_label_status"] == "unreviewed"
    assert lbl_en["is_fallback"] is False
    
    # 2. Hindi resolution
    lbl_hi = resolve_concept_display_label(conn, madhura_id, language="hi")
    assert lbl_hi is not None
    assert lbl_hi["language_code"] == "hi"
    assert lbl_hi["display_label"] == "मधुर"
    assert lbl_hi["is_fallback"] is False
    
    # 3. Sanskrit references for active concept
    sk_refs = resolve_concept_sanskrit_references(conn, madhura_id)
    assert sk_refs["canonical_sanskrit_deva"] == "मधुर"
    assert sk_refs["canonical_sanskrit_iast"] == "Madhura"
    
    # 4. Fallback to concept_code when all labels are disputed or rejected
    cur.execute("UPDATE concept_labels SET verification_status = 'disputed' WHERE concept_id = ?;", (madhura_id,))
    lbl_fallback = resolve_concept_display_label(conn, madhura_id, language="en")
    assert lbl_fallback is not None
    assert lbl_fallback["display_label"] == "RASA_MADHURA"
    assert lbl_fallback["label_text"] == "RASA_MADHURA"
    assert lbl_fallback["display_label_status"] == "unreviewed"
    assert lbl_fallback["is_fallback"] is True
    assert lbl_fallback["concept_label_id"] is None
    
    # 5. Quarantine of deprecated concepts in both helpers
    conn.execute("UPDATE dravyaguna_concepts SET status = 'deprecated' WHERE concept_id = ?;", (madhura_id,))
    # resolve_concept_display_label returns None even when allow_provisional=True
    assert resolve_concept_display_label(conn, madhura_id, allow_provisional=True) is None
    assert resolve_concept_display_label(conn, madhura_id, allow_provisional=False) is None
    # resolve_concept_sanskrit_references returns None for both references
    sk_dep = resolve_concept_sanskrit_references(conn, madhura_id, allow_provisional=True)
    assert sk_dep["canonical_sanskrit_deva"] is None
    assert sk_dep["canonical_sanskrit_iast"] is None
    
    # 6. Quarantine of provisional concepts in both helpers
    cur.execute("SELECT concept_id FROM dravyaguna_concepts WHERE concept_code = 'VIRYA_MRIDU';")
    mridu_id = cur.fetchone()[0]
    
    # By default (allow_provisional=False), returns None
    assert resolve_concept_display_label(conn, mridu_id, language="en", allow_provisional=False) is None
    sk_prov_quarantined = resolve_concept_sanskrit_references(conn, mridu_id, allow_provisional=False)
    assert sk_prov_quarantined["canonical_sanskrit_deva"] is None
    assert sk_prov_quarantined["canonical_sanskrit_iast"] is None
    
    # When allow_provisional=True, label and Sanskrit references are resolved
    lbl_prov = resolve_concept_display_label(conn, mridu_id, language="en", allow_provisional=True)
    assert lbl_prov is not None
    assert lbl_prov["display_label"] == "Soft Potency"
    assert lbl_prov["is_fallback"] is False
    
    sk_prov_allowed = resolve_concept_sanskrit_references(conn, mridu_id, allow_provisional=True)
    assert sk_prov_allowed["canonical_sanskrit_deva"] == "मृदु"
    assert sk_prov_allowed["canonical_sanskrit_iast"] == "Mṛdu"


# ============================================================================
# 8. Seed Idempotency, Timestamp Validation, and Caller Transaction Safety
# ============================================================================

def test_seed_idempotency_and_transaction_safety(v3_db):
    """Verifies seed idempotency, strict UTC timestamp validation, and savepoint rollback safety."""
    conn, _ = v3_db
    
    # 1. Strict UTC timestamp validation: rejects non-UTC timezone offsets
    with pytest.raises(ValueError, match="Timestamp must be in UTC"):
        seed_canonical_concept_catalog(conn, now="2026-11-19T02:00:00+05:30")
    
    with pytest.raises(ValueError, match="Timestamp must be in UTC"):
        seed_canonical_concept_catalog(conn, now="2026-11-19T02:00:00")  # Naive
    
    # 2. Initial seed with valid UTC timestamp
    valid_utc_now = "2026-11-19T02:00:00Z"
    run1 = seed_canonical_concept_catalog(conn, now=valid_utc_now)
    assert run1["concepts"] == 136
    assert run1["labels"] == 649
    assert run1["sources"] == 136
    
    # 3. Second run inserts 0 duplicate rows
    run2 = seed_canonical_concept_catalog(conn, now=valid_utc_now)
    assert run2["concepts"] == 0
    assert run2["labels"] == 0
    assert run2["sources"] == 0
    
    # 4. Caller-managed transaction (BEGIN IMMEDIATE) is NOT auto-committed by seeder
    # Start caller-managed transaction
    conn.execute("BEGIN IMMEDIATE;")
    assert conn.in_transaction is True
    
    # Run seeder inside caller transaction
    run3 = seed_canonical_concept_catalog(conn, now=valid_utc_now)
    assert run3["concepts"] == 0
    
    # Transaction remains active (not committed by seeder!)
    assert conn.in_transaction is True
    
    # Insert a test record within the caller transaction
    conn.execute("""
        INSERT INTO dravyaguna_concepts (concept_code, concept_domain, status, created_at)
        VALUES ('RASA_CALLER_TX', 'rasa', 'active', '2026-11-19T02:00:00Z');
    """)
    
    # Caller rolls back outer transaction
    conn.rollback()
    assert conn.in_transaction is False
    
    # Verify rolled back
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM dravyaguna_concepts WHERE concept_code = 'RASA_CALLER_TX';")
    assert cur.fetchone()[0] == 0, "Caller transaction rollback was not preserved!"
