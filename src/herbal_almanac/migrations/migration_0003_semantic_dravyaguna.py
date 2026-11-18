"""
Herbal Almanac — Migration 0003: Semantic Dravyaguna Architecture
Upgrade and Rollback Implementation
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MIGRATION_VERSION = 3
MIGRATION_NAME = "semantic_dravyaguna"

DIR_PATH = Path(__file__).resolve().parent
DDL_FILE = DIR_PATH / "stage_c_ddl_and_triggers.sql"

STAGE_C_DDL_SQL = DDL_FILE.read_text(encoding="utf-8")

ROLLBACK_SQL = """
-- Drop Stage C Triggers
DROP TRIGGER IF EXISTS trg_validate_source_claim_review_metadata_update;
DROP TRIGGER IF EXISTS trg_validate_source_claim_review_metadata_insert;
DROP TRIGGER IF EXISTS trg_protect_source_claim_mutation;
DROP TRIGGER IF EXISTS trg_protect_source_record_mutation;
DROP TRIGGER IF EXISTS trg_protect_legacy_herb_map_mutation;
DROP TRIGGER IF EXISTS trg_protect_legacy_herb_map_delete;
DROP TRIGGER IF EXISTS trg_protect_herb_identity_mutation;
DROP TRIGGER IF EXISTS trg_protect_source_key_mutation;
DROP TRIGGER IF EXISTS trg_protect_sources_delete;
DROP TRIGGER IF EXISTS trg_cascade_claim_supersession;
DROP TRIGGER IF EXISTS trg_prevent_concept_cycle_update;
DROP TRIGGER IF EXISTS trg_validate_concept_parent_domain_insert;
DROP TRIGGER IF EXISTS trg_validate_concept_parent_domain_update;
DROP TRIGGER IF EXISTS trg_prevent_parent_domain_mutation_with_children;
DROP TRIGGER IF EXISTS trg_validate_label_verification_insert;
DROP TRIGGER IF EXISTS trg_protect_verified_label_identity_mutation;
DROP TRIGGER IF EXISTS trg_protect_verified_label_delete;
DROP TRIGGER IF EXISTS trg_validate_label_verification_update;
DROP TRIGGER IF EXISTS trg_protect_verified_label_citation_delete;
DROP TRIGGER IF EXISTS trg_protect_verified_label_citation_update;
DROP TRIGGER IF EXISTS trg_protect_claim_mapping_mutation;
DROP TRIGGER IF EXISTS trg_protect_dosha_assertion_mutation;
DROP TRIGGER IF EXISTS trg_validate_herb_prop_domain_insert;
DROP TRIGGER IF EXISTS trg_validate_herb_prop_domain_update;
DROP TRIGGER IF EXISTS trg_validate_herb_prop_mapping_insert;
DROP TRIGGER IF EXISTS trg_validate_herb_prop_mapping_update;
DROP TRIGGER IF EXISTS trg_validate_herb_parts_domain_insert;
DROP TRIGGER IF EXISTS trg_validate_herb_parts_domain_update;
DROP TRIGGER IF EXISTS trg_validate_herb_parts_mapping_insert;
DROP TRIGGER IF EXISTS trg_validate_herb_parts_mapping_update;
DROP TRIGGER IF EXISTS trg_validate_herb_prep_domains_insert;
DROP TRIGGER IF EXISTS trg_validate_herb_prep_domains_update;
DROP TRIGGER IF EXISTS trg_validate_herb_prep_cross_herb_insert;
DROP TRIGGER IF EXISTS trg_validate_herb_prep_cross_herb_update;
DROP TRIGGER IF EXISTS trg_validate_herb_indications_domain_insert;
DROP TRIGGER IF EXISTS trg_validate_herb_indications_domain_update;
DROP TRIGGER IF EXISTS trg_validate_herb_indications_mapping_insert;
DROP TRIGGER IF EXISTS trg_validate_herb_indications_mapping_update;
DROP TRIGGER IF EXISTS trg_validate_dosha_assertion_domains_insert;
DROP TRIGGER IF EXISTS trg_validate_dosha_assertion_domains_update;
DROP TRIGGER IF EXISTS trg_validate_herb_dosha_assertion_insert;
DROP TRIGGER IF EXISTS trg_validate_herb_dosha_assertion_update;
DROP TRIGGER IF EXISTS trg_protect_reconciliation_snapshot_integrity_update;
DROP TRIGGER IF EXISTS trg_protect_reconciliation_snapshot_integrity_insert;

-- Drop Stage C Views
DROP VIEW IF EXISTS v_active_herb_dosha_effects;
DROP VIEW IF EXISTS v_active_herb_dravyaguna_properties;

-- Drop Stage C Indexes
DROP INDEX IF EXISTS uq_herb_preparations_null_part;
DROP INDEX IF EXISTS uq_herb_dravyaguna_prop_null_part;

-- Drop Stage C Tables (reverse dependency order)
DROP TABLE IF EXISTS source_reconciliation_events;
DROP TABLE IF EXISTS herb_indications;
DROP TABLE IF EXISTS herb_preparations;
DROP TABLE IF EXISTS herb_plant_parts;
DROP TABLE IF EXISTS herb_dosha_effects;
DROP TABLE IF EXISTS herb_dravyaguna_properties;
DROP TABLE IF EXISTS dosha_claim_assertions;
DROP TABLE IF EXISTS concept_claim_mappings;
DROP TABLE IF EXISTS concept_label_sources;
DROP TABLE IF EXISTS concept_labels;
DROP TABLE IF EXISTS dravyaguna_concepts;
"""

def execute_statements(conn: sqlite3.Connection, script: str) -> None:
    """Executes a multi-statement SQL script with syntax and completion checking.
    
    Detects incomplete trailing statements and raises an error if found.
    """
    buffer = ""
    for line in script.splitlines():
        buffer += line + "\n"
        if sqlite3.complete_statement(buffer):
            stmt = buffer.strip()
            buffer = ""
            if stmt:
                conn.execute(stmt)
    if buffer.strip():
        raise RuntimeError(f"Incomplete trailing SQL statement in script: {buffer.strip()}")

def apply_migration(conn: sqlite3.Connection, applied_at: str | Path | None = None, ddl_path: Path | None = None) -> None:
    """Applies Migration 3 atomically.
    
    Verifies that the migration runner supplies an unreserved connection
    without an active transaction, acquires an immediate write transaction,
    enforces schema version 2 prerequisite inside the transaction,
    executes all Stage C DDL and trigger definitions, records version 3
    in schema_migrations, and commits atomically. In case of failure or
    version mismatch, the transaction is rolled back completely.
    """
    if isinstance(applied_at, Path):
        ddl_path = applied_at
        applied_at = None
    elif isinstance(applied_at, str) and ("/" in applied_at or "\\" in applied_at):
        ddl_path = Path(applied_at)
        applied_at = None

    if applied_at is None:
        applied_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    if conn.in_transaction:
        raise RuntimeError("Migration runner supplied connection with an active transaction; expected unreserved connection.")

    ddl_sql = STAGE_C_DDL_SQL
    if ddl_path is not None:
        ddl_sql = Path(ddl_path).read_text(encoding="utf-8")

    conn.execute("BEGIN IMMEDIATE;")
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        current_version = row[0] if row and row[0] is not None else 0
        if current_version != 2:
            raise RuntimeError(f"Cannot apply Migration 3: expected version 2, got {current_version}")

        execute_statements(conn, ddl_sql)
        cursor.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (MIGRATION_VERSION, MIGRATION_NAME, applied_at),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

def rollback_migration(conn: sqlite3.Connection) -> None:
    """Rolls back Migration 3 atomically.
    
    WARNING: Rolling back Migration 3 drops all Stage C tables (dravyaguna_concepts,
    concept_labels, concept_label_sources, concept_claim_mappings,
    dosha_claim_assertions, herb_dravyaguna_properties, herb_dosha_effects,
    herb_plant_parts, herb_preparations, herb_indications) and associated triggers.
    All normalized Stage C data will be permanently removed.
    Existing Stage B tables, claims, and relationships are fully preserved.
    
    Acquires an immediate write transaction, verifies that schema version is 3
    under the write lock, executes rollback SQL, removes the version 3 ledger
    entry, and commits atomically. In case of failure or version mismatch,
    the transaction is rolled back to restore the prior database state.
    """
    if conn.in_transaction:
        raise RuntimeError("Migration runner supplied connection with an active transaction; expected unreserved connection.")

    conn.execute("BEGIN IMMEDIATE;")
    try:
        cursor = conn.cursor()
        row = cursor.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        current_version = row[0] if row and row[0] is not None else 0
        if current_version != 3:
            raise RuntimeError(f"Cannot rollback Migration 3: expected version 3, got {current_version}")

        execute_statements(conn, ROLLBACK_SQL)
        cursor.execute("DELETE FROM schema_migrations WHERE version = ?", (MIGRATION_VERSION,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
