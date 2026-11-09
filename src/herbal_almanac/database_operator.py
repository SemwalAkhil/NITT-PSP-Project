from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from difflib import SequenceMatcher
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable

from .cleaning import DOSHAS, PlantRecord, ascii_text, clean_text, normalize_dosha_expression


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
}
MIN_SEARCH_SCORE = 0.65
MIGRATION_1_VERSION = 1
MIGRATION_1_NAME = "core_identity_and_provenance"


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

    def connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.row_factory = sqlite3.Row
        return connection

    def create_database(self) -> None:
        """Create the schema and apply small migrations to the prototype DB."""
        if self._initialized:
            return
        with self.connect() as connection:
            connection.executescript(
                """
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
            )
            self._validate_legacy_source_identity(connection)
            self._migrate_legacy_herbs(connection)
            self._migrate_legacy_attributes(connection)
            self._migrate_legacy_treatments(connection)
            self._migrate_legacy_illnesses(connection)
            self._migrate_search_columns(connection)
            self._migrate_illness_canonical_keys(connection)
            connection.commit()
            try:
                connection.execute("BEGIN")
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
                if MIGRATION_1_VERSION not in applied_versions:
                    self._migration_1_core_identity_and_provenance(connection)
                    connection.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (
                            MIGRATION_1_VERSION,
                            MIGRATION_1_NAME,
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
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
    def _migration_1_core_identity_and_provenance(
        cls, connection: sqlite3.Connection
    ) -> None:
        cls._create_migration_1_tables(connection)
        cls._backfill_migration_1(connection)

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
        with self.connect() as connection:
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
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO herbs (id, english_name) VALUES (?, ?)",
                (id, english_name),
            )
        return True

    def insert_illness(self, id: int, english_name: str) -> bool:
        """Backward-compatible helper for the original prototype API."""
        self.create_database()
        with self.connect() as connection:
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
        with self.connect() as connection:
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
            return cursor.lastrowid

    def add_illness(self, english_name: str) -> int:
        """Insert one illness and return its database ID."""
        name = clean_text(english_name)
        if not name:
            raise ValueError("english_name cannot be empty")

        self.create_database()
        with self.connect() as connection:
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
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO treatment (herb_id, illness_id, source) VALUES (?, ?, 'manual')",
                (herb_id, illness_id),
            )

    def search_herbs(self, query: str = "") -> list[dict[str, Any]]:
        """Return herbs ranked by normalized exact, substring, and fuzzy match."""
        self.create_database()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, english_name, original_name, botanical_name, family, source
                FROM herbs
                ORDER BY english_name
                """,
            ).fetchall()
        return self._rank_rows(rows, query, ("english_name", "original_name", "botanical_name"))

    def search_illnesses(self, query: str = "") -> list[dict[str, Any]]:
        """Return illnesses whose names contain the query."""
        self.create_database()
        with self.connect() as connection:
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
        alias = ILLNESS_ALIASES.get(normalized) if aliases_enabled else None
        if alias:
            aliases.append(canonical_illness_key(alias))
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
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT i.id, i.english_name
                FROM treatment AS t
                JOIN illness AS i ON i.id = t.illness_id
                WHERE t.herb_id = ?
                ORDER BY i.english_name
                """,
                (herb_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def herb_attributes(self, herb_id: int) -> list[dict[str, Any]]:
        """Return all source attributes for one herb."""
        self.create_database()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT h.id AS herb_id, h.english_name AS herb_name,
                       a.field_name, a.value, a.source_text, a.source_language,
                       a.machine_generated, a.verification_status
                FROM herb_attributes AS a
                JOIN herbs AS h ON h.id = a.herb_id
                WHERE a.herb_id = ?
                ORDER BY a.field_name, a.value
                """,
                (herb_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def herb_doshas(self, herb_id: int) -> list[dict[str, Any]]:
        """Return normalized Dosha effects and their source expressions."""
        self.create_database()
        with self.connect() as connection:
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

    def all_records(self) -> dict[str, list[dict[str, Any]]]:
        """Return all herbs, illnesses, treatments, and herb attributes."""
        self.create_database()
        with self.connect() as connection:
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
                ORDER BY a.herb_id, a.field_name, a.value
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


if __name__ == "__main__":
    AyurvedicAlmanac().create_database()
