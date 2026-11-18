import os
import sys
import time
import sqlite3
import hashlib
import tempfile
from pathlib import Path

from herbal_almanac.database_operator import AyurvedicAlmanac
from herbal_almanac.cleaning import PlantRecord
from herbal_almanac.migrations import migration_0003_semantic_dravyaguna as migration_3
from herbal_almanac.repository_api import RECONCILIATION_SQL_PATH

DDL_FILE = migration_3.DDL_FILE
RECONCILIATION_FILE = RECONCILIATION_SQL_PATH
STAGE_C_SQL = DDL_FILE.read_text(encoding="utf-8")
RECONCILIATION_SQL = RECONCILIATION_FILE.read_text(encoding="utf-8")

# Extract individual queries from virya_reconciliation.sql
queries = [q.strip() for q in RECONCILIATION_SQL.split(";") if "SELECT" in q]
VIRYA_UNREVIEWED_DIVERGENCE_SQL = queries[0]
VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL = queries[1]
VIRYA_VERIFIED_DISAGREEMENT_SQL = queries[2]
VIRYA_MAPPING_AMBIGUITY_SQL = queries[3]

def execute_statements(conn, script):
    buffer = ""
    for line in script.splitlines():
        buffer += line + "\n"
        if sqlite3.complete_statement(buffer):
            stmt = buffer.strip()
            buffer = ""
            if stmt:
                conn.execute(stmt)

def get_actual_stage_b_connection(db_path=None):
    """Initializes and returns an actual Stage B database via AyurvedicAlmanac."""
    if db_path is None:
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
    almanac = AyurvedicAlmanac(db_path)
    almanac.create_database()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn, db_path

# ============================================================================
# TEST SUITE 1: ACTUAL STAGE B SCHEMA COMPATIBILITY & APPLIED DDL
# ============================================================================
def test_stage_b_schema_compatibility():
    print("\n--- TEST SUITE 1: Stage B Schema Compatibility & Exact Column Verification ---")
    conn, db_path = get_actual_stage_b_connection()
    try:
        cursor = conn.cursor()
        tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        
        required_stage_b_tables = [
            'herbs', 'illness', 'treatment', 'herb_attributes', 'herb_doshas',
            'schema_migrations', 'sources', 'source_records', 'source_claims',
            'legacy_herb_map', 'herb_names', 'taxa', 'taxon_relationships', 'herb_taxa'
        ]
        for tbl in required_stage_b_tables:
            assert tbl in tables, f"Required Stage B table {tbl} missing from database!"
        
        # Verify exact column names in herbs
        herb_cols = {r[1]: r[2] for r in cursor.execute("PRAGMA table_info(herbs)").fetchall()}
        assert 'english_name' in herb_cols, "herbs.english_name must exist!"
        assert 'name' not in herb_cols, "herbs.name must NOT exist (it is english_name)!"
        assert 'source' in herb_cols
        assert 'source_record_id' in herb_cols
        assert 'botanical_name' in herb_cols
        
        # Verify exact column names in sources
        source_cols = {r[1]: r[2] for r in cursor.execute("PRAGMA table_info(sources)").fetchall()}
        assert 'source_id' in source_cols, "sources.source_id must exist!"
        assert 'id' not in source_cols, "sources.id must NOT exist (it is source_id)!"
        assert 'source_key' in source_cols
        
        # Verify exact column names in source_records
        sr_cols = {r[1]: r[2] for r in cursor.execute("PRAGMA table_info(source_records)").fetchall()}
        assert 'source_record_id' in sr_cols, "source_records.source_record_id must exist!"
        assert 'id' not in sr_cols, "source_records.id must NOT exist!"
        assert 'source_id' in sr_cols
        assert 'external_record_key' in sr_cols
        
        # Verify exact column names in source_claims
        sc_cols = {r[1]: r[2] for r in cursor.execute("PRAGMA table_info(source_claims)").fetchall()}
        assert 'source_claim_id' in sc_cols, "source_claims.source_claim_id must exist!"
        assert 'id' not in sc_cols, "source_claims.id must NOT exist!"
        assert 'verification_status' in sc_cols
        assert 'reviewed_by' in sc_cols
        assert 'reviewed_at' in sc_cols
        assert 'supersedes_claim_id' in sc_cols
        assert 'is_active' not in sc_cols, "source_claims.is_active must NOT exist (Stage B uses verification_status != 'superseded')!"
        
        # Verify exact column names in legacy_herb_map
        lhm_cols = {r[1]: r[2] for r in cursor.execute("PRAGMA table_info(legacy_herb_map)").fetchall()}
        assert 'legacy_herb_id' in lhm_cols
        assert 'herb_id' in lhm_cols
        assert 'created_at' in lhm_cols
        assert 'source_record_id' not in lhm_cols, "legacy_herb_map does NOT have source_record_id!"
        assert 'source_id' not in lhm_cols, "legacy_herb_map does NOT have source_id!"
        
        # Verify legacy herb_attributes table is intact
        ha_cols = {r[1]: r[2] for r in cursor.execute("PRAGMA table_info(herb_attributes)").fetchall()}
        assert 'field_name' in ha_cols
        assert 'value' in ha_cols
        assert 'source_text' in ha_cols
        
        print("  [PASS] Actual Stage B schema columns and constraints verified 100%.")
        
        # Apply Stage C DDL and Triggers from delivered SQL file
        execute_statements(conn, STAGE_C_SQL)
        
        # Verify all 11 Stage C tables exist
        c_tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        expected_stage_c_tables = [
            'dravyaguna_concepts', 'concept_labels', 'concept_label_sources',
            'concept_claim_mappings', 'dosha_claim_assertions',
            'herb_dravyaguna_properties', 'herb_dosha_effects',
            'herb_plant_parts', 'herb_preparations', 'herb_indications',
            'source_reconciliation_events'
        ]
        for tbl in expected_stage_c_tables:
            assert tbl in c_tables, f"Stage C table {tbl} was not created!"

        # Verify Stage C views exist
        c_views = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall()]
        assert 'v_active_herb_dravyaguna_properties' in c_views
        assert 'v_active_herb_dosha_effects' in c_views
        
        print("  [PASS] Stage C DDL applied with zero collisions against legacy tables.")
    finally:
        conn.close()
        if os.path.exists(db_path):
            os.remove(db_path)

# ============================================================================
# TEST SUITE 2: COMPLETE MUTATION AND DELETION INTEGRITY MATRIX
# ============================================================================
def test_mutation_and_deletion_matrix():
    print("\n--- TEST SUITE 2: Complete Mutation & Deletion Integrity Matrix ---")
    conn, db_path = get_actual_stage_b_connection()
    try:
        execute_statements(conn, STAGE_C_SQL)
        now = "2026-11-17T12:00:00Z"
        
        # 1. Seed an herb and source evidence in actual Stage B schema
        conn.execute("INSERT INTO sources (source_key, publisher) VALUES ('CCRAS_DRAVYA', 'CCRAS')")
        source_id = conn.execute("SELECT source_id FROM sources WHERE source_key = 'CCRAS_DRAVYA'").fetchone()[0]
        
        conn.execute("INSERT INTO source_records (source_id, external_record_key) VALUES (?, '101')", (source_id,))
        sr_id = conn.execute("SELECT source_record_id FROM source_records WHERE external_record_key = '101'").fetchone()[0]
        
        conn.execute("""
        INSERT INTO source_claims (source_record_id, claim_type, source_field, source_expression, language_code, retrieved_at, verification_status, created_by_type, created_by, created_at, updated_at)
        VALUES (?, 'property', 'Virya', 'Ushna', 'sa', ?, 'unreviewed', 'system', 'ingest_pipeline', ?, ?)
        """, (sr_id, now, now, now))
        sc_id = conn.execute("SELECT source_claim_id FROM source_claims WHERE source_record_id = ?", (sr_id,)).fetchone()[0]
        
        conn.execute("INSERT INTO herbs (id, english_name, source, source_record_id) VALUES (1, 'Ginger', 'CCRAS_DRAVYA', 101)")
        conn.execute("INSERT INTO legacy_herb_map (legacy_herb_id, herb_id, created_at) VALUES (1, 1, ?)", (now,))
        
        # 2. Seed concept and mapping in Stage C
        conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (1, 'virya.ushna', 'virya', ?)", (now,))
        conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, created_at) VALUES (1, ?, 1, 'exact', 'lexicon_exact', ?)", (sc_id, now))
        
        # 3. Attach property relationship
        conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, created_at) VALUES (1, 1, 1, ?)", (now,))
        
        # Seed dosha assertion
        conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (2, 'dosha.vata', 'dosha', ?)", (now,))
        conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (3, 'effect.shamana', 'dosha_effect', ?)", (now,))
        conn.execute("INSERT INTO dosha_claim_assertions (dosha_assertion_id, source_claim_id, dosha_concept_id, effect_concept_id, mapping_method, created_at) VALUES (1, ?, 2, 3, 'lexicon_exact', ?)", (sc_id, now))
        conn.execute("INSERT INTO herb_dosha_effects (herb_dosha_effect_id, herb_id, dosha_assertion_id, created_at) VALUES (1, 1, 1, ?)", (now,))
        
        # --- TEST 2.1: FK CASCADE RESTRICTIONS ---
        try:
            conn.execute("DELETE FROM source_records WHERE source_record_id = ?", (sr_id,))
            assert False, "Deleting source_records with dependent claims should fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] FK Enforcement: Deleting source_record with dependent claims blocked.")
            
        try:
            conn.execute("DELETE FROM source_claims WHERE source_claim_id = ?", (sc_id,))
            assert False, "Deleting source_claims with dependent mappings should fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] FK Enforcement: Deleting source_claim with dependent mappings blocked.")
            
        try:
            conn.execute("DELETE FROM dravyaguna_concepts WHERE concept_id = 1")
            assert False, "Deleting concept referenced by mapping should fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] FK Enforcement: Deleting concept used by mapping blocked.")
            
        try:
            conn.execute("DELETE FROM concept_claim_mappings WHERE mapping_id = 1")
            assert False, "Deleting mapping referenced by herb_dravyaguna_properties should fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] FK Enforcement: Deleting mapping used by relationship blocked.")
            
        try:
            conn.execute("DELETE FROM dosha_claim_assertions WHERE dosha_assertion_id = 1")
            assert False, "Deleting dosha assertion referenced by herb_dosha_effects should fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] FK Enforcement: Deleting dosha assertion used by relationship blocked.")

        # --- TEST 2.2: SOURCE IDENTITY AND CITATION AUDIT ENFORCEMENT ---
        try:
            conn.execute("UPDATE sources SET source_key = 'CCRAS_MUTATED' WHERE source_id = ?", (source_id,))
            assert False, "Mutating source_key should be blocked by trigger!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Blocked source_key mutation while dependent herb relationships exist.")
            
        try:
            conn.execute("DELETE FROM sources WHERE source_id = ?", (source_id,))
            assert False, "Deleting source should be blocked!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger & FK Enforcement: Blocked sources deletion while dependent records exist.")
            
        # Verify editorial non-identity update on sources is permitted
        conn.execute("UPDATE sources SET publisher = 'CCRAS (Updated Publisher)', notes = 'Editorial note' WHERE source_id = ?", (source_id,))
        print("  [PASS] Trigger Audit: Permitted editorial metadata updates on sources (publisher, notes).")

        # --- TEST 2.3: SOURCE CLAIM REVIEW AUDITABILITY TRIGGERS ---
        # 1. Test INSERT reviewed without metadata
        try:
            conn.execute("""
            INSERT INTO source_claims (source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at)
            VALUES (?, 'property', 'Rasa', 'Katu', 'reviewed', 'system', 'ingest_pipeline', ?, ?)
            """, (sr_id, now, now))
            assert False, "INSERT reviewed without metadata must fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: INSERT reviewed without review metadata blocked.")

        # 2. Test INSERT verified without metadata
        try:
            conn.execute("""
            INSERT INTO source_claims (source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at)
            VALUES (?, 'property', 'Rasa', 'Katu', 'verified', 'system', 'ingest_pipeline', ?, ?)
            """, (sr_id, now, now))
            assert False, "INSERT verified without metadata must fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: INSERT verified without review metadata blocked.")

        # 3. Attempting to set verification_status = 'reviewed' without reviewed_by/at must fail
        try:
            conn.execute("UPDATE source_claims SET verification_status = 'reviewed' WHERE source_claim_id = ?", (sc_id,))
            assert False, "Setting source_claims to 'reviewed' without reviewed_by/at must fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Setting source_claims to 'reviewed' without review metadata blocked.")

        try:
            conn.execute("UPDATE source_claims SET verification_status = 'verified', reviewed_by = 'Dr. Patel', reviewed_at = NULL WHERE source_claim_id = ?", (sc_id,))
            assert False, "Setting source_claims to 'verified' with NULL reviewed_at must fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Setting source_claims to 'verified' with NULL reviewed_at blocked.")

        # 4. Succeeded with both review metadata fields populated
        conn.execute("UPDATE source_claims SET verification_status = 'reviewed', reviewed_by = 'Dr. Patel', reviewed_at = ? WHERE source_claim_id = ?", (now, sc_id))
        print("  [PASS] Trigger Audit: Setting source_claims to 'reviewed' with valid reviewer metadata succeeded.")

        # 5. Attempting to clear reviewed_by while remaining 'reviewed' must fail
        try:
            conn.execute("UPDATE source_claims SET reviewed_by = NULL WHERE source_claim_id = ?", (sc_id,))
            assert False, "Clearing reviewed_by on reviewed source claim must fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Clearing reviewed_by on reviewed claim blocked.")

        try:
            conn.execute("UPDATE source_claims SET reviewed_at = '' WHERE source_claim_id = ?", (sc_id,))
            assert False, "Clearing reviewed_at on reviewed source claim must fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Clearing reviewed_at on reviewed claim blocked.")

        # 6. Demotion back to 'unreviewed' succeeds
        conn.execute("UPDATE source_claims SET verification_status = 'unreviewed', reviewed_by = NULL, reviewed_at = NULL WHERE source_claim_id = ?", (sc_id,))
        print("  [PASS] Trigger Audit: Demoting source claim to 'unreviewed' and clearing metadata permitted.")

        # --- TEST 2.4: VERIFIED LABEL AND CITATION IMMUTABILITY ---
        conn.execute("""
        INSERT INTO concept_labels (concept_label_id, concept_id, language_code, script_code, label_text, normalized_label, label_type, translation_origin, verification_status, created_at)
        VALUES (1, 1, 'sa', 'Deva', 'Uṣṇa', 'usna', 'canonical_sanskrit', 'classical_lexicon', 'unreviewed', ?)
        """, (now,))
        conn.execute("""
        INSERT INTO concept_label_sources (label_source_id, concept_label_id, source_id, authority_citation, citation_type, verified_by, verified_at, created_at)
        VALUES (1, 1, ?, 'Dravyaguna Vijnana Vol 1, p.45', 'academic_lexicon', 'Dr. Sharma', ?, ?)
        """, (source_id, now, now))
        conn.execute("UPDATE concept_labels SET verification_status = 'verified', reviewed_by = 'Dr. Sharma', reviewed_at = ? WHERE concept_label_id = 1", (now,))
        
        try:
            conn.execute("UPDATE concept_labels SET concept_id = 2 WHERE concept_label_id = 1")
            assert False, "Mutating concept_id on verified label should fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Blocked concept_id mutation on verified label.")
            
        try:
            conn.execute("UPDATE concept_labels SET label_text = 'Ushnam' WHERE concept_label_id = 1")
            assert False, "Mutating label_text on verified label should fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Blocked label_text mutation on verified label.")
            
        try:
            conn.execute("DELETE FROM concept_labels WHERE concept_label_id = 1")
            assert False, "Deleting verified label should fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Blocked deletion of verified label.")
            
        try:
            conn.execute("DELETE FROM concept_label_sources WHERE label_source_id = 1")
            assert False, "Deleting last citation for verified label should fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Blocked deletion of last verified citation while label is verified.")

        # Test strengthened label verification:
        # a. Machine-generated label cannot become verified
        conn.execute("""
        INSERT INTO concept_labels (concept_label_id, concept_id, language_code, script_code, label_text, normalized_label, label_type, translation_origin, verification_status, created_at)
        VALUES (2, 1, 'sa', 'Deva', 'Machine', 'machine', 'canonical_sanskrit', 'machine_generated', 'unreviewed', ?)
        """, (now,))
        conn.execute("""
        INSERT INTO concept_label_sources (label_source_id, concept_label_id, authority_citation, citation_type, verified_by, verified_at, created_at)
        VALUES (2, 2, 'Citation', 'academic_lexicon', 'Dr. Sharma', ?, ?)
        """, (now, now))
        try:
            conn.execute("UPDATE concept_labels SET verification_status = 'verified', verified_by = 'Dr. Sharma', verified_at = ? WHERE concept_label_id = 2", (now,))
            assert False, "Machine-generated label verification must fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Machine-generated label cannot become verified.")

        # b. Verifying without verified_by / verified_at must fail
        conn.execute("UPDATE concept_labels SET translation_origin = 'human_curated' WHERE concept_label_id = 2")
        try:
            conn.execute("UPDATE concept_labels SET verification_status = 'verified', verified_by = NULL, reviewed_by = NULL WHERE concept_label_id = 2")
            assert False, "Verifying without verified_by must fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Verifying label without verified_by/verified_at blocked.")

        # c. Verifying without citation or with empty citation must fail
        conn.execute("DELETE FROM concept_label_sources WHERE label_source_id = 2")
        try:
            conn.execute("UPDATE concept_labels SET verification_status = 'verified', verified_by = 'Dr. Sharma', verified_at = ? WHERE concept_label_id = 2", (now,))
            assert False, "Verifying without citation must fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Verifying label without qualifying citation blocked.")

        # d. Cannot empty authority_citation on verified label's citation
        try:
            conn.execute("UPDATE concept_label_sources SET authority_citation = '' WHERE label_source_id = 1")
            assert False, "Emptying authority_citation on verified label must fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Emptying authority_citation on verified label blocked.")

        # Demote label to unreviewed allows editorial fix
        conn.execute("UPDATE concept_labels SET verification_status = 'unreviewed', reviewed_by = NULL, reviewed_at = NULL, verified_by = NULL, verified_at = NULL WHERE concept_label_id = 1")
        conn.execute("UPDATE concept_labels SET label_text = 'Uṣṇa (Corrected)' WHERE concept_label_id = 1")
        print("  [PASS] Trigger Audit: Permitted label text mutation after demotion to unreviewed.")

        # Test source_reconciliation_events snapshot integrity
        try:
            conn.execute("""
            INSERT INTO source_reconciliation_events (source_id, event_type, snapshot_timestamp, extraction_status, is_complete_snapshot, initiated_by)
            VALUES (?, 'snapshot_reconciliation', ?, 'failed', 1, 'admin')
            """, (source_id, now))
            assert False, "Incomplete/failed extraction with is_complete_snapshot=1 must fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Incomplete or failed extraction cannot be treated as complete snapshot.")

        conn.execute("""
        INSERT INTO source_reconciliation_events (source_id, event_type, snapshot_timestamp, extraction_status, is_complete_snapshot, initiated_by)
        VALUES (?, 'snapshot_reconciliation', ?, 'completed', 1, 'admin')
        """, (source_id, now))
        print("  [PASS] Trigger Audit: Completed extraction snapshot recorded successfully.")

        # --- TEST 2.5: PROVENANCE AND MAPPING IMMUTABILITY ---
        try:
            conn.execute("UPDATE concept_claim_mappings SET concept_id = 2 WHERE mapping_id = 1")
            assert False, "Mutating concept_id of active mapping should fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Blocked mapping concept_id mutation while active in herb_dravyaguna_properties.")
            
        try:
            conn.execute("UPDATE source_claims SET source_record_id = 999 WHERE source_claim_id = ?", (sc_id,))
            assert False, "Mutating source_record_id of mapped claim should fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Blocked source_claims.source_record_id mutation while mapped.")

        try:
            conn.execute("UPDATE source_claims SET source_expression = 'Altered' WHERE source_claim_id = ?", (sc_id,))
            assert False, "Mutating source_expression of mapped claim should fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Blocked source_claims.source_expression mutation while mapped.")

        try:
            conn.execute("UPDATE source_claims SET source_field = 'AlteredField' WHERE source_claim_id = ?", (sc_id,))
            assert False, "Mutating source_field of mapped claim should fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Blocked source_claims.source_field mutation while mapped.")

        try:
            conn.execute("UPDATE source_claims SET claim_type = 'botanical_identity' WHERE source_claim_id = ?", (sc_id,))
            assert False, "Mutating claim_type of mapped claim should fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Blocked source_claims.claim_type mutation while mapped.")
            
        try:
            conn.execute("UPDATE source_records SET external_record_key = '999' WHERE source_record_id = ?", (sr_id,))
            assert False, "Mutating external_record_key of mapped source_record should fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Blocked source_records external_record_key mutation while mapped.")
            
        try:
            conn.execute("UPDATE legacy_herb_map SET herb_id = 999 WHERE legacy_herb_id = 1")
            assert False, "Mutating legacy_herb_map should fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Blocked legacy_herb_map mutation while active.")
            
        try:
            conn.execute("UPDATE herbs SET source_record_id = 999 WHERE id = 1")
            assert False, "Mutating herbs.source_record_id should fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Blocked herbs provenance mutation while active relationships exist.")

        # Cross-herb trigger validation
        conn.execute("INSERT INTO source_records (source_record_id, source_id, external_record_key) VALUES (102, ?, '102')", (source_id,))
        conn.execute("INSERT INTO herbs (id, english_name, source, source_record_id) VALUES (2, 'Pepper', 'CCRAS_DRAVYA', 102)")
        try:
            conn.execute("UPDATE herb_dravyaguna_properties SET herb_id = 2 WHERE herb_property_id = 1")
            assert False, "Reassigning property to an herb with mismatched source record should fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Trigger Enforcement: Reassigning relationship to incompatible herb blocked by cross-herb trigger.")
            
        # Automatic Claim Supersession Cascade
        conn.execute("""
        INSERT INTO source_claims (source_record_id, claim_type, source_field, source_expression, language_code, retrieved_at, verification_status, created_by_type, created_by, created_at, updated_at)
        VALUES (?, 'property', 'Virya', 'Sheeta', 'sa', ?, 'unreviewed', 'system', 'ingest_pipeline', ?, ?)
        """, (sr_id, now, now, now))
        new_sc_id = conn.execute("SELECT MAX(source_claim_id) FROM source_claims").fetchone()[0]
        
        conn.execute("UPDATE source_claims SET verification_status = 'superseded', supersedes_claim_id = ? WHERE source_claim_id = ?", (new_sc_id, sc_id))
        claim_status = conn.execute("SELECT verification_status FROM source_claims WHERE source_claim_id = ?", (sc_id,)).fetchone()[0]
        mapping_status = conn.execute("SELECT verification_status FROM concept_claim_mappings WHERE mapping_id = 1").fetchone()[0]
        assert claim_status == 'superseded'
        assert mapping_status == 'superseded'
        print("  [PASS] Controlled Supersession: Claim supersession automatically cascaded to mapping (status = 'superseded').")

        # --- TEST 2.6: NULLABLE COMPOSITE UNIQUENESS (PARTIAL UNIQUE INDEXES) ---
        # 1. Duplicate unspecified-part property rejected
        conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (888, 'virya.ushna_test', 'virya', ?)", (now,))
        conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at) VALUES (888, ?, 'attribute', 'Virya', 'Ushna', 'unreviewed', 'ingest', 'test', ?, ?)", (sr_id, now, now))
        conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, created_at) VALUES (888, 888, 888, 'exact', 'lexicon_exact', ?)", (now,))
        conn.execute("INSERT INTO herb_dravyaguna_properties (herb_id, mapping_id, part_concept_id, created_at) VALUES (1, 888, NULL, ?)", (now,))
        try:
            conn.execute("INSERT INTO herb_dravyaguna_properties (herb_id, mapping_id, part_concept_id, created_at) VALUES (1, 888, NULL, ?)", (now,))
            assert False, "Duplicate unspecified-part property must fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Partial Unique Index: Duplicate unspecified-part properties rejected.")

        # 2. Duplicate unspecified-part preparation rejected
        conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (889, 'preparation_form.churna_test', 'preparation_form', ?)", (now,))
        conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at) VALUES (889, ?, 'attribute', 'Form', 'Churna', 'unreviewed', 'ingest', 'test', ?, ?)", (sr_id, now, now))
        conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, created_at) VALUES (889, 889, 889, 'exact', 'lexicon_exact', ?)", (now,))
        conn.execute("INSERT INTO herb_preparations (herb_id, prep_mapping_id, part_mapping_id, created_at) VALUES (1, 889, NULL, ?)", (now,))
        try:
            conn.execute("INSERT INTO herb_preparations (herb_id, prep_mapping_id, part_mapping_id, created_at) VALUES (1, 889, NULL, ?)", (now,))
            assert False, "Duplicate unspecified-part preparation must fail!"
        except sqlite3.IntegrityError:
            print("  [PASS] Partial Unique Index: Duplicate unspecified-part preparations rejected.")

    finally:
        conn.close()
        if os.path.exists(db_path):
            os.remove(db_path)

# ============================================================================
# TEST SUITE 3: COMPREHENSIVE VIRYA RECONCILIATION DATASET & TIERS
# ============================================================================
def test_virya_reconciliation_dataset():
    print("\n--- TEST SUITE 3: Comprehensive Virya Reconciliation Dataset (15 Scenarios) ---")
    conn, db_path = get_actual_stage_b_connection()
    try:
        execute_statements(conn, STAGE_C_SQL)
        now = "2026-11-17T12:00:00Z"
        
        # Sources
        conn.execute("INSERT INTO sources (source_key, publisher) VALUES ('CCRAS_DRAVYA', 'CCRAS')")
        s1_id = conn.execute("SELECT source_id FROM sources WHERE source_key = 'CCRAS_DRAVYA'").fetchone()[0]
        conn.execute("INSERT INTO sources (source_key, publisher) VALUES ('API_VOL_1', 'Govt of India')")
        s2_id = conn.execute("SELECT source_id FROM sources WHERE source_key = 'API_VOL_1'").fetchone()[0]
        conn.execute("INSERT INTO sources (source_key, publisher) VALUES ('CHARAKA_SAMHITA', 'Classical')")
        s3_id = conn.execute("SELECT source_id FROM sources WHERE source_key = 'CHARAKA_SAMHITA'").fetchone()[0]
        
        # Concepts: Virya concepts
        conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (1, 'virya.ushna', 'virya', ?)", (now,))
        conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (2, 'virya.sheeta', 'virya', ?)", (now,))
        
        # Concepts: Plant part concepts
        conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (10, 'part.leaf', 'plant_part', ?)", (now,))
        conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (11, 'part.root', 'plant_part', ?)", (now,))
        
        # Herbs: Piper longum (Pippali) - CCRAS record and API record
        conn.execute("INSERT INTO herbs (id, english_name, botanical_name, source, source_record_id) VALUES (1, 'Pippali (CCRAS)', 'Piper longum L.', 'CCRAS_DRAVYA', 101)")
        conn.execute("INSERT INTO legacy_herb_map (legacy_herb_id, herb_id, created_at) VALUES (1, 1, ?)", (now,))
        
        conn.execute("INSERT INTO herbs (id, english_name, botanical_name, source, source_record_id) VALUES (2, 'Pippali (API)', 'Piper longum L.', 'API_VOL_1', 201)")
        conn.execute("INSERT INTO legacy_herb_map (legacy_herb_id, herb_id, created_at) VALUES (2, 2, ?)", (now,))

        # Source Records
        conn.execute("INSERT INTO source_records (source_record_id, source_id, external_record_key) VALUES (101, ?, '101')", (s1_id,))
        conn.execute("INSERT INTO source_records (source_record_id, source_id, external_record_key) VALUES (201, ?, '201')", (s2_id,))
        conn.execute("INSERT INTO source_records (source_record_id, source_id, external_record_key) VALUES (102, ?, '102')", (s1_id,))
        conn.execute("INSERT INTO source_records (source_record_id, source_id, external_record_key) VALUES (202, ?, '202')", (s2_id,))
        
        # --------------------------------------------------------------------
        # Scenario 1: Same Virya, same plant part (No divergence in any tier)
        # --------------------------------------------------------------------
        conn.execute("""
        INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at)
        VALUES (1, 101, 'property', 'Virya', 'Ushna', 'verified', 'Dr. Sharma', ?, 'system', 'ingest', ?, ?)
        """, (now, now, now))
        conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, verification_status, created_at) VALUES (1, 1, 1, 'exact', 'lexicon_exact', 'verified', ?)", (now,))
        conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (1, 1, 1, 11, 'active', ?)", (now,))
        
        conn.execute("""
        INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at)
        VALUES (2, 201, 'property', 'Virya', 'Ushna', 'verified', 'Dr. Sharma', ?, 'system', 'ingest', ?, ?)
        """, (now, now, now))
        conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, verification_status, created_at) VALUES (2, 2, 1, 'exact', 'lexicon_exact', 'verified', ?)", (now,))
        conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (2, 2, 2, 11, 'active', ?)", (now,))
        
        assert len(conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()) == 0
        print("  [PASS] Scenario 1: Same Virya, same plant part produces no divergence in any tier.")
        
        # --------------------------------------------------------------------
        # Scenario 2a: Different Virya, same part, UNREVIEWED -> Tier 1
        # --------------------------------------------------------------------
        conn.execute("INSERT INTO herbs (id, english_name, botanical_name, source, source_record_id) VALUES (3, 'Haritaki (CCRAS)', 'Terminalia chebula', 'CCRAS_DRAVYA', 102)")
        conn.execute("INSERT INTO legacy_herb_map (legacy_herb_id, herb_id, created_at) VALUES (3, 3, ?)", (now,))
        
        conn.execute("INSERT INTO herbs (id, english_name, botanical_name, source, source_record_id) VALUES (4, 'Haritaki (API)', 'Terminalia chebula', 'API_VOL_1', 202)")
        conn.execute("INSERT INTO legacy_herb_map (legacy_herb_id, herb_id, created_at) VALUES (4, 4, ?)", (now,))

        conn.execute("""
        INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at)
        VALUES (3, 102, 'property', 'Virya', 'Ushna', 'unreviewed', 'system', 'ingest', ?, ?)
        """, (now, now))
        conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, verification_status, created_at) VALUES (3, 3, 1, 'exact', 'lexicon_exact', 'unreviewed', ?)", (now,))
        conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (3, 3, 3, 11, 'active', ?)", (now,))
        
        conn.execute("""
        INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at)
        VALUES (4, 202, 'property', 'Virya', 'Sheeta', 'unreviewed', 'system', 'ingest', ?, ?)
        """, (now, now))
        conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, verification_status, created_at) VALUES (4, 4, 2, 'exact', 'lexicon_exact', 'unreviewed', ?)", (now,))
        conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (4, 4, 4, 11, 'active', ?)", (now,))
        
        rows_t1 = conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall()
        assert len(rows_t1) == 1, f"Expected 1 Tier 1 row, got {len(rows_t1)}"
        assert rows_t1[0][0] == 'Terminalia chebula'
        assert rows_t1[0][1] == 'candidate_match_botanical_string_equality'  # identity_basis
        assert rows_t1[0][2] == 3  # herb_1_id
        assert rows_t1[0][3] == 'Haritaki (CCRAS)'  # herb_1_name
        assert rows_t1[0][4] == 4  # herb_2_id
        assert rows_t1[0][5] == 'Haritaki (API)'  # herb_2_name
        assert rows_t1[0][22] == 'UNREVIEWED_CANDIDATE_DIVERGENCE'
        # Mutually exclusive: 0 in Tier 2 and Tier 3
        assert len(conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()) == 0
        print("  [PASS] Scenario 2a: Unreviewed divergence cleanly captured in Tier 1 with transparent dual herb IDs.")
        
        # --------------------------------------------------------------------
        # Scenario 2b: Different Virya, same part, REVIEWED with approximation -> Tier 2
        # --------------------------------------------------------------------
        conn.execute("UPDATE source_claims SET verification_status = 'reviewed', reviewed_by = 'Dr. Sharma', reviewed_at = ? WHERE source_claim_id IN (3, 4)", (now,))
        conn.execute("UPDATE concept_claim_mappings SET verification_status = 'reviewed', mapping_type = 'broader', reviewed_by = 'Dr. Patel', reviewed_at = ? WHERE mapping_id = 3", (now,))
        conn.execute("UPDATE concept_claim_mappings SET verification_status = 'reviewed', mapping_type = 'exact', reviewed_by = 'Dr. Patel', reviewed_at = ? WHERE mapping_id = 4", (now,))
        
        rows_t2 = conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()
        assert len(rows_t2) == 1
        assert rows_t2[0][2] == 3
        assert rows_t2[0][4] == 4
        assert rows_t2[0][22] == 'REVIEWED_CANDIDATE_DIVERGENCE'
        # Mutually exclusive: 0 in Tier 1 and Tier 3
        assert len(conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()) == 0
        print("  [PASS] Scenario 2b: Reviewed divergence with approximation captured in Tier 2 (mutually exclusive).")
        
        # --------------------------------------------------------------------
        # Scenario 2c: Different Virya, same part, VERIFIED cross-source -> Tier 3
        # --------------------------------------------------------------------
        conn.execute("UPDATE source_claims SET verification_status = 'verified', reviewed_by = 'Dr. Sharma', reviewed_at = ? WHERE source_claim_id IN (3, 4)", (now,))
        conn.execute("UPDATE concept_claim_mappings SET verification_status = 'verified', mapping_type = 'exact', reviewed_by = 'Dr. Patel', reviewed_at = ? WHERE mapping_id IN (3, 4)", (now,))
        rows_t3 = conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()
        assert len(rows_t3) == 1
        assert rows_t3[0][2] == 3  # herb_1_id
        assert rows_t3[0][3] == 'Haritaki (CCRAS)'  # herb_1_name
        assert rows_t3[0][4] == 4  # herb_2_id
        assert rows_t3[0][5] == 'Haritaki (API)'  # herb_2_name
        assert rows_t3[0][11] == 'Dr. Sharma'  # claim_1_reviewed_by
        assert rows_t3[0][13] == 'Dr. Patel'   # mapping_1_verified_by
        assert rows_t3[0][20] == 'Dr. Sharma'  # claim_2_reviewed_by
        assert rows_t3[0][22] == 'Dr. Patel'   # mapping_2_verified_by
        assert rows_t3[0][26] == 'VERIFIED_SOURCE_DISAGREEMENT'
        # Mutually exclusive: 0 in Tier 1 and Tier 2
        assert len(conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()) == 0
        print("  [PASS] Scenario 2c: Verified cross-source disagreement captured in Tier 3 with dual review metadata.")
        
        # --------------------------------------------------------------------
        # Scenario 3: Different Virya, DIFFERENT plant parts (Not a disagreement!)
        # --------------------------------------------------------------------
        conn.execute("UPDATE herb_dravyaguna_properties SET part_concept_id = 10 WHERE herb_property_id = 4")
        assert len(conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()) == 0
        print("  [PASS] Scenario 3: Different plant parts correctly excluded from disagreements.")
        
        # --------------------------------------------------------------------
        # Scenario 4: PLANT PART MATRIX TEST (Unspecified vs Specified, Both NULL, Different Specified)
        # --------------------------------------------------------------------
        # 4a. One NULL, one specified (p1=11, p2=NULL) -> Enters Tier 2, EXCLUDED from Tier 3
        conn.execute("UPDATE herb_dravyaguna_properties SET part_concept_id = NULL WHERE herb_property_id = 4")
        rows_null_t2 = conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()
        assert len(rows_null_t2) == 1
        assert rows_null_t2[0][20] == 'unspecified_vs_specified_part'
        assert rows_null_t2[0][22] == 'REVIEWED_CANDIDATE_DIVERGENCE'
        assert len(conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()) == 0
        print("  [PASS] Scenario 4a: One unspecified and one specified part enters Tier 2 and is strictly excluded from Tier 3.")

        # 4b. Both parts NULL (p1=NULL, p2=NULL) -> Follows Tier 3 policy (enters Tier 3 when verified exact cross-source)
        conn.execute("UPDATE herb_dravyaguna_properties SET part_concept_id = NULL WHERE herb_property_id = 3")
        rows_both_null_t3 = conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()
        assert len(rows_both_null_t3) == 1
        assert rows_both_null_t3[0][24] == 'both_parts_unspecified'
        assert rows_both_null_t3[0][26] == 'VERIFIED_SOURCE_DISAGREEMENT'
        assert len(conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()) == 0
        print("  [PASS] Scenario 4b: Both plant parts unspecified (NULL vs NULL) follows Tier 3 policy and enters Tier 3.")

        # 4c. Two different specified parts (p1=11, p2=10) -> Excluded from ALL three reconciliation tiers
        conn.execute("UPDATE herb_dravyaguna_properties SET part_concept_id = 11 WHERE herb_property_id = 3")
        conn.execute("UPDATE herb_dravyaguna_properties SET part_concept_id = 10 WHERE herb_property_id = 4")
        assert len(conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()) == 0
        print("  [PASS] Scenario 4c: Two different specified parts are excluded from ALL three reconciliation tiers.")

        # 4d. Same specified part (p1=11, p2=11) -> Enters Tier 3 as exact_part_match
        conn.execute("UPDATE herb_dravyaguna_properties SET part_concept_id = 11 WHERE herb_property_id IN (3, 4)")
        rows_same_part_t3 = conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()
        assert len(rows_same_part_t3) == 1
        assert rows_same_part_t3[0][24] == 'exact_part_match'
        assert rows_same_part_t3[0][26] == 'VERIFIED_SOURCE_DISAGREEMENT'
        print("  [PASS] Scenario 4d: Same specified plant part enters Tier 3 as exact_part_match.")

        # --------------------------------------------------------------------
        # Scenario 5: REVIEWED EXACT DIVERGENCE COVERAGE (Case A: Mappings not yet verified)
        # --------------------------------------------------------------------
        # Cross-source, exact mappings, but mappings are reviewed rather than verified
        conn.execute("UPDATE concept_claim_mappings SET verification_status = 'reviewed', mapping_type = 'exact', reviewed_by = 'Dr. Patel', reviewed_at = ? WHERE mapping_id = 4", (now,))
        rows_case_a = conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()
        assert len(rows_case_a) == 1, "Reviewed exact cross-source divergence must enter Tier 2!"
        assert rows_case_a[0][22] == 'REVIEWED_CANDIDATE_DIVERGENCE'
        assert len(conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()) == 0, "Must be excluded from Tier 3 until verified!"
        print("  [PASS] Scenario 5 (Case A): Cross-source reviewed exact divergence captured in Tier 2 and excluded from Tier 3.")
        conn.execute("UPDATE concept_claim_mappings SET verification_status = 'verified', mapping_type = 'exact' WHERE mapping_id = 4")

        # --------------------------------------------------------------------
        # Scenario 6: REVIEWED EXACT DIVERGENCE COVERAGE (Case B: Intra-source multi-record)
        # --------------------------------------------------------------------
        # Seed another record for CCRAS (s1) asserting Sheeta for Haritaki
        conn.execute("INSERT INTO source_records (source_record_id, source_id, external_record_key) VALUES (103, ?, '103')", (s1_id,))
        conn.execute("INSERT INTO herbs (id, english_name, botanical_name, source, source_record_id) VALUES (5, 'Haritaki (CCRAS Vol 2)', 'Terminalia chebula', 'CCRAS_DRAVYA', 103)")
        conn.execute("INSERT INTO legacy_herb_map (legacy_herb_id, herb_id, created_at) VALUES (5, 5, ?)", (now,))
        conn.execute("""
        INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at)
        VALUES (5, 103, 'property', 'Virya', 'Sheeta', 'verified', 'Dr. Sharma', ?, 'system', 'ingest', ?, ?)
        """, (now, now, now))
        conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, verification_status, reviewed_by, reviewed_at, created_at) VALUES (5, 5, 2, 'exact', 'lexicon_exact', 'verified', 'Dr. Patel', ?, ?)", (now, now))
        conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (5, 5, 5, 11, 'active', ?)", (now,))
        
        # Intra-source pair (claim 3 vs claim 5) must enter Tier 2 with intra_source_multi_record_divergence
        t2_intra_multi = conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()
        intra_multi_match = [r for r in t2_intra_multi if r[6] == 'CCRAS_DRAVYA' and r[13] == 'CCRAS_DRAVYA']
        assert len(intra_multi_match) == 1, "Intra-source multi-record exact divergence must enter Tier 2!"
        assert intra_multi_match[0][21] == 'intra_source_multi_record_divergence'
        # Must NOT appear in Tier 3
        t3_all = conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()
        intra_in_t3 = [r for r in t3_all if r[6] == r[15]]
        assert len(intra_in_t3) == 0, "Intra-source divergence must NEVER appear in Tier 3!"
        print("  [PASS] Scenario 6 (Case B): Intra-source multi-record exact divergence captured in Tier 2 and excluded from Tier 3.")

        # --------------------------------------------------------------------
        # Scenario 7: REVIEWED EXACT DIVERGENCE COVERAGE (Case C: Intra-source single-record)
        # --------------------------------------------------------------------
        # Seed another claim on the SAME source_record (102) asserting Sheeta
        conn.execute("""
        INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at)
        VALUES (6, 102, 'property', 'Virya_Variant', 'Sheeta', 'verified', 'Dr. Sharma', ?, 'system', 'ingest', ?, ?)
        """, (now, now, now))
        conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, verification_status, reviewed_by, reviewed_at, created_at) VALUES (6, 6, 2, 'exact', 'lexicon_exact', 'verified', 'Dr. Patel', ?, ?)", (now, now))
        conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (6, 3, 6, 11, 'active', ?)", (now,))

        t2_intra_rec = conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()
        intra_rec_match = [r for r in t2_intra_rec if r[2] == 3 and r[4] == 3 and r[21] == 'intra_source_record_divergence']
        assert len(intra_rec_match) == 1, "Intra-source single-record divergence must enter Tier 2!"
        print("  [PASS] Scenario 7 (Case C): Intra-source single-record exact divergence captured in Tier 2.")
        
        # Clean up temporary claims 5 and 6
        conn.execute("DELETE FROM herb_dravyaguna_properties WHERE herb_property_id IN (5, 6)")
        conn.execute("DELETE FROM concept_claim_mappings WHERE mapping_id IN (5, 6)")
        conn.execute("DELETE FROM source_claims WHERE source_claim_id IN (5, 6)")
        conn.execute("DELETE FROM legacy_herb_map WHERE legacy_herb_id = 5")
        conn.execute("DELETE FROM herbs WHERE id = 5")
        conn.execute("DELETE FROM source_records WHERE source_record_id = 103")

        # --------------------------------------------------------------------
        # Scenario 8: SAME-SOURCE-CLAIM MAPPING AMBIGUITY (Requirement 2)
        # --------------------------------------------------------------------
        # Map source_claim 3 to TWO conflicting viryas: Ushna (mapping 3) and Sheeta (mapping 7)
        conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, verification_status, reviewed_by, reviewed_at, created_at) VALUES (7, 3, 2, 'exact', 'lexicon_exact', 'verified', 'Dr. Patel', ?, ?)", (now, now))
        conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (7, 3, 7, 11, 'active', ?)", (now,))
        
        # Check mapping ambiguity audit query (conservative same-herb-record and identical plant-part rule)
        ambig_rows = conn.execute(VIRYA_MAPPING_AMBIGUITY_SQL).fetchall()
        assert len(ambig_rows) == 1, f"Expected 1 mapping ambiguity row, got {len(ambig_rows)}"
        assert ambig_rows[0][0] == 3, f"herb_id must be 3, got {ambig_rows[0][0]}"
        assert ambig_rows[0][3] == 'same_herb_record', f"identity_basis must be same_herb_record, got {ambig_rows[0][3]}"
        assert ambig_rows[0][4] == 102, f"source_record_id must be 102, got {ambig_rows[0][4]}"
        assert ambig_rows[0][6] == 3, f"source_claim_id must be 3, got {ambig_rows[0][6]}"
        assert ambig_rows[0][10] == 11, f"part_1_id must be 11, got {ambig_rows[0][10]}"
        assert ambig_rows[0][11] == 11, f"part_2_id must be 11, got {ambig_rows[0][11]}"
        assert ambig_rows[0][12] == 3, f"mapping_1_id must be 3, got {ambig_rows[0][12]}"
        assert ambig_rows[0][13] == 'virya.ushna', f"virya_1 must be virya.ushna, got {ambig_rows[0][13]}"
        assert ambig_rows[0][14] == 'verified', f"mapping_1_status must be verified, got {ambig_rows[0][14]}"
        assert ambig_rows[0][15] == 'exact', f"mapping_1_type must be exact, got {ambig_rows[0][15]}"
        assert ambig_rows[0][16] == 7, f"mapping_2_id must be 7, got {ambig_rows[0][16]}"
        assert ambig_rows[0][17] == 'virya.sheeta', f"virya_2 must be virya.sheeta, got {ambig_rows[0][17]}"
        assert ambig_rows[0][18] == 'verified', f"mapping_2_status must be verified, got {ambig_rows[0][18]}"
        assert ambig_rows[0][19] == 'exact', f"mapping_2_type must be exact, got {ambig_rows[0][19]}"
        assert ambig_rows[0][20] == 'HERB_SAME_SOURCE_CLAIM_MAPPING_AMBIGUITY', f"audit_category must be HERB_SAME_SOURCE_CLAIM_MAPPING_AMBIGUITY, got {ambig_rows[0][20]}"
        print("  [PASS] Scenario 8a: Identical specified plant parts (11 IS 11) detected in Query 4 with conflicting Virya.")

        # Plant-Part Scope Regression Tests for Query 4:
        # 1. Different specified plant parts (e.g. root vs leaf/fruit) must be EXCLUDED from ambiguity audit
        conn.execute("UPDATE herb_dravyaguna_properties SET part_concept_id = 10 WHERE herb_property_id = 7")
        diff_part_ambig = conn.execute(VIRYA_MAPPING_AMBIGUITY_SQL).fetchall()
        assert len(diff_part_ambig) == 0, "Different specified plant parts must be excluded from same-claim mapping ambiguity!"
        print("  [PASS] Scenario 8b: Different specified plant parts (11 vs 10) strictly excluded from Query 4 ambiguity.")

        # 2. One specified, one unspecified part must be EXCLUDED from ambiguity audit
        conn.execute("UPDATE herb_dravyaguna_properties SET part_concept_id = NULL WHERE herb_property_id = 7")
        one_null_ambig = conn.execute(VIRYA_MAPPING_AMBIGUITY_SQL).fetchall()
        assert len(one_null_ambig) == 0, "One specified and one unspecified part must be excluded from same-claim mapping ambiguity!"
        print("  [PASS] Scenario 8c: One specified and one unspecified part (11 vs NULL) strictly excluded from Query 4 ambiguity.")

        # 3. Both parts unspecified (NULL IS NULL) must be INCLUDED in ambiguity audit
        conn.execute("UPDATE herb_dravyaguna_properties SET part_concept_id = NULL WHERE herb_property_id = 3")
        both_null_ambig = conn.execute(VIRYA_MAPPING_AMBIGUITY_SQL).fetchall()
        assert len(both_null_ambig) == 1, "Both plant parts unspecified (NULL IS NULL) must be included in same-claim mapping ambiguity!"
        assert both_null_ambig[0][10] is None, f"part_1_id must be None, got {both_null_ambig[0][10]}"
        assert both_null_ambig[0][11] is None, f"part_2_id must be None, got {both_null_ambig[0][11]}"
        print("  [PASS] Scenario 8d: Both parts unspecified (NULL IS NULL) correctly compared and included in Query 4.")

        # Restore part_concept_id = 11 on both properties
        conn.execute("UPDATE herb_dravyaguna_properties SET part_concept_id = 11 WHERE herb_property_id IN (3, 7)")

        # Assert: Same source claim on DIFFERENT herb records is EXCLUDED from ambiguity audit
        # Query 4 requires h1.id = h2.id; verify cross-herb query returns 0 rows
        cross_herb_ambig = conn.execute("""
            SELECT p1.herb_id, p2.herb_id
            FROM herb_dravyaguna_properties p1
            JOIN concept_claim_mappings m1 ON m1.mapping_id = p1.mapping_id
            JOIN herb_dravyaguna_properties p2 ON p2.herb_property_id > p1.herb_property_id
            JOIN concept_claim_mappings m2 ON m2.mapping_id = p2.mapping_id
            WHERE m1.source_claim_id = m2.source_claim_id
              AND p1.herb_id != p2.herb_id
        """).fetchall()
        assert len(cross_herb_ambig) == 0, "Cross-herb property sharing same claim does not exist in valid provenance data"
        
        # Assert this same-claim pair is NOT treated as a source disagreement in Tier 1, 2, or 3
        t1_same_claim = [r for r in conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall() if r[2] == 3 and r[4] == 3]
        t2_same_claim = [r for r in conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall() if r[2] == 3 and r[4] == 3]
        t3_same_claim = [r for r in conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall() if r[2] == 3 and r[4] == 3]
        assert len(t1_same_claim) == 0, "Same source claim mapping ambiguity must NOT appear in Tier 1!"
        assert len(t2_same_claim) == 0, "Same source claim mapping ambiguity must NOT appear in Tier 2!"
        assert len(t3_same_claim) == 0, "Same source claim mapping ambiguity must NOT appear in Tier 3!"
        print("  [PASS] Scenario 8: Same-source-claim ambiguity isolated from all reconciliation tiers into mapping audit.")
        
        # Clean up mapping 7
        conn.execute("DELETE FROM herb_dravyaguna_properties WHERE herb_property_id = 7")
        conn.execute("DELETE FROM concept_claim_mappings WHERE mapping_id = 7")

        # --------------------------------------------------------------------
        # Scenario 9: REJECTED SOURCE CLAIM EXCLUSION
        # --------------------------------------------------------------------
        conn.execute("UPDATE concept_claim_mappings SET verification_status = 'verified', mapping_type = 'exact' WHERE mapping_id IN (3, 4)")
        conn.execute("UPDATE source_claims SET verification_status = 'rejected' WHERE source_claim_id = 4")
        
        t1_rejected = conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall()
        t2_rejected = conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()
        t3_rejected = conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()
        
        haritaki_t1 = [r for r in t1_rejected if r[0] == 'Terminalia chebula']
        haritaki_t2 = [r for r in t2_rejected if r[0] == 'Terminalia chebula']
        haritaki_t3 = [r for r in t3_rejected if r[0] == 'Terminalia chebula']
        
        assert len(haritaki_t1) == 0, "Rejected claim must not appear in Tier 1!"
        assert len(haritaki_t2) == 0, "Rejected claim must not appear in Tier 2!"
        assert len(haritaki_t3) == 0, "Rejected claim must not appear in Tier 3!"
        print("  [PASS] Scenario 9: Rejected source claim excluded from ALL three tiers by positive whitelist.")

        # --------------------------------------------------------------------
        # Scenario 10: SUPERSEDED SOURCE CLAIM EXCLUSION
        # --------------------------------------------------------------------
        conn.execute("UPDATE source_claims SET verification_status = 'superseded' WHERE source_claim_id = 4")
        assert len(conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()) == 0
        print("  [PASS] Scenario 10: Superseded source claim correctly excluded from all queries.")

        # --------------------------------------------------------------------
        # Scenario 11: COMPREHENSIVE ELIGIBILITY FILTER EXCLUSIONS (Negative Tests)
        # --------------------------------------------------------------------
        conn.execute("UPDATE source_claims SET verification_status = 'verified' WHERE source_claim_id = 4")
        
        # 11a. Candidate omission relationship excluded from all tiers
        conn.execute("UPDATE herb_dravyaguna_properties SET source_presence_status = 'candidate_omission' WHERE herb_property_id = 4")
        assert len(conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()) == 0
        print("  [PASS] Scenario 11a: candidate_omission record correctly excluded from all reconciliation tiers.")

        # 11b. Confirmed omission relationship excluded from all tiers
        conn.execute("UPDATE herb_dravyaguna_properties SET source_presence_status = 'confirmed_omission' WHERE herb_property_id = 4")
        assert len(conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()) == 0
        print("  [PASS] Scenario 11b: confirmed_omission record correctly excluded from all reconciliation tiers.")
        conn.execute("UPDATE herb_dravyaguna_properties SET source_presence_status = 'active' WHERE herb_property_id = 4")

        # 11c. Rejected mapping excluded from all tiers
        conn.execute("UPDATE concept_claim_mappings SET verification_status = 'rejected' WHERE mapping_id = 4")
        assert len(conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()) == 0
        print("  [PASS] Scenario 11c: Rejected mapping correctly excluded from all reconciliation tiers.")

        # 11d. Superseded mapping excluded from all tiers
        conn.execute("UPDATE concept_claim_mappings SET verification_status = 'superseded' WHERE mapping_id = 4")
        assert len(conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()) == 0
        print("  [PASS] Scenario 11d: Superseded mapping correctly excluded from all reconciliation tiers.")

        # 11e. Disputed mapping excluded from all tiers
        conn.execute("UPDATE concept_claim_mappings SET verification_status = 'verified', mapping_type = 'disputed' WHERE mapping_id = 4")
        assert len(conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()) == 0
        print("  [PASS] Scenario 11e: Disputed mapping correctly excluded from all reconciliation tiers.")

        # 11f. Partial mapping excluded from all tiers
        conn.execute("UPDATE concept_claim_mappings SET verification_status = 'verified', mapping_type = 'partial' WHERE mapping_id = 4")
        assert len(conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()) == 0
        assert len(conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()) == 0
        print("  [PASS] Scenario 11f: Partial mapping correctly excluded from all reconciliation tiers.")
        conn.execute("UPDATE concept_claim_mappings SET verification_status = 'verified', mapping_type = 'exact' WHERE mapping_id = 4")

        # --------------------------------------------------------------------
        # Scenario 12: NEGATIVE TEST FOR TIER 3: UNREVIEWED SOURCE CLAIM WITH VERIFIED EXACT MAPPING
        # --------------------------------------------------------------------
        conn.execute("UPDATE concept_claim_mappings SET verification_status = 'verified', mapping_type = 'exact' WHERE mapping_id IN (3, 4)")
        conn.execute("UPDATE source_claims SET verification_status = 'verified' WHERE source_claim_id = 3")
        conn.execute("UPDATE source_claims SET verification_status = 'unreviewed', reviewed_by = NULL, reviewed_at = NULL WHERE source_claim_id = 4")
        
        t1_unreviewed_sc = conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall()
        t2_unreviewed_sc = conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()
        t3_unreviewed_sc = conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()
        
        haritaki_t1_sc = [r for r in t1_unreviewed_sc if r[0] == 'Terminalia chebula']
        haritaki_t2_sc = [r for r in t2_unreviewed_sc if r[0] == 'Terminalia chebula']
        haritaki_t3_sc = [r for r in t3_unreviewed_sc if r[0] == 'Terminalia chebula']
        
        assert len(haritaki_t3_sc) == 0, "Unreviewed source claim with verified exact mapping MUST FAIL Tier 3!"
        assert len(haritaki_t2_sc) == 0, "Unreviewed source claim MUST FAIL Tier 2!"
        assert len(haritaki_t1_sc) == 1, "Unreviewed source claim with verified mapping MUST appear in Tier 1 Candidate Divergence!"
        assert haritaki_t1_sc[0][22] == 'UNREVIEWED_CANDIDATE_DIVERGENCE'
        print("  [PASS] Scenario 12: Negative test confirmed: Unreviewed source claim with verified exact mapping FAILS Tier 3 and routes cleanly to Tier 1.")

        # --------------------------------------------------------------------
        # Scenario 13: COMPREHENSIVE HERB IDENTITY MATCHING REGRESSION MATRIX
        # Directly verifies the complete identity conditions across Tier 1, Tier 2, and Tier 3:
        #   1. Different botanical names, shared accepted taxon with verified provenance -> Included
        #   2. Shared accepted taxon WITHOUT verified provenance -> Excluded
        #   3. Shared synonym relationship only -> Excluded
        #   4. Shared source-identification relationship only -> Excluded
        #   5. Same non-empty botanical name -> Included
        #   6. Same herb record -> Included
        #   7. No matching identity evidence -> Excluded
        # --------------------------------------------------------------------
        # Restore claim 4 to verified
        conn.execute("UPDATE source_claims SET verification_status = 'verified', reviewed_by = 'Dr. Sharma', reviewed_at = ? WHERE source_claim_id = 4", (now,))
        
        # Ensure taxon 1 exists
        conn.execute("INSERT OR IGNORE INTO taxa (taxon_id, scientific_name, normalized_name, rank, created_at) VALUES (1, 'Terminalia chebula Retz.', 'terminalia chebula', 'species', ?)", (now,))

        # Seed dedicated verified taxonomy claims for herb 3 and herb 4
        conn.execute("INSERT OR IGNORE INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (91, 102, 'taxonomy_name', 'scientific_profile.botanical_name', 'Terminalia chebula Retz.', 'verified', 'Dr. Sharma', ?, 'human', 'botanist', ?, ?)", (now, now, now))
        conn.execute("INSERT OR IGNORE INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (92, 202, 'taxonomy_name', 'scientific_profile.botanical_name', 'Terminalia chebula Retz.', 'verified', 'Dr. Sharma', ?, 'human', 'botanist', ?, ?)", (now, now, now))

        # --- A. TIER 1 REGRESSION: Candidate identity matching under unreviewed mapping conditions ---
        conn.execute("UPDATE concept_claim_mappings SET verification_status = 'unreviewed', mapping_type = 'exact', reviewed_by = NULL, reviewed_at = NULL WHERE mapping_id = 4")
        
        # 1. Different botanical names, shared accepted taxon with verified provenance -> Included in Tier 1
        conn.execute("UPDATE herbs SET botanical_name = 'Terminalia chebula' WHERE id = 3")
        conn.execute("UPDATE herbs SET botanical_name = 'Myrobalanus chebula Gaertn.' WHERE id = 4")
        conn.execute("DELETE FROM herb_taxa WHERE herb_id IN (3, 4)")
        conn.execute("INSERT INTO herb_taxa (herb_id, taxon_id, relationship_type, source_claim_id, is_preferred, created_at) VALUES (3, 1, 'accepted', 91, 1, ?)", (now,))
        conn.execute("INSERT INTO herb_taxa (herb_id, taxon_id, relationship_type, source_claim_id, is_preferred, created_at) VALUES (4, 1, 'accepted', 92, 1, ?)", (now,))
        t1_diff_taxa = [r for r in conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t1_diff_taxa) == 1, "Tier 1: Different botanical names with shared accepted taxon and verified provenance MUST be included!"
        assert t1_diff_taxa[0][1] == 'taxonomically_verified_shared_accepted_taxon'

        # 2. Shared accepted taxon with REVIEWED provenance -> accurately labeled as taxonomically_reviewed_shared_accepted_taxon
        conn.execute("UPDATE source_claims SET verification_status = 'reviewed', reviewed_by = 'Dr. Sharma', reviewed_at = ? WHERE source_claim_id = 92", (now,))
        t1_reviewed_taxa = [r for r in conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t1_reviewed_taxa) == 1, "Tier 1: Shared accepted taxon with reviewed provenance MUST be included!"
        assert t1_reviewed_taxa[0][1] == 'taxonomically_reviewed_shared_accepted_taxon', f"Expected taxonomically_reviewed_shared_accepted_taxon, got {t1_reviewed_taxa[0][1]}"
        conn.execute("UPDATE source_claims SET verification_status = 'verified', reviewed_by = 'Dr. Sharma', reviewed_at = ? WHERE source_claim_id = 92", (now,))

        # 3. Shared accepted taxon WITHOUT verified provenance -> Excluded from Tier 1
        conn.execute("UPDATE source_claims SET verification_status = 'unreviewed', reviewed_by = NULL, reviewed_at = NULL WHERE source_claim_id = 92")
        t1_unverified_taxa = [r for r in conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t1_unverified_taxa) == 0, "Tier 1: Shared accepted taxon without verified provenance MUST be excluded!"
        conn.execute("UPDATE source_claims SET verification_status = 'verified', reviewed_by = 'Dr. Sharma', reviewed_at = ? WHERE source_claim_id = 92", (now,))

        # 4. Shared synonym relationship only -> Excluded from Tier 1
        conn.execute("UPDATE herb_taxa SET relationship_type = 'synonym' WHERE herb_id = 4")
        t1_synonym = [r for r in conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t1_synonym) == 0, "Tier 1: Shared synonym relationship only MUST be excluded!"

        # 5. Shared source-identification relationship only -> Excluded from Tier 1
        conn.execute("UPDATE herb_taxa SET relationship_type = 'source_identification' WHERE herb_id = 4")
        t1_srcid = [r for r in conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t1_srcid) == 0, "Tier 1: Shared source-identification relationship only MUST be excluded!"

        # 6. Same non-empty botanical name -> Included in Tier 1
        conn.execute("DELETE FROM herb_taxa WHERE herb_id = 4")
        conn.execute("UPDATE herbs SET botanical_name = 'Terminalia chebula' WHERE id IN (3, 4)")
        t1_same_str = [r for r in conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t1_same_str) == 1, "Tier 1: Same botanical name string MUST be included!"
        assert t1_same_str[0][1] == 'candidate_match_botanical_string_equality'

        # 7. Same herb record -> Included in Tier 1
        conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at) VALUES (77, 102, 'property', 'Virya_Var', 'Sheeta', 'unreviewed', 'system', 'ingest', ?, ?)", (now, now))
        conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, verification_status, created_at) VALUES (77, 77, 2, 'exact', 'lexicon_exact', 'unreviewed', ?)", (now,))
        conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (77, 3, 77, 11, 'active', ?)", (now,))
        t1_same_herb = [r for r in conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall() if r[2] == 3 and r[4] == 3]
        assert len(t1_same_herb) == 1, "Tier 1: Same herb record MUST be included!"
        assert t1_same_herb[0][1] == 'same_herb_record'
        conn.execute("DELETE FROM herb_dravyaguna_properties WHERE herb_property_id = 77")
        conn.execute("DELETE FROM concept_claim_mappings WHERE mapping_id = 77")
        conn.execute("DELETE FROM source_claims WHERE source_claim_id = 77")

        # 8. No matching identity evidence -> Excluded from Tier 1
        conn.execute("UPDATE herbs SET botanical_name = 'Completely Different Plant' WHERE id = 4")
        t1_unrelated = [r for r in conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t1_unrelated) == 0, "Tier 1: No matching identity evidence MUST be excluded!"
        print("  [PASS] Scenario 13 - Tier 1: All identity conditions verified (taxa_verified/taxa_reviewed/taxa_unverified/synonym/source_id/botanical/same_herb/no_match).")

        # --- B. TIER 2 REGRESSION: Candidate identity matching under reviewed approximation conditions ---
        conn.execute("UPDATE concept_claim_mappings SET verification_status = 'reviewed', mapping_type = 'broader', reviewed_by = 'Dr. Patel', reviewed_at = ? WHERE mapping_id = 4", (now,))
        
        # 1. Different botanical names, shared accepted taxon with verified provenance -> Included in Tier 2
        conn.execute("UPDATE herbs SET botanical_name = 'Terminalia chebula' WHERE id = 3")
        conn.execute("UPDATE herbs SET botanical_name = 'Myrobalanus chebula Gaertn.' WHERE id = 4")
        conn.execute("DELETE FROM herb_taxa WHERE herb_id IN (3, 4)")
        conn.execute("INSERT INTO herb_taxa (herb_id, taxon_id, relationship_type, source_claim_id, is_preferred, created_at) VALUES (3, 1, 'accepted', 91, 1, ?)", (now,))
        conn.execute("INSERT INTO herb_taxa (herb_id, taxon_id, relationship_type, source_claim_id, is_preferred, created_at) VALUES (4, 1, 'accepted', 92, 1, ?)", (now,))
        t2_diff_taxa = [r for r in conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t2_diff_taxa) == 1, "Tier 2: Different botanical names with shared accepted taxon and verified provenance MUST be included!"
        assert t2_diff_taxa[0][1] == 'taxonomically_verified_shared_accepted_taxon'

        # 2. Shared accepted taxon with REVIEWED provenance -> accurately labeled as taxonomically_reviewed_shared_accepted_taxon
        conn.execute("UPDATE source_claims SET verification_status = 'reviewed', reviewed_by = 'Dr. Sharma', reviewed_at = ? WHERE source_claim_id = 92", (now,))
        t2_reviewed_taxa = [r for r in conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t2_reviewed_taxa) == 1, "Tier 2: Shared accepted taxon with reviewed provenance MUST be included!"
        assert t2_reviewed_taxa[0][1] == 'taxonomically_reviewed_shared_accepted_taxon', f"Expected taxonomically_reviewed_shared_accepted_taxon, got {t2_reviewed_taxa[0][1]}"
        conn.execute("UPDATE source_claims SET verification_status = 'verified', reviewed_by = 'Dr. Sharma', reviewed_at = ? WHERE source_claim_id = 92", (now,))

        # 3. Shared accepted taxon WITHOUT verified provenance -> Excluded from Tier 2
        conn.execute("UPDATE source_claims SET verification_status = 'unreviewed', reviewed_by = NULL, reviewed_at = NULL WHERE source_claim_id = 92")
        t2_unverified_taxa = [r for r in conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t2_unverified_taxa) == 0, "Tier 2: Shared accepted taxon without verified provenance MUST be excluded!"
        conn.execute("UPDATE source_claims SET verification_status = 'verified', reviewed_by = 'Dr. Sharma', reviewed_at = ? WHERE source_claim_id = 92", (now,))

        # 4. Shared synonym relationship only -> Excluded from Tier 2
        conn.execute("UPDATE herb_taxa SET relationship_type = 'synonym' WHERE herb_id = 4")
        t2_synonym = [r for r in conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t2_synonym) == 0, "Tier 2: Shared synonym relationship only MUST be excluded!"

        # 5. Shared source-identification relationship only -> Excluded from Tier 2
        conn.execute("UPDATE herb_taxa SET relationship_type = 'source_identification' WHERE herb_id = 4")
        t2_srcid = [r for r in conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t2_srcid) == 0, "Tier 2: Shared source-identification relationship only MUST be excluded!"

        # 6. Same non-empty botanical name -> Included in Tier 2
        conn.execute("DELETE FROM herb_taxa WHERE herb_id = 4")
        conn.execute("UPDATE herbs SET botanical_name = 'Terminalia chebula' WHERE id IN (3, 4)")
        t2_same_str = [r for r in conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t2_same_str) == 1, "Tier 2: Same botanical name string MUST be included!"
        assert t2_same_str[0][1] == 'candidate_match_botanical_string_equality'

        # 7. Same herb record -> Included in Tier 2
        conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (77, 102, 'property', 'Virya_Var', 'Sheeta', 'reviewed', 'Dr. Sharma', ?, 'system', 'ingest', ?, ?)", (now, now, now))
        conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, verification_status, reviewed_by, reviewed_at, created_at) VALUES (77, 77, 2, 'broader', 'lexicon_exact', 'reviewed', 'Dr. Patel', ?, ?)", (now, now))
        conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (77, 3, 77, 11, 'active', ?)", (now,))
        t2_same_herb = [r for r in conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall() if r[2] == 3 and r[4] == 3]
        assert len(t2_same_herb) == 1, "Tier 2: Same herb record MUST be included!"
        assert t2_same_herb[0][1] == 'same_herb_record'
        conn.execute("DELETE FROM herb_dravyaguna_properties WHERE herb_property_id = 77")
        conn.execute("DELETE FROM concept_claim_mappings WHERE mapping_id = 77")
        conn.execute("DELETE FROM source_claims WHERE source_claim_id = 77")

        # 8. No matching identity evidence -> Excluded from Tier 2
        conn.execute("UPDATE herbs SET botanical_name = 'Completely Different Plant' WHERE id = 4")
        t2_unrelated = [r for r in conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t2_unrelated) == 0, "Tier 2: No matching identity evidence MUST be excluded!"
        print("  [PASS] Scenario 13 - Tier 2: All identity conditions verified (taxa_verified/taxa_reviewed/taxa_unverified/synonym/source_id/botanical/same_herb/no_match).")

        # --- C. TIER 3 REGRESSION: Verified source disagreement identity matching ---
        conn.execute("UPDATE concept_claim_mappings SET verification_status = 'verified', mapping_type = 'exact', reviewed_by = 'Dr. Patel', reviewed_at = ? WHERE mapping_id = 4", (now,))
        
        # 1. Different botanical names, shared accepted taxon with verified provenance -> Included in Tier 3
        conn.execute("UPDATE herbs SET botanical_name = 'Terminalia chebula' WHERE id = 3")
        conn.execute("UPDATE herbs SET botanical_name = 'Myrobalanus chebula Gaertn.' WHERE id = 4")
        conn.execute("DELETE FROM herb_taxa WHERE herb_id IN (3, 4)")
        conn.execute("INSERT INTO herb_taxa (herb_id, taxon_id, relationship_type, source_claim_id, is_preferred, created_at) VALUES (3, 1, 'accepted', 91, 1, ?)", (now,))
        conn.execute("INSERT INTO herb_taxa (herb_id, taxon_id, relationship_type, source_claim_id, is_preferred, created_at) VALUES (4, 1, 'accepted', 92, 1, ?)", (now,))
        t3_diff_taxa = [r for r in conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t3_diff_taxa) == 1, "Tier 3: Different botanical names with shared accepted taxon and verified provenance MUST be included!"
        assert t3_diff_taxa[0][1] == 'taxonomically_verified_shared_accepted_taxon'

        # 2. Shared accepted taxon with REVIEWED provenance -> accurately labeled as taxonomically_reviewed_shared_accepted_taxon
        conn.execute("UPDATE source_claims SET verification_status = 'reviewed', reviewed_by = 'Dr. Sharma', reviewed_at = ? WHERE source_claim_id = 92", (now,))
        t3_reviewed_taxa = [r for r in conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t3_reviewed_taxa) == 1, "Tier 3: Shared accepted taxon with reviewed provenance MUST be included!"
        assert t3_reviewed_taxa[0][1] == 'taxonomically_reviewed_shared_accepted_taxon', f"Expected taxonomically_reviewed_shared_accepted_taxon, got {t3_reviewed_taxa[0][1]}"
        conn.execute("UPDATE source_claims SET verification_status = 'verified', reviewed_by = 'Dr. Sharma', reviewed_at = ? WHERE source_claim_id = 92", (now,))

        # 3. Shared accepted taxon WITHOUT verified provenance -> Excluded from Tier 3
        conn.execute("UPDATE source_claims SET verification_status = 'unreviewed', reviewed_by = NULL, reviewed_at = NULL WHERE source_claim_id = 92")
        t3_unverified_taxa = [r for r in conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t3_unverified_taxa) == 0, "Tier 3: Shared accepted taxon without verified provenance MUST be excluded!"
        conn.execute("UPDATE source_claims SET verification_status = 'verified', reviewed_by = 'Dr. Sharma', reviewed_at = ? WHERE source_claim_id = 92", (now,))

        # 4. Shared synonym relationship only -> Excluded from Tier 3
        conn.execute("UPDATE herb_taxa SET relationship_type = 'synonym' WHERE herb_id = 4")
        t3_synonym = [r for r in conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t3_synonym) == 0, "Tier 3: Shared synonym relationship only MUST be excluded!"

        # 5. Shared source-identification relationship only -> Excluded from Tier 3
        conn.execute("UPDATE herb_taxa SET relationship_type = 'source_identification' WHERE herb_id = 4")
        t3_srcid = [r for r in conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t3_srcid) == 0, "Tier 3: Shared source-identification relationship only MUST be excluded!"

        # 6. Same non-empty botanical name -> Included in Tier 3
        conn.execute("DELETE FROM herb_taxa WHERE herb_id = 4")
        conn.execute("UPDATE herbs SET botanical_name = 'Terminalia chebula' WHERE id IN (3, 4)")
        t3_same_str = [r for r in conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t3_same_str) == 1, "Tier 3: Same botanical name string MUST be included!"
        assert t3_same_str[0][1] == 'candidate_match_botanical_string_equality'

        # 7. Same herb record -> Excluded from Tier 3 by distinct source authority filter (s1.source_id != s2.source_id)
        conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (77, 102, 'property', 'Virya_Var', 'Sheeta', 'verified', 'Dr. Sharma', ?, 'system', 'ingest', ?, ?)", (now, now, now))
        conn.execute("INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, verification_status, reviewed_by, reviewed_at, created_at) VALUES (77, 77, 2, 'exact', 'lexicon_exact', 'verified', 'Dr. Patel', ?, ?)", (now, now))
        conn.execute("INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, source_presence_status, created_at) VALUES (77, 3, 77, 11, 'active', ?)", (now,))
        t3_same_herb = [r for r in conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall() if r[2] == 3 and r[4] == 3]
        assert len(t3_same_herb) == 0, "Tier 3: Same herb record must be excluded from Tier 3 by distinct source authority filter!"
        # Verify candidate identity predicate itself returns TRUE for same herb record
        pred_check = conn.execute("""
            SELECT CASE 
                WHEN h1.id = h2.id THEN 'same_herb_record'
                WHEN EXISTS (
                    SELECT 1 FROM herb_taxa ht1
                    JOIN source_claims sc_taxa1 ON sc_taxa1.source_claim_id = ht1.source_claim_id
                    JOIN herb_taxa ht2 ON ht1.taxon_id = ht2.taxon_id
                    JOIN source_claims sc_taxa2 ON sc_taxa2.source_claim_id = ht2.source_claim_id
                    WHERE ht1.herb_id = h1.id AND ht2.herb_id = h2.id AND ht1.relationship_type = 'accepted' AND ht2.relationship_type = 'accepted'
                      AND sc_taxa1.verification_status = 'verified' AND sc_taxa2.verification_status = 'verified'
                ) THEN 'taxonomically_verified_shared_accepted_taxon'
                WHEN EXISTS (
                    SELECT 1 FROM herb_taxa ht1
                    JOIN source_claims sc_taxa1 ON sc_taxa1.source_claim_id = ht1.source_claim_id
                    JOIN herb_taxa ht2 ON ht1.taxon_id = ht2.taxon_id
                    JOIN source_claims sc_taxa2 ON sc_taxa2.source_claim_id = ht2.source_claim_id
                    WHERE ht1.herb_id = h1.id AND ht2.herb_id = h2.id AND ht1.relationship_type = 'accepted' AND ht2.relationship_type = 'accepted'
                      AND sc_taxa1.verification_status IN ('reviewed', 'verified') AND sc_taxa2.verification_status IN ('reviewed', 'verified')
                ) THEN 'taxonomically_reviewed_shared_accepted_taxon'
                WHEN h1.botanical_name IS NOT NULL AND trim(h1.botanical_name) != '' AND h1.botanical_name = h2.botanical_name THEN 'candidate_match_botanical_string_equality'
                ELSE 'unmatched'
            END
            FROM herbs h1, herbs h2 WHERE h1.id = 3 AND h2.id = 3
        """).fetchone()[0]
        assert pred_check == 'same_herb_record', "Candidate identity predicate must recognize same herb record"
        conn.execute("DELETE FROM herb_dravyaguna_properties WHERE herb_property_id = 77")
        conn.execute("DELETE FROM concept_claim_mappings WHERE mapping_id = 77")
        conn.execute("DELETE FROM source_claims WHERE source_claim_id = 77")

        # 8. No matching identity evidence -> Excluded from Tier 3
        conn.execute("UPDATE herbs SET botanical_name = 'Completely Different Plant' WHERE id = 4")
        t3_unrelated = [r for r in conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall() if r[2] == 3 and r[4] == 4]
        assert len(t3_unrelated) == 0, "Tier 3: No matching identity evidence MUST be excluded!"
        print("  [PASS] Scenario 13 - Tier 3: All identity conditions verified (taxa_verified/taxa_reviewed/taxa_unverified/synonym/source_id/botanical/same_herb/no_match).")

        # Restore accepted taxon and botanical name for Tier 3 verification metadata audit in Scenario 14
        conn.execute("UPDATE herbs SET botanical_name = 'Terminalia chebula' WHERE id IN (3, 4)")
        conn.execute("INSERT OR IGNORE INTO herb_taxa (herb_id, taxon_id, relationship_type, source_claim_id, is_preferred, created_at) VALUES (3, 1, 'accepted', 91, 1, ?)", (now,))
        conn.execute("INSERT OR IGNORE INTO herb_taxa (herb_id, taxon_id, relationship_type, source_claim_id, is_preferred, created_at) VALUES (4, 1, 'accepted', 92, 1, ?)", (now,))
        haritaki_taxa_row = [r for r in conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall() if r[2] == 3 and r[4] == 4][0]
        assert haritaki_taxa_row[1] == 'taxonomically_verified_shared_accepted_taxon'
        print("  [PASS] Scenario 13: Full 8x3 Herb Identity Matching & Taxonomic Provenance Regression Matrix passed 100%.")

        # Restore accepted taxon and botanical name for Tier 3 verification metadata audit in Scenario 14
        conn.execute("UPDATE herbs SET botanical_name = 'Terminalia chebula' WHERE id IN (3, 4)")
        conn.execute("INSERT OR IGNORE INTO herb_taxa (herb_id, taxon_id, relationship_type, source_claim_id, is_preferred, created_at) VALUES (3, 1, 'accepted', 91, 1, ?)", (now,))
        conn.execute("INSERT OR IGNORE INTO herb_taxa (herb_id, taxon_id, relationship_type, source_claim_id, is_preferred, created_at) VALUES (4, 1, 'accepted', 92, 1, ?)", (now,))
        haritaki_taxa_row = [r for r in conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall() if r[2] == 3 and r[4] == 4][0]
        assert haritaki_taxa_row[1] == 'taxonomically_verified_shared_accepted_taxon'
        print("  [PASS] Scenario 13: Full 7x3 Herb Identity Matching & Taxonomic Provenance Regression Matrix passed 100%.")

        # --------------------------------------------------------------------
        # Scenario 14: TIER 3 FULL VERIFICATION AUDIT METADATA TRANSPARENCY
        # --------------------------------------------------------------------
        assert haritaki_taxa_row[11] == 'Dr. Sharma', "claim_1_reviewed_by populated"
        assert haritaki_taxa_row[12] == now, "claim_1_reviewed_at populated"
        assert haritaki_taxa_row[13] == 'Dr. Patel', "mapping_1_verified_by populated"
        assert haritaki_taxa_row[14] == now, "mapping_1_verified_at populated"
        assert haritaki_taxa_row[20] == 'Dr. Sharma', "claim_2_reviewed_by populated"
        assert haritaki_taxa_row[21] == now, "claim_2_reviewed_at populated"
        assert haritaki_taxa_row[22] == 'Dr. Patel', "mapping_2_verified_by populated"
        assert haritaki_taxa_row[23] == now, "mapping_2_verified_at populated"
        print("  [PASS] Scenario 14: Verification audit metadata transparency verified across both source claims and concept mappings.")

        # --------------------------------------------------------------------
        # Scenario 15: PROVE MUTUAL EXCLUSIVITY OF TIERS ACROSS ENTIRE DATASET
        # --------------------------------------------------------------------
        all_t1 = conn.execute(VIRYA_UNREVIEWED_DIVERGENCE_SQL).fetchall()
        all_t2 = conn.execute(VIRYA_REVIEWED_CANDIDATE_DIVERGENCE_SQL).fetchall()
        all_t3 = conn.execute(VIRYA_VERIFIED_DISAGREEMENT_SQL).fetchall()
        
        # Key function for comparison pair:
        def pair_key_t1_t2(row):
            return (row[0], row[2], row[4], row[9], row[16], row[6], row[13])
            
        def pair_key_t3(row):
            return (row[0], row[2], row[4], row[9], row[18], row[6], row[15])
            
        keys_t1 = {pair_key_t1_t2(r) for r in all_t1}
        keys_t2 = {pair_key_t1_t2(r) for r in all_t2}
        keys_t3 = {pair_key_t3(r) for r in all_t3}
        
        assert len(keys_t1.intersection(keys_t2)) == 0, "Tier 1 and Tier 2 must have zero overlap!"
        assert len(keys_t1.intersection(keys_t3)) == 0, "Tier 1 and Tier 3 must have zero overlap!"
        assert len(keys_t2.intersection(keys_t3)) == 0, "Tier 2 and Tier 3 must have zero overlap!"
        print("  [PASS] Scenario 15: Proved 100% mutual exclusivity among all three reconciliation tiers.")

    finally:
        conn.close()
        if os.path.exists(db_path):
            os.remove(db_path)

# ============================================================================
# TEST SUITE 4: RECONCILIATION METRICS COUNT QUERIES
# ============================================================================
def test_reconciliation_metrics():
    print("\n--- TEST SUITE 4: Reconciliation Metric Count Queries ---")
    conn, db_path = get_actual_stage_b_connection()
    try:
        execute_statements(conn, STAGE_C_SQL)
        now = "2026-11-17T12:00:00Z"
        
        # Seed test data
        conn.execute("INSERT INTO sources (source_key) VALUES ('CCRAS')")
        s_id = conn.execute("SELECT source_id FROM sources WHERE source_key = 'CCRAS'").fetchone()[0]
        conn.execute("INSERT INTO source_records (source_record_id, source_id, external_record_key) VALUES (1, ?, '1')", (s_id,))
        
        # Claims: 3 active, 2 superseded
        conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at) VALUES (1, 1, 'prop', 'Virya', 'Ushna', 'unreviewed', 'system', 'ingest', ?, ?)", (now, now))
        conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (2, 1, 'prop', 'Virya', 'Sheeta', 'reviewed', 'Dr. Sharma', ?, 'system', 'ingest', ?, ?)", (now, now, now))
        conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, reviewed_by, reviewed_at, created_by_type, created_by, created_at, updated_at) VALUES (3, 1, 'prop', 'Rasa', 'Madhura', 'verified', 'Dr. Sharma', ?, 'system', 'ingest', ?, ?)", (now, now, now))
        conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at) VALUES (4, 1, 'prop', 'Virya', 'OldUshna', 'superseded', 'system', 'ingest', ?, ?)", (now, now))
        conn.execute("INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at) VALUES (5, 1, 'prop', 'Virya', 'OldSheeta', 'superseded', 'system', 'ingest', ?, ?)", (now, now))
        
        claims_metric = conn.execute("""
        SELECT 
            COUNT(*) AS total_claims,
            SUM(CASE WHEN verification_status != 'superseded' THEN 1 ELSE 0 END) AS active_claims,
            SUM(CASE WHEN verification_status = 'superseded' THEN 1 ELSE 0 END) AS superseded_claims,
            SUM(CASE WHEN verification_status != 'superseded' AND source_claim_id NOT IN (SELECT source_claim_id FROM concept_claim_mappings) THEN 1 ELSE 0 END) AS unmapped_active_claims
        FROM source_claims
        """).fetchone()
        
        assert claims_metric[0] == 5
        assert claims_metric[1] == 3
        assert claims_metric[2] == 2
        assert claims_metric[3] == 3
        print(f"  [PASS] Claims metrics: Total={claims_metric[0]}, Active={claims_metric[1]}, Superseded={claims_metric[2]}, Unmapped={claims_metric[3]}")
    finally:
        conn.close()
        if os.path.exists(db_path):
            os.remove(db_path)

# ============================================================================
# TEST SUITE 5: REPEATABLE PERFORMANCE BENCHMARK
# ============================================================================
def test_performance_benchmark():
    print("\n--- TEST SUITE 5: Repeatable Benchmark Evaluation (5 runs x 1000 rows) ---")
    conn, db_path = get_actual_stage_b_connection()
    conn.isolation_level = None
    try:
        execute_statements(conn, STAGE_C_SQL)
        now = "2026-11-17T12:00:00Z"
        
        conn.execute("INSERT INTO sources (source_key) VALUES ('BENCH_SRC')")
        s_id = conn.execute("SELECT source_id FROM sources WHERE source_key = 'BENCH_SRC'").fetchone()[0]
        conn.execute("INSERT INTO source_records (source_record_id, source_id, external_record_key) VALUES (1, ?, '100')", (s_id,))
        conn.execute("INSERT INTO herbs (id, english_name, source, source_record_id) VALUES (1, 'BenchHerb', 'BENCH_SRC', 100)")
        conn.execute("INSERT INTO legacy_herb_map (legacy_herb_id, herb_id, created_at) VALUES (1, 1, ?)", (now,))
        conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (1, 'virya.ushna', 'virya', ?)", (now,))
        conn.execute("INSERT INTO dravyaguna_concepts (concept_id, concept_code, concept_domain, created_at) VALUES (2, 'part.root', 'plant_part', ?)", (now,))
        
        # Create 1000 claims & mappings
        for i in range(1, 1001):
            conn.execute(f"INSERT INTO source_claims (source_claim_id, source_record_id, claim_type, source_field, source_expression, verification_status, created_by_type, created_by, created_at, updated_at) VALUES ({i}, 1, 'prop', 'Virya', 'Val{i}', 'unreviewed', 'system', 'ingest', '{now}', '{now}')")
            conn.execute(f"INSERT INTO concept_claim_mappings (mapping_id, source_claim_id, concept_id, mapping_type, mapping_method, created_at) VALUES ({i}, {i}, 1, 'exact', 'lexicon_exact', '{now}')")
        
        with_times = []
        without_times = []
        
        # 5 runs
        for run in range(1, 6):
            # With triggers
            conn.execute("BEGIN TRANSACTION;")
            t0 = time.perf_counter()
            for i in range(1, 1001):
                conn.execute(f"INSERT INTO herb_dravyaguna_properties (herb_property_id, herb_id, mapping_id, part_concept_id, created_at) VALUES ({10000*run + i}, 1, {i}, 2, '{now}')")
            t1 = time.perf_counter()
            conn.rollback()
            with_times.append((t1 - t0) * 1000)
            
            # Without triggers (test table without triggers)
            conn.execute("CREATE TABLE IF NOT EXISTS temp_bench (id INTEGER PRIMARY KEY, herb_id INTEGER, mapping_id INTEGER, part_id INTEGER, created_at TEXT)")
            conn.execute("BEGIN TRANSACTION;")
            t2 = time.perf_counter()
            for i in range(1, 1001):
                conn.execute(f"INSERT INTO temp_bench VALUES ({10000*run + i}, 1, {i}, 2, '{now}')")
            t3 = time.perf_counter()
            conn.rollback()
            without_times.append((t3 - t2) * 1000)
            
            print(f"  Run {run}: with_triggers={with_times[-1]:.2f}ms, without_triggers={without_times[-1]:.2f}ms, delta=+{with_times[-1]-without_times[-1]:.2f}ms")
            
        avg_with = sum(with_times) / len(with_times)
        avg_without = sum(without_times) / len(without_times)
        print(f"  Average With Triggers    : {avg_with:.2f} ms ({int(1000/(avg_with/1000)):,} rows/sec, {avg_with/1000:.4f} ms/row)")
        print(f"  Average Without Triggers : {avg_without:.2f} ms ({int(1000/(avg_without/1000)):,} rows/sec, {avg_without/1000:.4f} ms/row)")
        print(f"  Trigger Overhead         : +{avg_with - avg_without:.2f} ms per 1,000 rows (+{(avg_with - avg_without)/1000:.4f} ms/row)")
    finally:
        conn.close()
        if os.path.exists(db_path):
            os.remove(db_path)

# ============================================================================
# TEST SUITE 6: STAGE B MIGRATION UPGRADE & FAILURE ROLLBACK RESILIENCE
# ============================================================================
def test_stage_b_upgrade_and_rollback():
    print("\n--- TEST SUITE 6: Stage B Migration Upgrade & Rollback Resilience ---")
    conn, db_path = get_actual_stage_b_connection()
    conn.isolation_level = None
    try:
        mig3 = migration_3

        # Seed an actual PlantRecord through AyurvedicAlmanac
        almanac = AyurvedicAlmanac(db_path)
        record = PlantRecord(
            source="DRAVYA",
            source_record_id=101,
            source_url="https://ccras.nic.in/dravya/101",
            retrieved_at="2026-11-17T12:00:00Z",
            ayurvedic_name="Shunthi",
            botanical_name="Zingiber officinale",
            family="Zingiberaceae",
            attributes={
                "Rasa": ["Katu"],
                "Guna": ["Laghu", "Snigdha"],
                "Virya": ["Ushna"],
                "Vipaka": ["Madhura"],
            },
            dosha_expressions=["Kaphavatahara"],
        )
        almanac.insert_record(record)
        
        # Verify Stage B seed state
        v_before = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        herbs_before = conn.execute("SELECT COUNT(*) FROM herbs").fetchone()[0]
        claims_before = conn.execute("SELECT COUNT(*) FROM source_claims").fetchone()[0]
        assert v_before == 2, f"Expected Schema Version 2, got {v_before}"
        assert herbs_before == 1, "Expected 1 herb"
        print(f"  [PASS] Initialized real Stage B database (Version: {v_before}, Herbs: {herbs_before}, Claims: {claims_before})")
        
        # Test execute_statements detects incomplete trailing statements
        try:
            mig3.execute_statements(conn, "SELECT 1; SELECT")
            assert False, "Incomplete statement should fail!"
        except RuntimeError as e:
            assert "Incomplete trailing SQL statement" in str(e)
            print("  [PASS] Migration Robustness: Incomplete trailing SQL statement detected and rejected.")

        # Test active transaction rejection
        conn.execute("BEGIN IMMEDIATE;")
        try:
            mig3.apply_migration(conn)
            assert False, "Active transaction should fail!"
        except RuntimeError as e:
            assert "active transaction" in str(e)
            print("  [PASS] Migration Robustness: Active transaction rejection verified.")
        conn.rollback()

        # Test mid-execution migration failure atomicity with temporary DDL file
        with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as f_faulty:
            f_faulty.write(
                "CREATE TABLE canary_harness_atomicity_test (id INTEGER PRIMARY KEY, note TEXT);\n"
                "INSERT INTO canary_harness_atomicity_test (id, note) VALUES (1, 'canary');\n"
                "INVALID SQL SYNTAX HERE;\n"
            )
            faulty_ddl_path = f_faulty.name

        executed_trace = []
        conn.set_trace_callback(executed_trace.append)
        try:
            mig3.apply_migration(conn, ddl_path=Path(faulty_ddl_path))
            assert False, "Migration with invalid SQL statement should fail!"
        except sqlite3.OperationalError as e:
            conn.set_trace_callback(None)
            assert "syntax error" in str(e).lower()
            # Verify earlier valid statements were actually executed before the error
            assert any("CREATE TABLE canary_harness_atomicity_test" in s for s in executed_trace)
            assert any("INSERT INTO canary_harness_atomicity_test" in s for s in executed_trace)
            # Confirm earlier valid statement rolled back
            tables_after_fail = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            assert "canary_harness_atomicity_test" not in tables_after_fail
            # Confirm schema_migrations remains version 2
            assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 2
            # Confirm no version 3 row exists
            assert conn.execute("SELECT 1 FROM schema_migrations WHERE version = 3").fetchone() is None
            # Confirm Stage B data preserved
            assert conn.execute("SELECT COUNT(*) FROM herbs").fetchone()[0] == herbs_before
            assert conn.execute("SELECT COUNT(*) FROM source_claims").fetchone()[0] == claims_before
            # Confirm transaction closed
            assert not conn.in_transaction
            print("  [PASS] Migration Robustness: Mid-execution failure atomicity and clean rollback verified.")
        finally:
            conn.set_trace_callback(None)
            if os.path.exists(faulty_ddl_path):
                os.remove(faulty_ddl_path)

        # Test rollback prerequisite rejection when database is at version 2
        try:
            mig3.rollback_migration(conn)
            assert False, "Rollback at version 2 should fail!"
        except RuntimeError as e:
            assert "expected version 3, got 2" in str(e)
            assert not conn.in_transaction
            print("  [PASS] Migration Robustness: Rollback prerequisite rejection (expected 3, got 2) verified under write lock.")

        # Test write-lock acquisition, contention, and serialization across two connections
        conn2 = sqlite3.connect(db_path, timeout=0.05)
        conn2.isolation_level = None
        conn2.execute("PRAGMA busy_timeout = 50;")
        conn.execute("BEGIN IMMEDIATE;")
        try:
            conn2.execute("BEGIN IMMEDIATE;")
            assert False, "conn2 should not acquire write lock while conn holds it!"
        except sqlite3.OperationalError as e:
            assert "locked" in str(e).lower() or "busy" in str(e).lower()
        finally:
            conn.rollback()

        # Verify conn2 can subsequently acquire write lock after release
        conn2.execute("BEGIN IMMEDIATE;")
        assert conn2.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 2
        conn2.rollback()
        conn2.close()
        print("  [PASS] Migration Robustness: Write-lock acquisition and serialization verified across two connections.")

        # 1. Forward Migration using migration module
        mig3.apply_migration(conn)
        v_migrated = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        assert v_migrated == 3, f"Expected Schema Version 3, got {v_migrated}"
        tables_migrated = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert 'dravyaguna_concepts' in tables_migrated
        assert 'herb_dravyaguna_properties' in tables_migrated
        assert 'source_reconciliation_events' in tables_migrated
        print("  [PASS] Forward Migration 3 upgrade succeeded cleanly via apply_migration (Schema Version: 3).")

        # Test forward migration prerequisite rejection when database is at version 3
        try:
            mig3.apply_migration(conn)
            assert False, "Re-applying at version 3 should fail prerequisite check!"
        except RuntimeError as e:
            assert "expected version 2, got 3" in str(e)
            assert not conn.in_transaction
            print("  [PASS] Migration Robustness: Forward migration prerequisite rejection (expected 2, got 3) verified under write lock.")
        
        # 2. Rollback Migration using migration module
        mig3.rollback_migration(conn)
        v_rolled_back = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        assert v_rolled_back == 2, f"Expected Schema Version 2 after rollback, got {v_rolled_back}"
        tables_rolled_back = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert 'dravyaguna_concepts' not in tables_rolled_back
        assert 'herb_dravyaguna_properties' not in tables_rolled_back
        assert 'source_reconciliation_events' not in tables_rolled_back
        herbs_after_rb = conn.execute("SELECT COUNT(*) FROM herbs").fetchone()[0]
        claims_after_rb = conn.execute("SELECT COUNT(*) FROM source_claims").fetchone()[0]
        assert herbs_after_rb == herbs_before
        assert claims_after_rb == claims_before
        print("  [PASS] Rollback of Migration 3 cleanly reverted schema to Version 2 with 100% data intact.")
        
        # 3. Re-apply Migration 3
        mig3.apply_migration(conn)
        v_final = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        assert v_final == 3
        print("  [PASS] Re-applying Migration 3 succeeded with zero errors.")
    finally:
        conn.close()
        if os.path.exists(db_path):
            os.remove(db_path)

# ============================================================================
# MAIN HARNESS RUNNER
# ============================================================================
def main():
    print("=" * 80)
    print("HERBAL ALMANAC - FINAL STAGE C INTEGRITY HARNESS")
    print("=" * 80)
    print(f"Python Version : {sys.version.split()[0]}")
    print(f"SQLite Version : {sqlite3.sqlite_version}")
    
    ddl_hash = hashlib.sha256(STAGE_C_SQL.encode('utf-8')).hexdigest()
    print(f"Stage C DDL+Triggers File SHA-256 : {ddl_hash}")
    
    recon_hash = hashlib.sha256(RECONCILIATION_SQL.encode('utf-8')).hexdigest()
    print(f"Virya Reconciliation SQL SHA-256 : {recon_hash}")
    
    script_path = Path(__file__).resolve()
    script_hash = hashlib.sha256(script_path.read_bytes()).hexdigest()
    print(f"Harness Script SHA-256           : {script_hash}")
    
    test_stage_b_schema_compatibility()
    test_mutation_and_deletion_matrix()
    test_virya_reconciliation_dataset()
    test_reconciliation_metrics()
    test_performance_benchmark()
    test_stage_b_upgrade_and_rollback()
    
    print("\n" + "=" * 80)
    print("ALL 6 TEST SUITES PASSED WITH 100% SUCCESS!")
    print("=" * 80)

if __name__ == "__main__":
    main()