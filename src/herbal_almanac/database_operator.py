from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from difflib import SequenceMatcher
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Iterator
from threading import RLock

from .cleaning import DOSHAS, PlantRecord, ascii_text, clean_text, normalize_dosha_expression
from .schema_capability_gate import (
    validate_schema_migration_ledger,
    require_stage_c_schema_v3,
    get_schema_version,
)
from .migrations import migration_0003_semantic_dravyaguna
from .concept_catalog import seed_canonical_concept_catalog
from .backfill_engine import (
    capture_stage_b_table_snapshot,
    verify_stage_b_row_invariance,
    run_stage_c_semantic_backfill,
)


def search_key(value: str) -> str:
    return "".join(
        character
        for character in clean_text(value).casefold()
        if character.isalnum() or character.isspace()
    ).strip()


def canonical_illness_key(value: str) -> str:
    """Fold case/diacritics and Sanskrit visarga transliterations."""
    key = search_key(ascii_text(value))
    return re.sub(r"h$", "", key)


ILLNESS_ALIASES = {
    "fever": "jvara",
    "fevers": "jvara",
    "bawasir": "arsha",
}
MIN_SEARCH_SCORE = 0.65
MIGRATION_1_VERSION = 1
MIGRATION_1_NAME = "core_identity_and_provenance"
MIGRATION_2_VERSION = 2
MIGRATION_2_NAME = "normalized_botanical_taxonomy"
TAXON_RANKS = (
    "unknown", "family", "genus", "species", "subspecies", "variety", "form",
    "cultivar", "unranked",
)
VERNACULAR_LANGUAGE_CODES = {
    "English": "en",
    "Assamese": "as",
    "Bengali": "bn",
    "Bodo": "brx",
    "Dogri": "doi",
    "Gujarati": "gu",
    "Hindi": "hi",
    "Kannada": "kn",
    "Kashmiri": "ks",
    "Konkani": "kok",
    "Maithili": "mai",
    "Malayalam": "ml",
    "Manipuri": "mni",
    "Marathi": "mr",
    "Nepali": "ne",
    "Odia": "or",
    "Punjabi": "pa",
    "Sanskrit": "sa",
    "Santali": "sat",
    "Sindhi": "sd",
    "Tamil": "ta",
    "Telugu": "te",
    "Urdu": "ur",
}


def detect_script(text: str) -> str:
    """Return the ISO 15924 script code for text based on Unicode character ranges."""
    for char in text:
        cp = ord(char)
        if 0x0900 <= cp <= 0x097F:
            return "Deva"
        if 0x0980 <= cp <= 0x09FF:
            return "Beng"
        if 0x0A00 <= cp <= 0x0A7F:
            return "Guru"
        if 0x0A80 <= cp <= 0x0AFF:
            return "Gujr"
        if 0x0B00 <= cp <= 0x0B7F:
            return "Orya"
        if 0x0B80 <= cp <= 0x0BFF:
            return "Taml"
        if 0x0C00 <= cp <= 0x0C7F:
            return "Telu"
        if 0x0C80 <= cp <= 0x0CFF:
            return "Knda"
        if 0x0D00 <= cp <= 0x0D7F:
            return "Mlym"
        if ("a" <= char <= "z") or ("A" <= char <= "Z"):
            return "Latn"
    return "Zyyy"


class MigrationError(RuntimeError):
    """Raised when legacy data cannot be migrated without ambiguity."""


class ClaimAssociationError(ValueError):
    """Raised when a source claim cannot be attached to a herb safely."""


def default_database_path() -> Path:
    """Return the platform's per-user writable database location."""
    if os.name == "nt":
        data_home = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        data_home = Path.home() / "Library" / "Application Support"
    else:
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "herbal-almanac" / "AyurvedicDB.db"


class AyurvedicAlmanac:
    """SQLite persistence for cleaned DRAVYA plant records."""

    supported_languages = [
        "English", "Assamese", "Bengali", "Bodo", "Dogri", "Gujarati", "Hindi",
        "Kannada", "Kashmiri", "Konkani", "Maithili", "Malayalam",
        "Manipuri", "Marathi", "Nepali", "Odia", "Punjabi", "Sanskrit",
        "Santali", "Sindhi", "Tamil", "Telugu", "Urdu",
    ]

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path else default_database_path()
        self._initialized = False
        self._initialization_lock = RLock()

    def connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a transaction-scoped connection and always close it."""
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create_database(self) -> None:
        """Create the schema and apply versioned migrations safely.

        A re-entrant instance lock avoids duplicate work from threads sharing
        this object. SQLite's BEGIN IMMEDIATE plus busy_timeout serializes
        separate instances and processes using the same database file.
        """
        with self._initialization_lock:
            if self._initialized:
                return

            connection = self.connect()
            try:
                connection.execute("PRAGMA busy_timeout = 10000")
                connection.execute("BEGIN IMMEDIATE")
                schema_statements = """

                CREATE TABLE IF NOT EXISTS herbs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    english_name TEXT NOT NULL,
                    original_name TEXT,
                    retrieved_at TEXT,
                    search_key TEXT NOT NULL DEFAULT '',
                    source TEXT,
                    source_record_id INTEGER,
                    source_url TEXT,
                    botanical_name TEXT,
                    family TEXT,
                    UNIQUE(source, source_record_id)
                );

                CREATE TABLE IF NOT EXISTS illness (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    english_name TEXT NOT NULL UNIQUE,
                    search_key TEXT NOT NULL DEFAULT '',
                    canonical_key TEXT NOT NULL DEFAULT '',
                    machine_generated INTEGER NOT NULL DEFAULT 0,
                    verification_status TEXT NOT NULL DEFAULT 'unverified'
                );

                CREATE TABLE IF NOT EXISTS treatment (
                    herb_id INTEGER NOT NULL,
                    illness_id INTEGER NOT NULL,
                    source TEXT NOT NULL DEFAULT 'manual',
                    PRIMARY KEY (herb_id, illness_id),
                    FOREIGN KEY (herb_id) REFERENCES herbs(id) ON DELETE CASCADE,
                    FOREIGN KEY (illness_id) REFERENCES illness(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS herb_attributes (
                    herb_id INTEGER NOT NULL,
                    field_name TEXT NOT NULL,
                    value TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    source_language TEXT,
                    machine_generated INTEGER NOT NULL DEFAULT 0,
                    verification_status TEXT,
                    PRIMARY KEY (herb_id, field_name, value),
                    FOREIGN KEY (herb_id) REFERENCES herbs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS herb_doshas (
                    herb_id INTEGER NOT NULL,
                    dosha TEXT NOT NULL,
                    effect TEXT NOT NULL,
                    source_expression TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'scraped',
                    PRIMARY KEY (herb_id, dosha, source_expression, source),
                    CHECK (dosha IN ('Vata', 'Pitta', 'Kapha')),
                    CHECK (effect IN ('decrease', 'increase', 'unspecified')),
                    FOREIGN KEY (herb_id) REFERENCES herbs(id) ON DELETE CASCADE
                );


                """
                # executescript() implicitly commits a pending transaction.
                # Execute this static DDL one statement at a time so the
                # BEGIN IMMEDIATE reservation remains active during setup.
                for statement in schema_statements.split(";"):
                    if statement.strip():
                        connection.execute(statement)
                self._validate_legacy_source_identity(connection)
                self._migrate_legacy_herbs(connection)
                self._migrate_legacy_attributes(connection)
                self._migrate_legacy_treatments(connection)
                self._migrate_legacy_illnesses(connection)
                self._migrate_search_columns(connection)
                self._migrate_illness_canonical_keys(connection)
                connection.commit()

                # Inspect migration state only after acquiring the writer lock.
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        applied_at TEXT NOT NULL
                    )
                    """
                )
                applied_versions = {
                    row["version"]
                    for row in connection.execute("SELECT version FROM schema_migrations")
                }
                if MIGRATION_2_VERSION in applied_versions and MIGRATION_1_VERSION not in applied_versions:
                    raise MigrationError(
                        "Migration 2 is recorded without Migration 1; "
                        "restore the database backup before retrying."
                    )

                migrations = (
                    (MIGRATION_1_VERSION, MIGRATION_1_NAME, self._migration_1_core_identity_and_provenance),
                    (MIGRATION_2_VERSION, MIGRATION_2_NAME, self._migration_2_normalized_botanical_taxonomy),
                )
                for version, name, migration in migrations:
                    if version in applied_versions:
                        continue
                    migration(connection)
                    connection.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (version, name, datetime.now(timezone.utc).isoformat()),
                    )
                    applied_versions.add(version)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

            self._initialized = True

    @classmethod
    def _validate_legacy_source_identity(cls, connection: sqlite3.Connection) -> None:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(herbs)")
        }
        if not {"source", "source_record_id"} <= columns:
            return
        identities: dict[tuple[str, str], list[int]] = {}
        for row in connection.execute(
            """
            SELECT id, source, source_record_id
            FROM herbs
            WHERE source_record_id IS NOT NULL
            ORDER BY id
            """
        ):
            identity = (
                cls._legacy_source_key(row["source"]),
                str(row["source_record_id"]),
            )
            identities.setdefault(identity, []).append(row["id"])
        duplicates = {
            identity: herb_ids
            for identity, herb_ids in identities.items()
            if len(herb_ids) > 1
        }
        if duplicates:
            details = "; ".join(
                f"source={source!r}, source_record_id={record_id!r}, "
                f"legacy_herb_ids={herb_ids}"
                for (source, record_id), herb_ids in sorted(duplicates.items())
            )
            raise MigrationError(
                "Migration 1 cannot map duplicate legacy source identities: "
                + details
                + ". Resolve the duplicate herb rows before retrying."
            )

    @staticmethod
    def _create_migration_1_tables(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sources (
                source_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_key TEXT NOT NULL UNIQUE,
                publisher TEXT,
                title TEXT,
                edition_or_version TEXT,
                publication_date TEXT,
                default_url TEXT,
                license TEXT,
                attribution_text TEXT,
                notes TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS source_records (
                source_record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                external_record_key TEXT,
                source_url TEXT,
                retrieved_at TEXT,
                published_at TEXT,
                content_hash TEXT,
                raw_artifact_ref TEXT,
                FOREIGN KEY (source_id) REFERENCES sources(source_id)
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_source_records_external_key
            ON source_records(source_id, external_record_key)
            WHERE external_record_key IS NOT NULL
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_source_records_source_id "
            "ON source_records(source_id)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS source_claims (
                source_claim_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_record_id INTEGER NOT NULL,
                claim_type TEXT NOT NULL,
                source_field TEXT NOT NULL,
                source_expression TEXT NOT NULL,
                language_code TEXT NOT NULL DEFAULT 'und',
                retrieved_at TEXT,
                verification_status TEXT NOT NULL DEFAULT 'unreviewed',
                created_by_type TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                reviewed_by TEXT,
                reviewed_at TEXT,
                reviewer_notes TEXT,
                normalization_method TEXT,
                supersedes_claim_id INTEGER,
                FOREIGN KEY (source_record_id) REFERENCES source_records(source_record_id),
                FOREIGN KEY (supersedes_claim_id) REFERENCES source_claims(source_claim_id)
                    ON DELETE SET NULL,
                CHECK (created_by_type IN ('ingest', 'human', 'system')),
                CHECK (verification_status IN (
                    'unreviewed', 'reviewed', 'verified', 'rejected', 'superseded'
                ))
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_source_claims_record_type
            ON source_claims(source_record_id, claim_type, source_field)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_source_claims_supersedes
            ON source_claims(supersedes_claim_id)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS legacy_herb_map (
                legacy_herb_id INTEGER PRIMARY KEY,
                herb_id INTEGER NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY (legacy_herb_id) REFERENCES herbs(id),
                FOREIGN KEY (herb_id) REFERENCES herbs(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS herb_names (
                herb_name_id INTEGER PRIMARY KEY AUTOINCREMENT,
                herb_id INTEGER NOT NULL,
                name_text TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                language_code TEXT NOT NULL DEFAULT 'und',
                script_code TEXT NOT NULL DEFAULT 'Zyyy',
                name_type TEXT NOT NULL,
                is_preferred INTEGER NOT NULL DEFAULT 0,
                source_claim_id INTEGER NOT NULL,
                FOREIGN KEY (herb_id) REFERENCES herbs(id),
                FOREIGN KEY (source_claim_id) REFERENCES source_claims(source_claim_id),
                CHECK (is_preferred IN (0, 1)),
                CHECK (name_type IN (
                    'ayurvedic', 'vernacular', 'botanical_source',
                    'accepted_botanical', 'botanical_synonym', 'historical',
                    'trade', 'source_alias'
                ))
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_herb_names_association
            ON herb_names(
                herb_id, name_text, normalized_text, language_code,
                script_code, name_type, source_claim_id
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_herb_names_preferred
            ON herb_names(herb_id, name_type)
            WHERE is_preferred = 1
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_herb_names_normalized "
            "ON herb_names(normalized_text, language_code)"
        )

    @staticmethod
    def _legacy_source_key(source: str | None) -> str:
        cleaned = clean_text(source) if source else ""
        return cleaned or "manual"

    @classmethod
    def _backfill_migration_1(cls, connection: sqlite3.Connection) -> None:
        now = datetime.now(timezone.utc).isoformat()
        source_keys = {
            cls._legacy_source_key(row["source"])
            for row in connection.execute("SELECT DISTINCT source FROM herbs")
        }
        source_keys.add("manual")
        for source_key in sorted(source_keys):
            connection.execute(
                """
                INSERT OR IGNORE INTO sources
                    (source_key, publisher, notes)
                VALUES (?, ?, ?)
                """,
                (
                    source_key,
                    None if source_key == "manual" else source_key,
                    "Legacy source identifier; publication metadata unavailable.",
                ),
            )

        source_ids = {
            row["source_key"]: row["source_id"]
            for row in connection.execute("SELECT source_key, source_id FROM sources")
        }
        for row in connection.execute(
            """
            SELECT id, source, source_record_id, source_url, retrieved_at,
                   original_name, english_name
            FROM herbs
            ORDER BY id
            """
        ):
            legacy_herb_id = row["id"]
            source_key = cls._legacy_source_key(row["source"])
            source_id = source_ids[source_key]
            external_key = (
                str(row["source_record_id"])
                if row["source_record_id"] is not None
                else None
            )
            raw_artifact_ref = (
                f"legacy_herb_id:{legacy_herb_id}"
                if external_key is None or source_key == "manual"
                else None
            )
            source_record_cursor = connection.execute(
                """
                INSERT INTO source_records
                    (source_id, external_record_key, source_url, retrieved_at,
                     raw_artifact_ref)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    external_key,
                    row["source_url"],
                    row["retrieved_at"],
                    raw_artifact_ref,
                ),
            )
            source_record_id = source_record_cursor.lastrowid
            connection.execute(
                """
                INSERT INTO legacy_herb_map (legacy_herb_id, herb_id, created_at)
                VALUES (?, ?, ?)
                """,
                (legacy_herb_id, legacy_herb_id, now),
            )
            name_text = row["original_name"] or row["english_name"]
            if not name_text:
                continue
            claim_cursor = connection.execute(
                """
                INSERT INTO source_claims
                    (source_record_id, claim_type, source_field, source_expression,
                     language_code, retrieved_at, verification_status,
                     created_by_type, created_by, created_at, updated_at)
                VALUES (?, 'herb_name', ?, ?, 'und', ?, 'unreviewed',
                        'system', 'migration:1', ?, ?)
                """,
                (
                    source_record_id,
                    "legacy.herbs.original_name"
                    if row["original_name"]
                    else "legacy.herbs.english_name",
                    name_text,
                    row["retrieved_at"],
                    now,
                    now,
                ),
            )
            cls._insert_herb_name(
                connection,
                legacy_herb_id,
                name_text,
                search_key(ascii_text(name_text) or name_text),
                "und",
                "Zyyy",
                "source_alias",
                True,
                claim_cursor.lastrowid,
            )

    @classmethod
    def _resolve_legacy_source_record_id(
        cls, connection: sqlite3.Connection, herb_id: int
    ) -> int:
        herb = connection.execute(
            """
            SELECT h.id, h.source, h.source_record_id
            FROM legacy_herb_map AS m
            JOIN herbs AS h ON h.id = m.legacy_herb_id
            WHERE m.herb_id = ?
            """,
            (herb_id,),
        ).fetchone()
        if herb is None:
            raise ClaimAssociationError(
                f"Herb {herb_id} has no legacy source mapping; "
                "a claim cannot be associated safely."
            )
        source_key = cls._legacy_source_key(herb["source"])
        if herb["source_record_id"] is None:
            artifact_ref = f"legacy_herb_id:{herb['id']}"
            rows = connection.execute(
                """
                SELECT sr.source_record_id
                FROM source_records AS sr
                JOIN sources AS s ON s.source_id = sr.source_id
                WHERE s.source_key = ? AND sr.raw_artifact_ref = ?
                """,
                (source_key, artifact_ref),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT sr.source_record_id
                FROM source_records AS sr
                JOIN sources AS s ON s.source_id = sr.source_id
                WHERE s.source_key = ? AND sr.external_record_key = ?
                """,
                (source_key, str(herb["source_record_id"])),
            ).fetchall()
        if len(rows) != 1:
            raise ClaimAssociationError(
                f"Herb {herb_id} maps to {len(rows)} source records for "
                f"source={source_key!r}; expected exactly one."
            )
        return rows[0]["source_record_id"]

    @classmethod
    def _validate_herb_claim(
        cls, connection: sqlite3.Connection, herb_id: int, source_claim_id: int
    ) -> None:
        claim = connection.execute(
            """
            SELECT sc.source_record_id, s.source_key, sr.raw_artifact_ref
            FROM source_claims AS sc
            JOIN source_records AS sr ON sr.source_record_id = sc.source_record_id
            JOIN sources AS s ON s.source_id = sr.source_id
            WHERE sc.source_claim_id = ?
            """,
            (source_claim_id,),
        ).fetchone()
        if claim is None:
            raise ClaimAssociationError(
                f"Source claim {source_claim_id} does not exist or is unresolved."
            )
        expected_source_record_id = cls._resolve_legacy_source_record_id(
            connection, herb_id
        )
        if claim["source_key"] == "manual":
            expected_artifact_ref = f"legacy_herb_id:{herb_id}"
            if claim["raw_artifact_ref"] != expected_artifact_ref:
                raise ClaimAssociationError(
                    f"Manual claim {source_claim_id} is not explicitly bound to "
                    f"herb {herb_id}; expected raw_artifact_ref="
                    f"{expected_artifact_ref!r}."
                )
            return
        if claim["source_record_id"] != expected_source_record_id:
            raise ClaimAssociationError(
                f"Source claim {source_claim_id} belongs to source record "
                f"{claim['source_record_id']}, not herb {herb_id}'s source record "
                f"{expected_source_record_id}."
            )

    @classmethod
    def _insert_herb_name(
        cls,
        connection: sqlite3.Connection,
        herb_id: int,
        name_text: str,
        normalized_text: str,
        language_code: str,
        script_code: str,
        name_type: str,
        is_preferred: bool,
        source_claim_id: int,
    ) -> int:
        cls._validate_herb_claim(connection, herb_id, source_claim_id)
        existing = connection.execute(
            """
            SELECT herb_name_id FROM herb_names
            WHERE herb_id = ? AND name_text = ? AND normalized_text = ?
                  AND language_code = ? AND script_code = ? AND name_type = ?
                  AND source_claim_id = ?
            """,
            (
                herb_id,
                name_text,
                normalized_text,
                language_code,
                script_code,
                name_type,
                source_claim_id,
            ),
        ).fetchone()
        if existing:
            return existing["herb_name_id"]

        if is_preferred:
            existing_preferred = connection.execute(
                """
                SELECT herb_name_id, name_text FROM herb_names
                WHERE herb_id = ? AND name_type = ? AND is_preferred = 1
                """,
                (herb_id, name_type),
            ).fetchone()
            if existing_preferred and existing_preferred["name_text"] != name_text:
                connection.execute(
                    "UPDATE herb_names SET is_preferred = 0 WHERE herb_name_id = ?",
                    (existing_preferred["herb_name_id"],),
                )

        cursor = connection.execute(
            """
            INSERT INTO herb_names
                (herb_id, name_text, normalized_text, language_code,
                 script_code, name_type, is_preferred, source_claim_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                herb_id,
                name_text,
                normalized_text,
                language_code,
                script_code,
                name_type,
                int(is_preferred),
                source_claim_id,
            ),
        )
        return cursor.lastrowid

    @classmethod
    def _ensure_source(cls, connection: sqlite3.Connection, source_name: str | None) -> int:
        source_key = cls._legacy_source_key(source_name)
        connection.execute(
            """
            INSERT OR IGNORE INTO sources
                (source_key, publisher, title, default_url, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                source_key,
                "CCRAS" if source_key == "CCRAS DRAVYA" else (None if source_key == "manual" else source_key),
                "CCRAS DRAVYA Portal" if source_key == "CCRAS DRAVYA" else source_key,
                "https://dravya.ccras.org.in" if source_key == "CCRAS DRAVYA" else None,
                "CCRAS DRAVYA plant directory and monographs."
                if source_key == "CCRAS DRAVYA"
                else "Source registered during data ingestion.",
            ),
        )
        row = connection.execute(
            "SELECT source_id FROM sources WHERE source_key = ?",
            (source_key,),
        ).fetchone()
        return row["source_id"]

    @classmethod
    def _ensure_source_record(
        cls,
        connection: sqlite3.Connection,
        source_id: int,
        external_record_key: str | None,
        source_url: str | None,
        retrieved_at: str | None,
        raw_artifact_ref: str | None = None,
    ) -> int:
        if external_record_key is not None:
            existing = connection.execute(
                """
                SELECT source_record_id FROM source_records
                WHERE source_id = ? AND external_record_key = ?
                """,
                (source_id, external_record_key),
            ).fetchone()
            if existing:
                connection.execute(
                    """
                    UPDATE source_records
                    SET source_url = COALESCE(?, source_url),
                        retrieved_at = COALESCE(?, retrieved_at)
                    WHERE source_record_id = ?
                    """,
                    (source_url, retrieved_at, existing["source_record_id"]),
                )
                return existing["source_record_id"]
            cursor = connection.execute(
                """
                INSERT INTO source_records
                    (source_id, external_record_key, source_url, retrieved_at, raw_artifact_ref)
                VALUES (?, ?, ?, ?, ?)
                """,
                (source_id, external_record_key, source_url, retrieved_at, raw_artifact_ref),
            )
            return cursor.lastrowid
        else:
            if raw_artifact_ref is not None:
                existing = connection.execute(
                    """
                    SELECT source_record_id FROM source_records
                    WHERE source_id = ? AND raw_artifact_ref = ?
                    """,
                    (source_id, raw_artifact_ref),
                ).fetchone()
                if existing:
                    return existing["source_record_id"]
            cursor = connection.execute(
                """
                INSERT INTO source_records
                    (source_id, external_record_key, source_url, retrieved_at, raw_artifact_ref)
                VALUES (?, ?, ?, ?, ?)
                """,
                (source_id, None, source_url, retrieved_at, raw_artifact_ref),
            )
            return cursor.lastrowid

    @staticmethod
    def _ensure_legacy_herb_map(connection: sqlite3.Connection, herb_id: int, now: str) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO legacy_herb_map (legacy_herb_id, herb_id, created_at)
            VALUES (?, ?, ?)
            """,
            (herb_id, herb_id, now),
        )

    @classmethod
    def _record_claim(
        cls,
        connection: sqlite3.Connection,
        source_record_id: int,
        claim_type: str,
        source_field: str,
        source_expression: str,
        language_code: str = "und",
        retrieved_at: str | None = None,
        created_by_type: str = "ingest",
        created_by: str = "scraper:dravya",
        verification_status: str = "unreviewed",
        now: str | None = None,
        is_single_value_field: bool = False,
    ) -> int:
        now = now or datetime.now(timezone.utc).isoformat()
        if created_by_type == "user":
            created_by_type = "human"
        existing = connection.execute(
            """
            SELECT source_claim_id
            FROM source_claims
            WHERE source_record_id = ? AND claim_type = ? AND source_field = ?
                  AND source_expression = ? AND verification_status != 'superseded'
            """,
            (source_record_id, claim_type, source_field, source_expression),
        ).fetchone()
        if existing:
            return existing["source_claim_id"]

        supersedes_claim_id = None
        if is_single_value_field:
            old_claim = connection.execute(
                """
                SELECT source_claim_id
                FROM source_claims
                WHERE source_record_id = ? AND claim_type = ? AND source_field = ?
                      AND verification_status != 'superseded'
                ORDER BY source_claim_id DESC
                LIMIT 1
                """,
                (source_record_id, claim_type, source_field),
            ).fetchone()
            if old_claim:
                supersedes_claim_id = old_claim["source_claim_id"]
                connection.execute(
                    """
                    UPDATE source_claims
                    SET verification_status = 'superseded', updated_at = ?
                    WHERE source_claim_id = ?
                    """,
                    (now, supersedes_claim_id),
                )

        cursor = connection.execute(
            """
            INSERT INTO source_claims
                (source_record_id, claim_type, source_field, source_expression,
                 language_code, retrieved_at, verification_status, created_by_type,
                 created_by, created_at, updated_at, supersedes_claim_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_record_id,
                claim_type,
                source_field,
                source_expression,
                language_code,
                retrieved_at,
                verification_status,
                created_by_type,
                created_by,
                now,
                now,
                supersedes_claim_id,
            ),
        )
        return cursor.lastrowid

    @classmethod
    def _sync_herb_names(
        cls,
        connection: sqlite3.Connection,
        herb_id: int,
        source_record_id: int,
        record: PlantRecord,
        now: str,
    ) -> None:
        ayurvedic_name = clean_text(record.ayurvedic_name)
        if ayurvedic_name:
            claim_id = cls._record_claim(
                connection,
                source_record_id=source_record_id,
                claim_type="herb_name",
                source_field="heading.ayurvedic_name",
                source_expression=ayurvedic_name,
                language_code="sa",
                retrieved_at=record.retrieved_at,
                now=now,
                is_single_value_field=True,
            )
            cls._validate_herb_claim(connection, herb_id, claim_id)
            norm_text = search_key(ascii_text(ayurvedic_name) or ayurvedic_name)
            script_code = detect_script(ayurvedic_name)
            cls._insert_herb_name(
                connection,
                herb_id=herb_id,
                name_text=ayurvedic_name,
                normalized_text=norm_text,
                language_code="sa",
                script_code=script_code,
                name_type="ayurvedic",
                is_preferred=True,
                source_claim_id=claim_id,
            )

        translit_name = clean_text(record.transliterated_name)
        if translit_name and translit_name != ayurvedic_name:
            claim_id = cls._record_claim(
                connection,
                source_record_id=source_record_id,
                claim_type="herb_name",
                source_field="transliterated_name",
                source_expression=translit_name,
                language_code="en",
                retrieved_at=record.retrieved_at,
                now=now,
                is_single_value_field=True,
            )
            cls._validate_herb_claim(connection, herb_id, claim_id)
            norm_translit = search_key(translit_name)
            cls._insert_herb_name(
                connection,
                herb_id=herb_id,
                name_text=translit_name,
                normalized_text=norm_translit,
                language_code="en",
                script_code="Latn",
                name_type="source_alias",
                is_preferred=False,
                source_claim_id=claim_id,
            )

        for field, values in record.attributes.items():
            if not field.startswith("Vernacular Names."):
                continue
            lang_name = field.split(".", 1)[1]
            lang_code = VERNACULAR_LANGUAGE_CODES.get(lang_name, "und")
            for val in values:
                cleaned_val = clean_text(val)
                if not cleaned_val:
                    continue
                claim_id = cls._record_claim(
                    connection,
                    source_record_id=source_record_id,
                    claim_type="herb_name",
                    source_field=field,
                    source_expression=cleaned_val,
                    language_code=lang_code,
                    retrieved_at=record.retrieved_at,
                    now=now,
                )
                cls._validate_herb_claim(connection, herb_id, claim_id)
                norm_val = search_key(ascii_text(cleaned_val) or cleaned_val)
                script = detect_script(cleaned_val)
                cls._insert_herb_name(
                    connection,
                    herb_id=herb_id,
                    name_text=cleaned_val,
                    normalized_text=norm_val,
                    language_code=lang_code,
                    script_code=script,
                    name_type="vernacular",
                    is_preferred=False,
                    source_claim_id=claim_id,
                )

        # Retained for backward compatibility with legacy databases containing Translated Names.* attributes
        for field, values in record.attributes.items():
            if not field.startswith("Translated Names."):
                continue
            lang_name = field.split(".", 1)[1]
            lang_code = VERNACULAR_LANGUAGE_CODES.get(lang_name, "und")
            for val in values:
                cleaned_val = clean_text(val)
                if not cleaned_val:
                    continue
                claim_id = cls._record_claim(
                    connection,
                    source_record_id=source_record_id,
                    claim_type="herb_name",
                    source_field=field,
                    source_expression=cleaned_val,
                    language_code=lang_code,
                    retrieved_at=record.retrieved_at,
                    created_by_type="system",
                    created_by="translation:google",
                    verification_status="unreviewed",
                    now=now,
                )
                cls._validate_herb_claim(connection, herb_id, claim_id)
                norm_val = search_key(ascii_text(cleaned_val) or cleaned_val)
                script = detect_script(cleaned_val)
                cls._insert_herb_name(
                    connection,
                    herb_id=herb_id,
                    name_text=cleaned_val,
                    normalized_text=norm_val,
                    language_code=lang_code,
                    script_code=script,
                    name_type="source_alias",
                    is_preferred=False,
                    source_claim_id=claim_id,
                )

    @classmethod
    def _sync_herb_taxa(
        cls,
        connection: sqlite3.Connection,
        herb_id: int,
        source_record_id: int,
        record: PlantRecord,
        now: str,
    ) -> None:
        if record.botanical_name:
            botanical = clean_text(record.botanical_name)
            if botanical:
                claim_id = cls._record_claim(
                    connection,
                    source_record_id=source_record_id,
                    claim_type="taxonomy_name",
                    source_field="scientific_profile.botanical_name",
                    source_expression=botanical,
                    language_code="la",
                    retrieved_at=record.retrieved_at,
                    now=now,
                    is_single_value_field=True,
                )
                cls._validate_herb_claim(connection, herb_id, claim_id)
                norm_name = search_key(ascii_text(botanical) or botanical)
                taxon = connection.execute(
                    "SELECT taxon_id FROM taxa WHERE scientific_name = ? AND rank = 'unknown'",
                    (botanical,),
                ).fetchone()
                if taxon:
                    taxon_id = taxon["taxon_id"]
                else:
                    taxon_id = connection.execute(
                        """
                        INSERT INTO taxa (scientific_name, normalized_name, rank, created_at)
                        VALUES (?, ?, 'unknown', ?)
                        """,
                        (botanical, norm_name, now),
                    ).lastrowid
                existing_ht = connection.execute(
                    """
                    SELECT herb_taxon_id FROM herb_taxa
                    WHERE herb_id = ? AND taxon_id = ? AND relationship_type = 'source_identification'
                          AND source_claim_id = ?
                    """,
                    (herb_id, taxon_id, claim_id),
                ).fetchone()
                if not existing_ht:
                    connection.execute(
                        """
                        INSERT INTO herb_taxa
                            (herb_id, taxon_id, relationship_type, source_claim_id, is_preferred, created_at)
                        VALUES (?, ?, 'source_identification', ?, 0, ?)
                        """,
                        (herb_id, taxon_id, claim_id, now),
                    )

        if record.family:
            family = clean_text(record.family)
            if family:
                claim_id = cls._record_claim(
                    connection,
                    source_record_id=source_record_id,
                    claim_type="taxonomy_name",
                    source_field="scientific_profile.family",
                    source_expression=family,
                    language_code="la",
                    retrieved_at=record.retrieved_at,
                    now=now,
                    is_single_value_field=True,
                )
                cls._validate_herb_claim(connection, herb_id, claim_id)
                norm_fam = search_key(ascii_text(family) or family)
                taxon = connection.execute(
                    "SELECT taxon_id FROM taxa WHERE scientific_name = ? AND rank = 'family'",
                    (family,),
                ).fetchone()
                if taxon:
                    taxon_id = taxon["taxon_id"]
                else:
                    taxon_id = connection.execute(
                        """
                        INSERT INTO taxa (scientific_name, normalized_name, rank, created_at)
                        VALUES (?, ?, 'family', ?)
                        """,
                        (family, norm_fam, now),
                    ).lastrowid
                existing_ht = connection.execute(
                    """
                    SELECT herb_taxon_id FROM herb_taxa
                    WHERE herb_id = ? AND taxon_id = ? AND relationship_type = 'source_identification'
                          AND source_claim_id = ?
                    """,
                    (herb_id, taxon_id, claim_id),
                ).fetchone()
                if not existing_ht:
                    connection.execute(
                        """
                        INSERT INTO herb_taxa
                            (herb_id, taxon_id, relationship_type, source_claim_id, is_preferred, created_at)
                        VALUES (?, ?, 'source_identification', ?, 0, ?)
                        """,
                        (herb_id, taxon_id, claim_id, now),
                    )

    @classmethod
    def _sync_attribute_claims(
        cls,
        connection: sqlite3.Connection,
        herb_id: int,
        source_record_id: int,
        record: PlantRecord,
        now: str,
    ) -> None:
        for field, values in record.attributes.items():
            if field.startswith(("Vernacular Names.", "Translated Names.")):
                continue
            meta = record.attribute_metadata.get(field, {})
            lang = meta.get("source_language") or "und"
            ver_status = meta.get("verification_status") or "unreviewed"
            created_by_type = "system" if meta.get("machine_generated") else "ingest"
            for val in values:
                cleaned_val = clean_text(val)
                if not cleaned_val:
                    continue
                cls._record_claim(
                    connection,
                    source_record_id=source_record_id,
                    claim_type="attribute",
                    source_field=field,
                    source_expression=cleaned_val,
                    language_code=lang,
                    retrieved_at=record.retrieved_at,
                    created_by_type=created_by_type,
                    created_by="scraper:dravya",
                    verification_status=ver_status,
                    now=now,
                )
        for expr in record.dosha_expressions:
            cleaned_expr = clean_text(expr)
            if cleaned_expr:
                cls._record_claim(
                    connection,
                    source_record_id=source_record_id,
                    claim_type="dosha_expression",
                    source_field="Doshakarma",
                    source_expression=cleaned_expr,
                    language_code="sa",
                    retrieved_at=record.retrieved_at,
                    created_by_type="ingest",
                    created_by="scraper:dravya",
                    verification_status="unreviewed",
                    now=now,
                )

    @classmethod
    def _migration_1_core_identity_and_provenance(
        cls, connection: sqlite3.Connection
    ) -> None:
        cls._create_migration_1_tables(connection)
        cls._backfill_migration_1(connection)

    @staticmethod
    def _create_migration_2_tables(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS taxa (
                taxon_id INTEGER PRIMARY KEY AUTOINCREMENT,
                scientific_name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                rank TEXT NOT NULL,
                authorship TEXT,
                created_at TEXT NOT NULL,
                CHECK (rank IN (
                    'unknown', 'family', 'genus', 'species', 'subspecies',
                    'variety', 'form', 'cultivar', 'unranked'
                ))
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_taxa_normalized_name "
            "ON taxa(normalized_name, rank)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS taxon_relationships (
                relationship_id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_taxon_id INTEGER NOT NULL,
                child_taxon_id INTEGER NOT NULL,
                relationship_type TEXT NOT NULL,
                source_claim_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (parent_taxon_id) REFERENCES taxa(taxon_id),
                FOREIGN KEY (child_taxon_id) REFERENCES taxa(taxon_id),
                FOREIGN KEY (source_claim_id) REFERENCES source_claims(source_claim_id),
                CHECK (parent_taxon_id <> child_taxon_id),
                CHECK (relationship_type IN ('parent_child', 'accepted_synonym'))
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_taxon_relationships_unique
            ON taxon_relationships(
                parent_taxon_id, child_taxon_id, relationship_type, source_claim_id
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_taxon_relationships_child
            ON taxon_relationships(child_taxon_id, relationship_type)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS herb_taxa (
                herb_taxon_id INTEGER PRIMARY KEY AUTOINCREMENT,
                herb_id INTEGER NOT NULL,
                taxon_id INTEGER NOT NULL,
                relationship_type TEXT NOT NULL,
                source_claim_id INTEGER NOT NULL,
                is_preferred INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (herb_id) REFERENCES herbs(id),
                FOREIGN KEY (taxon_id) REFERENCES taxa(taxon_id),
                FOREIGN KEY (source_claim_id) REFERENCES source_claims(source_claim_id),
                CHECK (is_preferred IN (0, 1)),
                CHECK (relationship_type IN (
                    'accepted', 'source_identification', 'synonym'
                ))
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_herb_taxa_unique
            ON herb_taxa(herb_id, taxon_id, relationship_type, source_claim_id)
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_herb_taxa_preferred
            ON herb_taxa(herb_id)
            WHERE relationship_type = 'accepted' AND is_preferred = 1
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_herb_taxa_taxon "
            "ON herb_taxa(taxon_id, relationship_type)"
        )

    @classmethod
    def _insert_legacy_taxon_claim(
        cls,
        connection: sqlite3.Connection,
        herb_id: int,
        expression: str,
        source_field: str,
        rank: str,
        created_at: str,
    ) -> None:
        source_record_id = cls._resolve_legacy_source_record_id(connection, herb_id)
        claim_id = connection.execute(
            """
            INSERT INTO source_claims
                (source_record_id, claim_type, source_field, source_expression,
                 language_code, verification_status, created_by_type, created_by,
                 created_at, updated_at)
            VALUES (?, 'taxonomy_name', ?, ?, 'und', 'unreviewed',
                    'system', 'migration:2', ?, ?)
            """,
            (source_record_id, source_field, expression, created_at, created_at),
        ).lastrowid
        taxon_id = connection.execute(
            """
            INSERT INTO taxa
                (scientific_name, normalized_name, rank, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (expression, search_key(ascii_text(expression) or expression), rank, created_at),
        ).lastrowid
        cls._validate_herb_claim(connection, herb_id, claim_id)
        connection.execute(
            """
            INSERT INTO herb_taxa
                (herb_id, taxon_id, relationship_type, source_claim_id,
                 is_preferred, created_at)
            VALUES (?, ?, 'source_identification', ?, 0, ?)
            """,
            (herb_id, taxon_id, claim_id, created_at),
        )

    @classmethod
    def _backfill_migration_2(cls, connection: sqlite3.Connection) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for row in connection.execute(
            "SELECT id, botanical_name, family FROM herbs ORDER BY id"
        ):
            if row["botanical_name"]:
                cls._insert_legacy_taxon_claim(
                    connection,
                    row["id"],
                    row["botanical_name"],
                    "legacy.herbs.botanical_name",
                    "unknown",
                    now,
                )
            if row["family"]:
                cls._insert_legacy_taxon_claim(
                    connection,
                    row["id"],
                    row["family"],
                    "legacy.herbs.family",
                    "family",
                    now,
                )

    @classmethod
    def _migration_2_normalized_botanical_taxonomy(
        cls, connection: sqlite3.Connection
    ) -> None:
        cls._create_migration_2_tables(connection)
        cls._backfill_migration_2(connection)

    @staticmethod
    def _migrate_legacy_herbs(connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(herbs)")
        }
        for name, definition in (
            ("source", "TEXT"),
            ("source_record_id", "INTEGER"),
            ("source_url", "TEXT"),
            ("botanical_name", "TEXT"),
            ("family", "TEXT"),
            ("original_name", "TEXT"),
            ("retrieved_at", "TEXT"),
            ("search_key", "TEXT NOT NULL DEFAULT ''"),
        ):
            if name not in columns:
                connection.execute(f"ALTER TABLE herbs ADD COLUMN {name} {definition}")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_herbs_source_record "
            "ON herbs(source, source_record_id)"
        )

    @staticmethod
    def _migrate_legacy_attributes(connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(herb_attributes)")
        }
        for name, definition in (
            ("source_language", "TEXT"),
            ("machine_generated", "INTEGER NOT NULL DEFAULT 0"),
            ("verification_status", "TEXT"),
        ):
            if name not in columns:
                connection.execute(
                    f"ALTER TABLE herb_attributes ADD COLUMN {name} {definition}"
                )

    @staticmethod
    def _migrate_legacy_treatments(connection: sqlite3.Connection) -> None:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(treatment)")
        }
        if "source" not in columns:
            connection.execute(
                "ALTER TABLE treatment ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'"
            )

    @staticmethod
    def _migrate_search_columns(connection: sqlite3.Connection) -> None:
        for table in ("herbs", "illness"):
            columns = {
                row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
            }
            if "search_key" not in columns:
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN search_key TEXT NOT NULL DEFAULT ''"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_herbs_search_key ON herbs(search_key)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_illness_search_key ON illness(search_key)"
        )
        for table in ("herbs", "illness"):
            rows = connection.execute(
                f"SELECT id, english_name FROM {table}"
            ).fetchall()
            for row in rows:
                connection.execute(
                    f"UPDATE {table} SET search_key = ? WHERE id = ?",
                    (search_key(row["english_name"]), row["id"]),
                )
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(illness)")
        }
        for name, definition in (
            ("machine_generated", "INTEGER NOT NULL DEFAULT 0"),
            ("verification_status", "TEXT NOT NULL DEFAULT 'unverified'"),
        ):
            if name not in columns:
                connection.execute(f"ALTER TABLE illness ADD COLUMN {name} {definition}")

    @staticmethod
    def _migrate_illness_canonical_keys(connection: sqlite3.Connection) -> None:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(illness)")
        }
        if "canonical_key" not in columns:
            connection.execute(
                "ALTER TABLE illness ADD COLUMN canonical_key TEXT NOT NULL DEFAULT ''"
            )
        rows = connection.execute(
            "SELECT id, english_name FROM illness ORDER BY id"
        ).fetchall()
        for row in rows:
            connection.execute(
                "UPDATE illness SET canonical_key = ? WHERE id = ?",
                (canonical_illness_key(row["english_name"]), row["id"]),
            )
        duplicate_groups = connection.execute(
            """
            SELECT canonical_key
            FROM illness
            GROUP BY canonical_key
            HAVING canonical_key != '' AND COUNT(*) > 1
            """
        ).fetchall()
        for group in duplicate_groups:
            illness_ids = [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM illness WHERE canonical_key = ? ORDER BY id",
                    (group["canonical_key"],),
                )
            ]
            keeper_id, duplicate_ids = illness_ids[0], illness_ids[1:]
            for duplicate_id in duplicate_ids:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO treatment (herb_id, illness_id)
                    SELECT herb_id, ?
                    FROM treatment
                    WHERE illness_id = ?
                    """,
                    (keeper_id, duplicate_id),
                )
                connection.execute(
                    "DELETE FROM treatment WHERE illness_id = ?", (duplicate_id,)
                )
                connection.execute("DELETE FROM illness WHERE id = ?", (duplicate_id,))
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_illness_canonical_key "
            "ON illness(canonical_key)"
        )

    @staticmethod
    def _migrate_legacy_illnesses(connection: sqlite3.Connection) -> None:
        duplicate_names = connection.execute(
            """
            SELECT english_name
            FROM illness
            GROUP BY english_name
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        for row in duplicate_names:
            illness_ids = [
                illness_row["id"]
                for illness_row in connection.execute(
                    "SELECT id FROM illness WHERE english_name = ? ORDER BY id",
                    (row["english_name"],),
                )
            ]
            keeper_id, duplicate_ids = illness_ids[0], illness_ids[1:]
            for duplicate_id in duplicate_ids:
                connection.execute(
                    """
                    DELETE FROM treatment
                    WHERE illness_id = ?
                      AND herb_id IN (
                          SELECT herb_id FROM treatment WHERE illness_id = ?
                      )
                      AND EXISTS (
                          SELECT 1 FROM treatment
                          WHERE illness_id = ? AND herb_id = treatment.herb_id
                      )
                    """,
                    (duplicate_id, duplicate_id, keeper_id),
                )
                connection.execute(
                    "UPDATE treatment SET illness_id = ? WHERE illness_id = ?",
                    (keeper_id, duplicate_id),
                )
                connection.execute("DELETE FROM illness WHERE id = ?", (duplicate_id,))
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_illness_english_name "
            "ON illness(english_name)"
        )

    def insert_record(self, record: PlantRecord) -> int:
        """Upsert one record and its attributes in a single transaction."""
        self.create_database()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO herbs (
                    english_name, original_name, source, source_record_id, source_url,
                    botanical_name, family, retrieved_at, search_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, source_record_id) DO UPDATE SET
                    english_name = excluded.english_name,
                    original_name = excluded.original_name,
                    retrieved_at = excluded.retrieved_at,
                    search_key = excluded.search_key,
                    source_url = excluded.source_url,
                    botanical_name = excluded.botanical_name,
                    family = excluded.family
                """,
                (
                    record.transliterated_name or record.ayurvedic_name,
                    record.ayurvedic_name,
                    record.source,
                    record.source_record_id,
                    record.source_url,
                    record.botanical_name,
                    record.family,
                    record.retrieved_at,
                    search_key(record.transliterated_name or record.ayurvedic_name),
                ),
            )
            herb_id = connection.execute(
                "SELECT id FROM herbs WHERE source = ? AND source_record_id = ?",
                (record.source, record.source_record_id),
            ).fetchone()["id"]

            connection.execute("DELETE FROM herb_attributes WHERE herb_id = ?", (herb_id,))
            connection.execute(
                "DELETE FROM treatment WHERE herb_id = ? AND source = 'scraped'",
                (herb_id,),
            )
            connection.execute(
                "DELETE FROM herb_doshas WHERE herb_id = ? AND source = 'scraped'",
                (herb_id,),
            )
            connection.executemany(
                """
                INSERT INTO herb_attributes
                    (herb_id, field_name, value, source_text, source_language,
                     machine_generated, verification_status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        herb_id, field, value, record.source_values.get(field, value),
                        record.attribute_metadata.get(field, {}).get("source_language"),
                        int(record.attribute_metadata.get(field, {}).get("machine_generated", False)),
                        record.attribute_metadata.get(field, {}).get("verification_status"),
                    )
                    for field, values in record.attributes.items()
                    for value in values
                ),
            )
            self._insert_treatments_from_attributes(connection, herb_id, record)
            self._insert_doshas(connection, herb_id, record)

            now = datetime.now(timezone.utc).isoformat()
            source_id = self._ensure_source(connection, record.source)
            source_record_id = self._ensure_source_record(
                connection,
                source_id=source_id,
                external_record_key=str(record.source_record_id),
                source_url=record.source_url,
                retrieved_at=record.retrieved_at,
            )
            self._ensure_legacy_herb_map(connection, herb_id, now)
            self._sync_herb_names(connection, herb_id, source_record_id, record, now)
            self._sync_herb_taxa(connection, herb_id, source_record_id, record, now)
            self._sync_attribute_claims(connection, herb_id, source_record_id, record, now)
            return herb_id

    @staticmethod
    def _insert_doshas(
        connection: sqlite3.Connection,
        herb_id: int,
        record: PlantRecord,
    ) -> None:
        for expression in record.dosha_expressions:
            normalized = normalize_dosha_expression(expression)
            connection.executemany(
                """
                INSERT INTO herb_doshas
                    (herb_id, dosha, effect, source_expression, source)
                VALUES (?, ?, ?, ?, 'scraped')
                ON CONFLICT(herb_id, dosha, source_expression, source) DO UPDATE SET
                    effect = excluded.effect
                """,
                (
                    (herb_id, dosha, normalized.effects[dosha], expression)
                    for dosha in DOSHAS
                ),
            )

    @staticmethod
    def _insert_treatments_from_attributes(
        connection: sqlite3.Connection,
        herb_id: int,
        record: PlantRecord,
    ) -> None:
        therapeutic_values = {
            clean_text(attribute.value)
            for attribute in record.typed_attributes()
            if attribute.kind == "disease" and clean_text(attribute.value)
        }
        for illness_name in sorted(therapeutic_values):
            connection.execute(
                """
                INSERT INTO illness (
                    english_name, search_key, canonical_key,
                    machine_generated, verification_status
                )
                VALUES (?, ?, ?, 1, 'unverified')
                ON CONFLICT(canonical_key) DO NOTHING
                """,
                (
                    ascii_text(illness_name) or illness_name,
                    search_key(ascii_text(illness_name) or illness_name),
                    canonical_illness_key(illness_name),
                ),
            )
            illness_id = connection.execute(
                "SELECT id FROM illness WHERE canonical_key = ?",
                (canonical_illness_key(illness_name),),
            ).fetchone()["id"]
            connection.execute(
                """
                INSERT INTO treatment (herb_id, illness_id, source)
                VALUES (?, ?, 'scraped')
                ON CONFLICT(herb_id, illness_id) DO NOTHING
                """,
                (herb_id, illness_id),
            )

    def insert_records(self, records: Iterable[PlantRecord]) -> int:
        inserted = 0
        for record in records:
            self.insert_record(record)
            inserted += 1
        return inserted

    def insert_herb(self, id: int, english_name: str) -> bool:
        """Backward-compatible helper for the original prototype API."""
        self.create_database()
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO herbs (id, english_name) VALUES (?, ?)",
                (id, english_name),
            )
        return True

    def insert_illness(self, id: int, english_name: str) -> bool:
        """Backward-compatible helper for the original prototype API."""
        self.create_database()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO illness (
                    id, english_name, search_key, canonical_key,
                    machine_generated, verification_status
                ) VALUES (?, ?, ?, ?, 0, 'verified')
                """,
                (id, english_name, search_key(english_name), canonical_illness_key(english_name)),
            )
        return True

    def add_herb(
        self,
        english_name: str,
        source: str | None = None,
        source_record_id: int | None = None,
        source_url: str | None = None,
        botanical_name: str | None = None,
        family: str | None = None,
    ) -> int:
        """Insert one manually entered herb and return its database ID."""
        name = clean_text(english_name)
        if not name:
            raise ValueError("english_name cannot be empty")
        if source_record_id is not None and source_record_id <= 0:
            raise ValueError("source_record_id must be a positive integer")
        if source_url and not source_url.startswith(("http://", "https://")):
            raise ValueError("source_url must be an HTTP(S) URL")

        self.create_database()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO herbs (
                    english_name, source, source_record_id, source_url,
                    botanical_name, family, search_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    clean_text(source) if source else None,
                    source_record_id,
                    source_url,
                    clean_text(botanical_name) if botanical_name else None,
                    clean_text(family) if family else None,
                    search_key(name),
                ),
            )
            herb_id = cursor.lastrowid
            now = datetime.now(timezone.utc).isoformat()
            self._ensure_legacy_herb_map(connection, herb_id, now)
            source_key = self._legacy_source_key(source)
            source_id = self._ensure_source(connection, source_key)
            ext_key = str(source_record_id) if source_record_id is not None else None
            raw_ref = (
                f"legacy_herb_id:{herb_id}"
                if ext_key is None or source_key == "manual"
                else None
            )
            self._ensure_source_record(
                connection,
                source_id=source_id,
                external_record_key=ext_key,
                source_url=source_url,
                retrieved_at=now,
                raw_artifact_ref=raw_ref,
            )
            return herb_id

    def add_herb_attributes(
        self,
        herb_id: int,
        attributes: dict[str, list[str]],
    ) -> dict[str, Any]:
        """Add attributes to an existing herb, saving to legacy tables and source_claims."""
        if not isinstance(attributes, dict):
            raise ValueError("attributes must be a dictionary")

        allowed_prefixes = (
            "Rasa", "Guna", "Guṇa", "Virya", "Vīrya", "Vipaka", "Vipāka",
            "Prabhava", "Karma", "Doshakarma", "Parts Used", "Part Used",
            "Dosage Formulation", "Preparation", "Therapeutic Usage", "Vyadhi",
            "Indication", "Dose", "Varga", "Mahakashaya", "Pharmacopoeial Status",
            "Custom.", "Custom",
        )

        cleaned_attributes: dict[str, list[str]] = {}
        for raw_field, raw_values in attributes.items():
            field = clean_text(raw_field)
            if not field:
                continue
            if len(field) > 80:
                raise ValueError(f"Field name '{field}' exceeds maximum length of 80 characters.")

            is_allowed = any(
                field == prefix
                or field.startswith(prefix + ".")
                or field.startswith(prefix + " ")
                or field.startswith(prefix + "_")
                or field.startswith(prefix + ":")
                or (prefix in ("Custom.", "Custom") and field.startswith("Custom"))
                for prefix in allowed_prefixes
            )
            if not is_allowed:
                raise ValueError(
                    f"Invalid attribute field: '{field}'. Must match recognized Dravyaguna fields or start with 'Custom.'."
                )

            if isinstance(raw_values, str):
                val_list = [raw_values]
            elif isinstance(raw_values, (list, tuple, set)):
                val_list = list(raw_values)
            else:
                raise ValueError(f"Values for field '{field}' must be a list of strings.")

            if len(val_list) > 30:
                raise ValueError(f"Field '{field}' has too many values ({len(val_list)} > max 30).")

            cleaned_vals: list[str] = []
            for v in val_list:
                c_v = clean_text(str(v))
                if not c_v:
                    continue
                if len(c_v) > 300:
                    raise ValueError(f"Value in field '{field}' exceeds maximum length of 300 characters.")
                cleaned_vals.append(c_v)

            if cleaned_vals:
                cleaned_attributes[field] = cleaned_vals

        self.create_database()
        attributes_added = 0
        claims_added = 0
        now = datetime.now(timezone.utc).isoformat()
        is_v3 = False

        with self._connection() as connection:
            herb = connection.execute(
                "SELECT id, source, source_record_id, source_url FROM herbs WHERE id = ?",
                (herb_id,),
            ).fetchone()
            if not herb:
                raise ValueError(f"Herb with ID {herb_id} does not exist.")

            source_key = self._legacy_source_key(herb["source"])
            ext_key = str(herb["source_record_id"]) if herb["source_record_id"] is not None else None
            raw_ref = f"legacy_herb_id:{herb_id}" if ext_key is None or source_key == "manual" else None

            claim_source_key = "manual" if ext_key is None else source_key
            source_id = self._ensure_source(connection, claim_source_key)
            source_record_id = self._ensure_source_record(
                connection,
                source_id=source_id,
                external_record_key=ext_key,
                source_url=herb["source_url"],
                retrieved_at=now,
                raw_artifact_ref=raw_ref,
            )
            self._ensure_legacy_herb_map(connection, herb_id, now)

            has_source_claims = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='source_claims'"
            ).fetchone() is not None

            for field, values in cleaned_attributes.items():
                for val in values:
                    cur = connection.execute(
                        """
                        INSERT OR IGNORE INTO herb_attributes
                            (herb_id, field_name, value, source_text, source_language,
                             machine_generated, verification_status)
                        VALUES (?, ?, ?, ?, 'und', 0, 'unreviewed')
                        """,
                        (herb_id, field, val, val),
                    )
                    if cur.rowcount > 0:
                        attributes_added += 1

                    if has_source_claims:
                        claim_type = "dosha_expression" if field.startswith("Doshakarma") else "attribute"
                        existing_claim = connection.execute(
                            """
                            SELECT source_claim_id FROM source_claims
                            WHERE source_record_id = ? AND claim_type = ? AND source_field = ?
                                  AND source_expression = ? AND verification_status != 'superseded'
                            """,
                            (source_record_id, claim_type, field, val),
                        ).fetchone()
                        if existing_claim is None:
                            self._record_claim(
                                connection,
                                source_record_id=source_record_id,
                                claim_type=claim_type,
                                source_field=field,
                                source_expression=val,
                                language_code="und",
                                retrieved_at=now,
                                created_by_type="human",
                                created_by="manual",
                                verification_status="unreviewed",
                                now=now,
                            )
                            claims_added += 1

                if field.startswith("Doshakarma"):
                    for val in values:
                        normalized = normalize_dosha_expression(val)
                        for dosha in DOSHAS:
                            connection.execute(
                                """
                                INSERT INTO herb_doshas
                                    (herb_id, dosha, effect, source_expression, source)
                                VALUES (?, ?, ?, ?, 'manual')
                                ON CONFLICT(herb_id, dosha, source_expression, source) DO UPDATE SET
                                    effect = excluded.effect
                                """,
                                (herb_id, dosha, normalized.effects[dosha], val),
                            )

                if field.startswith(("Therapeutic Usage", "Vyadhi", "Indication")):
                    for val in values:
                        for ill_name in val.split(","):
                            ill_name = clean_text(ill_name)
                            if not ill_name:
                                continue
                            canon = canonical_illness_key(ill_name)
                            if not canon:
                                continue
                            connection.execute(
                                """
                                INSERT INTO illness (
                                    english_name, search_key, canonical_key,
                                    machine_generated, verification_status
                                )
                                VALUES (?, ?, ?, 0, 'unverified')
                                ON CONFLICT(canonical_key) DO NOTHING
                                """,
                                (
                                    ascii_text(ill_name) or ill_name,
                                    search_key(ascii_text(ill_name) or ill_name),
                                    canon,
                                ),
                            )
                            ill_row = connection.execute(
                                "SELECT id FROM illness WHERE canonical_key = ?",
                                (canon,),
                            ).fetchone()
                            if ill_row:
                                connection.execute(
                                    """
                                    INSERT INTO treatment (herb_id, illness_id, source)
                                    VALUES (?, ?, 'manual')
                                    ON CONFLICT(herb_id, illness_id) DO NOTHING
                                    """,
                                    (herb_id, ill_row["id"]),
                                )

            try:
                from .schema_capability_gate import get_schema_version
                if get_schema_version(connection) >= 3:
                    is_v3 = True
            except Exception:
                is_v3 = False

        stage_c_backfilled = False
        if is_v3:
            self.run_stage_c_backfill()
            stage_c_backfilled = True

        return {
            "herb_id": herb_id,
            "attributes_added": attributes_added,
            "claims_added": claims_added,
            "stage_c_backfilled": stage_c_backfilled,
        }

    def add_illness(self, english_name: str) -> int:
        """Insert one illness and return its database ID."""
        name = clean_text(english_name)
        if not name:
            raise ValueError("english_name cannot be empty")

        self.create_database()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO illness (
                    english_name, search_key, canonical_key,
                    machine_generated, verification_status
                ) VALUES (?, ?, ?, 0, 'verified')
                """,
                (name, search_key(name), canonical_illness_key(name)),
            )
            return cursor.lastrowid

    def add_treatment(self, herb_id: int, illness_id: int) -> None:
        """Create one herb/illness relationship, enforcing foreign keys."""
        if herb_id <= 0 or illness_id <= 0:
            raise ValueError("herb_id and illness_id must be positive integers")

        self.create_database()
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO treatment (herb_id, illness_id, source) VALUES (?, ?, 'manual')",
                (herb_id, illness_id),
            )

    def dashboard_summary(self) -> dict[str, Any]:
        """Return lightweight counts and recent herbs for the web dashboard."""
        self.create_database()
        with self._connection() as connection:
            counts = {
                "herbs": connection.execute("SELECT COUNT(*) FROM herbs").fetchone()[0],
                "illnesses": connection.execute("SELECT COUNT(*) FROM illness").fetchone()[0],
                "treatments": connection.execute("SELECT COUNT(*) FROM treatment").fetchone()[0],
                "attributes": connection.execute("SELECT COUNT(*) FROM herb_attributes").fetchone()[0],
            }
            recent = connection.execute(
                """
                SELECT id, english_name, original_name, botanical_name, family
                FROM herbs
                ORDER BY id DESC
                LIMIT 6
                """
            ).fetchall()
            top_illnesses = connection.execute(
                """
                SELECT i.id, i.english_name, COUNT(t.herb_id) AS herb_count
                FROM illness i
                JOIN treatment t ON i.id = t.illness_id
                GROUP BY i.id, i.english_name
                ORDER BY herb_count DESC, i.english_name ASC
                LIMIT 6
                """
            ).fetchall()
        return {
            **counts,
            "recent_herbs": [dict(row) for row in recent],
            "top_illnesses": [dict(row) for row in top_illnesses],
        }

    def get_herb(self, herb_id: int) -> dict[str, Any] | None:
        """Return one herb's core identity, or None when it does not exist."""
        if herb_id <= 0:
            return None
        self.create_database()
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, english_name, original_name, source, source_record_id,
                       source_url, retrieved_at, botanical_name, family
                FROM herbs
                WHERE id = ?
                """,
                (herb_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def search_herbs(self, query: str = "") -> list[dict[str, Any]]:
        """Return herbs ranked by normalized exact, substring, and fuzzy match, including vernacular names."""
        self.create_database()
        clean_q = query.strip()
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, english_name, original_name, botanical_name, family, source
                FROM herbs
                ORDER BY english_name
                """,
            ).fetchall()
            vernacular_matched_ids: set[int] = set()
            if clean_q:
                try:
                    v_matches = connection.execute(
                        """
                        SELECT DISTINCT herb_id
                        FROM herb_attributes
                        WHERE field_name LIKE 'Vernacular Names.%'
                          AND (value LIKE ? OR source_text LIKE ?)
                        """,
                        (f"%{clean_q}%", f"%{clean_q}%"),
                    ).fetchall()
                    vernacular_matched_ids = {r[0] for r in v_matches}
                except Exception:
                    pass

                try:
                    from .herb_glossary import normalize_binomial, search_herb_glossary

                    glossary_herbs = search_herb_glossary(clean_q)
                    if glossary_herbs:
                        ccras_ids = [gh.ccras_id for gh in glossary_herbs if gh.ccras_id is not None]
                        if ccras_ids:
                            placeholders = ",".join("?" for _ in ccras_ids)
                            id_matches = connection.execute(
                                f"""
                                SELECT id FROM herbs
                                WHERE (
                                    source = 'CCRAS DRAVYA'
                                    OR source = 'DRAVYA'
                                    OR lower(trim(source)) IN ('ccras dravya', 'ccras', 'dravya', 'ccras_dravya', 'ccras-dravya')
                                ) AND source_record_id IN ({placeholders})
                                """,
                                ccras_ids,
                            ).fetchall()
                            for r in id_matches:
                                vernacular_matched_ids.add(r[0])

                        hit_binomials = {
                            normalize_binomial(gh.botanical_name)
                            for gh in glossary_herbs
                            if gh.botanical_name
                        }
                        hit_binomials.discard("")
                        if hit_binomials:
                            b_matches = connection.execute(
                                "SELECT id, botanical_name FROM herbs WHERE botanical_name IS NOT NULL AND botanical_name != ''"
                            ).fetchall()
                            for r in b_matches:
                                if normalize_binomial(r[1]) in hit_binomials:
                                    vernacular_matched_ids.add(r[0])
                except Exception:
                    pass

        augmented_rows: list[dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            if item["id"] in vernacular_matched_ids:
                item["vernacular_name"] = clean_q
            else:
                item["vernacular_name"] = ""
            augmented_rows.append(item)

        return self._rank_rows(
            augmented_rows,
            query,
            ("english_name", "original_name", "botanical_name", "vernacular_name"),
        )

    def search_illnesses(self, query: str = "") -> list[dict[str, Any]]:
        """Return illnesses whose names contain the query."""
        self.create_database()
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, english_name, canonical_key
                FROM illness
                ORDER BY english_name
                """,
            ).fetchall()
        return self._rank_rows(rows, query, ("english_name", "canonical_key"), aliases_enabled=True)

    @staticmethod
    def _rank_rows(
        rows: Iterable[sqlite3.Row],
        query: str,
        fields: tuple[str, ...],
        aliases_enabled: bool = False,
    ) -> list[dict[str, Any]]:
        normalized = search_key(query)
        aliases = [normalized]
        if aliases_enabled and query.strip():
            alias = ILLNESS_ALIASES.get(normalized)
            if alias:
                aliases.append(canonical_illness_key(alias))
            try:
                from .illness_glossary import search_glossary, tolerant_illness_key

                for g in search_glossary(query):
                    for term_candidate in (
                        g.original_term,
                        canonical_illness_key(g.original_term),
                        tolerant_illness_key(g.original_term),
                        g.english,
                    ):
                        if term_candidate:
                            aliases.append(search_key(term_candidate))
                    for syn in g.english_synonyms:
                        aliases.append(search_key(syn))
                    for part in g.original_term.split("/"):
                        aliases.append(search_key(part))
                        aliases.append(canonical_illness_key(part))
            except Exception:
                pass
        ranked: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            item = dict(row)
            candidates = [search_key(str(item.get(field) or "")) for field in fields]
            score = max(
                max(
                    1.0 if term == candidate else
                    0.9 if term and term in candidate else
                    SequenceMatcher(None, term, candidate).ratio()
                    for term in aliases
                )
                for candidate in candidates
            ) if normalized else 1.0
            item["match_score"] = round(score, 4)
            ranked.append((score, item))
        ranked.sort(key=lambda pair: (-pair[0], str(pair[1].get(fields[0], "")).casefold()))
        if not normalized:
            return [item for _, item in ranked]
        return [
            item for score, item in ranked
            if score >= MIN_SEARCH_SCORE
        ]

    def treatment_details(self, herb_id: int) -> list[dict[str, Any]]:
        """Return illnesses associated with one herb."""
        self.create_database()
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT i.id, i.english_name, t.source
                FROM treatment AS t
                JOIN illness AS i ON i.id = t.illness_id
                WHERE t.herb_id = ?
                ORDER BY i.english_name
                """,
                (herb_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_illness(self, illness_id: int) -> dict[str, Any] | None:
        """Return one illness's core identity, or None when it does not exist."""
        if illness_id <= 0:
            return None
        self.create_database()
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, english_name, canonical_key, machine_generated, verification_status
                FROM illness
                WHERE id = ?
                """,
                (illness_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def illness_summaries(self, query: str = "") -> list[dict[str, Any]]:
        """Return illnesses matching query with associated herb counts, ranked."""
        self.create_database()
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT i.id, i.english_name, i.canonical_key, COUNT(t.herb_id) AS herb_count
                FROM illness i
                LEFT JOIN treatment t ON i.id = t.illness_id
                GROUP BY i.id, i.english_name, i.canonical_key
                ORDER BY i.english_name
                """,
            ).fetchall()
        ranked = self._rank_rows(rows, query, ("english_name", "canonical_key"), aliases_enabled=True)
        return [
            {
                "id": item["id"],
                "english_name": item["english_name"],
                "herb_count": item["herb_count"],
            }
            for item in ranked
        ]

    def herbs_for_illness(self, illness_id: int) -> list[dict[str, Any]]:
        """Return herbs associated with one illness, parameterized."""
        if illness_id <= 0:
            return []
        self.create_database()
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT h.id, h.english_name, h.original_name, h.botanical_name, h.family,
                       h.source, h.source_record_id, t.source AS link_source
                FROM treatment AS t
                JOIN herbs AS h ON h.id = t.herb_id
                WHERE t.illness_id = ?
                ORDER BY h.english_name, h.original_name
                """,
                (illness_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def herb_attributes(self, herb_id: int) -> list[dict[str, Any]]:
        """Return all source attributes for one herb."""
        self.create_database()
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT h.id AS herb_id, h.english_name AS herb_name,
                       a.field_name, a.value, a.source_text, a.source_language,
                       a.machine_generated, a.verification_status
                FROM herb_attributes AS a
                JOIN herbs AS h ON h.id = a.herb_id
                WHERE a.herb_id = ?
                ORDER BY a.field_name, a.rowid
                """,
                (herb_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def herb_doshas(self, herb_id: int) -> list[dict[str, Any]]:
        """Return normalized Dosha effects and their source expressions."""
        self.create_database()
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT herb_id, dosha, effect, source_expression, source
                FROM herb_doshas
                WHERE herb_id = ?
                ORDER BY source_expression, dosha, source
                """,
                (herb_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def herb_claims(self, herb_id: int) -> list[dict[str, Any]]:
        """Return all traceable source claims associated with a herb."""
        self.create_database()
        with self._connection() as connection:
            herb = connection.execute(
                "SELECT id, source, source_record_id FROM herbs WHERE id = ?",
                (herb_id,),
            ).fetchone()
            if not herb:
                return []
            source_key = self._legacy_source_key(herb["source"])
            if herb["source_record_id"] is not None:
                sr_clause = "sr.external_record_key = ? AND s.source_key = ?"
                sr_param = (str(herb["source_record_id"]), source_key)
            else:
                sr_clause = "sr.raw_artifact_ref = ? AND (s.source_key = ? OR s.source_key = 'manual')"
                sr_param = (f"legacy_herb_id:{herb_id}", source_key)

            rows = connection.execute(
                f"""
                SELECT sc.source_claim_id, sc.source_record_id, s.source_key,
                       sr.external_record_key, sr.source_url, sc.claim_type,
                       sc.source_field, sc.source_expression, sc.language_code,
                       sc.verification_status, sc.created_by_type, sc.created_by,
                       sc.created_at, sc.updated_at, sc.supersedes_claim_id
                FROM source_claims AS sc
                JOIN source_records AS sr ON sr.source_record_id = sc.source_record_id
                JOIN sources AS s ON s.source_id = sr.source_id
                WHERE {sr_clause}
                ORDER BY sc.source_claim_id
                """,
                sr_param,
            ).fetchall()
            return [dict(row) for row in rows]

    def herb_source_record(self, herb_id: int) -> dict[str, Any] | None:
        """Return the source record metadata for a herb."""
        self.create_database()
        with self._connection() as connection:
            herb = connection.execute(
                "SELECT id, source, source_record_id FROM herbs WHERE id = ?",
                (herb_id,),
            ).fetchone()
            if not herb:
                return None
            source_key = self._legacy_source_key(herb["source"])
            if herb["source_record_id"] is not None:
                sr_clause = "sr.external_record_key = ? AND s.source_key = ?"
                sr_param = (str(herb["source_record_id"]), source_key)
            else:
                sr_clause = "sr.raw_artifact_ref = ? AND (s.source_key = ? OR s.source_key = 'manual')"
                sr_param = (f"legacy_herb_id:{herb_id}", source_key)

            row = connection.execute(
                f"""
                SELECT sr.source_record_id, sr.source_id, s.source_key,
                       sr.external_record_key, sr.source_url, sr.retrieved_at,
                       sr.raw_artifact_ref, s.title AS source_title, s.publisher
                FROM source_records AS sr
                JOIN sources AS s ON s.source_id = sr.source_id
                WHERE {sr_clause}
                """,
                sr_param,
            ).fetchone()
            return dict(row) if row else None

    def all_records(self) -> dict[str, list[dict[str, Any]]]:
        """Return all herbs, illnesses, treatments, and herb attributes."""
        self.create_database()
        with self._connection() as connection:
            herbs = connection.execute(
                """
                SELECT id, english_name, original_name, source, source_record_id,
                       source_url, retrieved_at, botanical_name, family
                FROM herbs
                ORDER BY id
                """
            ).fetchall()
            illnesses = connection.execute(
                "SELECT id, english_name, machine_generated, verification_status "
                "FROM illness ORDER BY id"
            ).fetchall()
            treatments = connection.execute(
                """
                SELECT t.herb_id, h.english_name AS herb_name,
                       h.original_name AS herb_original_name,
                       h.botanical_name, h.source, h.source_record_id,
                       t.illness_id, i.english_name AS illness_name
                FROM treatment AS t
                JOIN herbs AS h ON h.id = t.herb_id
                JOIN illness AS i ON i.id = t.illness_id
                ORDER BY t.herb_id, t.illness_id
                """
            ).fetchall()
            attributes = connection.execute(
                """
                SELECT h.id AS herb_id, h.english_name AS herb_name,
                       a.field_name, a.value, a.source_text, a.source_language,
                       a.machine_generated, a.verification_status
                FROM herb_attributes AS a
                JOIN herbs AS h ON h.id = a.herb_id
                ORDER BY a.herb_id, a.field_name, a.rowid
                """
            ).fetchall()
            doshas = connection.execute(
                """
                SELECT d.herb_id, h.english_name AS herb_name, d.dosha,
                       d.effect, d.source_expression, d.source
                FROM herb_doshas AS d
                JOIN herbs AS h ON h.id = d.herb_id
                ORDER BY d.herb_id, d.source_expression, d.dosha, d.source
                """
            ).fetchall()
        return {
            "herbs": [dict(row) for row in herbs],
            "illnesses": [dict(row) for row in illnesses],
            "treatments": [dict(row) for row in treatments],
            "attributes": [dict(row) for row in attributes],
            "doshas": [dict(row) for row in doshas],
        }

    def upgrade_to_stage_c(self, now: str | None = None) -> dict[str, Any]:
        """Upgrades the database to Schema Version 3 (Semantic Dravyaguna).

        Applies Migration 3 and seeds the canonical concept catalog inside a
        serialized transaction while cryptographically verifying
        pre- and post-upgrade Stage B row invariance.
        """
        if now is None:
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self._initialization_lock:
            connection = self.connect()
            try:
                connection.execute("PRAGMA busy_timeout = 10000")

                # Verify current ledger: must be exactly [1, 2]
                current_version = validate_schema_migration_ledger(connection)
                if current_version == 3:
                    return {"status": "already_upgraded", "version": 3}

                # Capture pre-migration snapshot of all 13 Stage B tables
                pre_snapshot = capture_stage_b_table_snapshot(connection)

                # Apply Migration 3 (atomically acquires write transaction, executes DDL, and commits)
                migration_0003_semantic_dravyaguna.apply_migration(connection, applied_at=now)

                # Seed Canonical Concept Catalog and verify Stage B row invariance
                connection.execute("BEGIN IMMEDIATE")
                seed_counts = seed_canonical_concept_catalog(connection, now=now)
                post_snapshot = capture_stage_b_table_snapshot(connection)
                verify_stage_b_row_invariance(pre_snapshot, post_snapshot)
                connection.commit()

                return {
                    "status": "upgraded",
                    "version": 3,
                    "seeded_catalog": seed_counts,
                }
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()

    def run_stage_c_backfill(self, now: str | None = None) -> dict[str, Any]:
        """Backfills legacy Stage B claims into normalized Stage C tables.

        Requires Schema Version 3 and operates inside a BEGIN IMMEDIATE
        transaction while cryptographically verifying pre- and post-backfill
        Stage B row invariance.
        """
        if now is None:
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self._initialization_lock:
            connection = self.connect()
            try:
                connection.execute("PRAGMA busy_timeout = 10000")
                connection.execute("BEGIN IMMEDIATE")

                require_stage_c_schema_v3(connection)

                # Capture pre-backfill snapshot of all 13 Stage B tables
                pre_snapshot = capture_stage_b_table_snapshot(connection)

                # Run Stage C semantic backfill
                backfill_stats = run_stage_c_semantic_backfill(connection, now=now)

                # Verify post-backfill Stage B row invariance
                post_snapshot = capture_stage_b_table_snapshot(connection)
                verify_stage_b_row_invariance(pre_snapshot, post_snapshot)

                connection.commit()
                return {
                    "status": "backfilled",
                    "version": 3,
                    "backfill_stats": backfill_stats,
                }
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()


if __name__ == "__main__":
    AyurvedicAlmanac().create_database()
