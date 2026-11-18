"""
Herbal Almanac — Stage C.2 Work Package 2 (WP-2)
Schema-Version Compatibility & Deterministic Migration Ledger Validation Gate

Enforces ADR Decision 7:
- Validates the complete migration ledger sequence [1, 2] or [1, 2, 3].
- Fails fast with FeatureUnavailableError when Stage C semantic operations
  are invoked on a Schema Version 2 database.
- Unlocks Stage C operations on Schema Version 3.
- Rejects malformed, gapped, duplicate, non-sequential, or future migration ledgers
  with MigrationError.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


# ============================================================================
# 1. WP-2 Exception Classes (ADR Decision 7)
# ============================================================================

class MigrationError(RuntimeError):
    """Raised when the database migration ledger is missing, corrupted, gapped, or unsupported."""
    pass


class FeatureUnavailableError(RuntimeError):
    """Raised when Stage C semantic features are invoked against a Schema Version 2 database."""
    pass


# ============================================================================
# 2. Migration Ledger Inspector
# ============================================================================

def validate_schema_migration_ledger(conn: sqlite3.Connection) -> int:
    """Validates the complete migration sequence recorded in schema_migrations.
    
    Rules per ADR Decision 7.A:
    1. Table schema_migrations must exist in sqlite_master.
    2. Queries: SELECT version FROM schema_migrations ORDER BY version ASC;
    3. Exactly [1, 2] -> returns 2 (Valid Schema Version 2 baseline).
    4. Exactly [1, 2, 3] -> returns 3 (Valid Schema Version 3 baseline).
    5. Any other sequence (e.g. [], [1], [1, 3], [2, 3], [1, 2, 2], [0, 1, 2], [1, 2, 3, 4]):
       Raises MigrationError with exact format:
       "Unsupported database schema migration ledger <versions>. Expected exact sequence [1, 2] or [1, 2, 3]."
       
    Returns:
        int: The validated schema version (2 or 3).
        
    Raises:
        MigrationError: If schema_migrations does not exist or ledger is invalid.
    """
    cur = conn.cursor()
    
    # Rule 1: Verify schema_migrations table exists
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations';"
    )
    if cur.fetchone() is None:
        raise MigrationError(
            "Database schema_migrations ledger table does not exist. "
            "Initialize database via create_database() first."
        )
    
    # Rule 2: Fetch all versions in insertion order (rowid ASC)
    cur.execute("SELECT version FROM schema_migrations ORDER BY rowid ASC;")
    rows = cur.fetchall()
    
    versions = [r[0] for r in rows]
    
    # Rule 3 & 4: Exact accepted ledgers
    if versions == [1, 2]:
        return 2
    if versions == [1, 2, 3]:
        return 3
    
    # Rule 5: Malformed, gapped, duplicate, or unsupported ledger
    raise MigrationError(
        f"Unsupported database schema migration ledger {versions}. "
        f"Expected exact sequence [1, 2] or [1, 2, 3]."
    )


# ============================================================================
# 3. Stage C Capability Gate
# ============================================================================

def require_stage_c_schema_v3(conn: sqlite3.Connection) -> None:
    """Guards Stage C semantic APIs, ensuring caller is operating on Schema Version 3.
    
    Rules per ADR Decision 7.A.2:
    - If database is at valid Schema Version 2 ([1, 2]), raises FeatureUnavailableError:
      "Stage C normalized semantic features require schema version 3 (current database version is 2). "
      "Apply Migration 3 to enable Dravyaguna semantic profiles."
    - If database is at valid Schema Version 3 ([1, 2, 3]), returns None.
    - If ledger is malformed or unsupported, validate_schema_migration_ledger raises MigrationError.
    
    Raises:
        FeatureUnavailableError: When database is at schema version 2.
        MigrationError: When schema_migrations ledger is malformed or missing.
    """
    version = validate_schema_migration_ledger(conn)
    if version == 2:
        raise FeatureUnavailableError(
            "Stage C normalized semantic features require schema version 3 (current database version is 2). "
            "Apply Migration 3 to enable Dravyaguna semantic profiles."
        )


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Convenience alias returning the validated schema version (2 or 3)."""
    return validate_schema_migration_ledger(conn)
