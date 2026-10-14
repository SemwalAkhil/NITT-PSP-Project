from __future__ import annotations

import sqlite3
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from cleaning import PlantRecord, ascii_text, clean_text


def search_key(value: str) -> str:
    return " ".join(
        character
        for character in clean_text(value).casefold()
        if character.isalnum() or character.isspace()
    ).strip()


class AyurvedicAlmanac:
    """SQLite persistence for cleaned DRAVYA plant records."""

    supported_languages = [
        "English", "Assamese", "Bengali", "Bodo", "Dogri", "Gujarati", "Hindi",
        "Kannada", "Kashmiri", "Konkani", "Maithili", "Malayalam",
        "Manipuri", "Marathi", "Nepali", "Odia", "Punjabi", "Sanskrit",
        "Santali", "Sindhi", "Tamil", "Telugu", "Urdu",
    ]

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path or Path(__file__).with_name("AyurvedicDB.db"))
        self._initialized = False

    def connect(self) -> sqlite3.Connection:
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
                    search_key TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS treatment (
                    herb_id INTEGER NOT NULL,
                    illness_id INTEGER NOT NULL,
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
                """
            )
            self._migrate_legacy_herbs(connection)
            self._migrate_legacy_attributes(connection)
            self._migrate_legacy_illnesses(connection)
            self._migrate_search_columns(connection)
        self._initialized = True

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
                f"SELECT id, english_name FROM {table} "
                "WHERE search_key = '' OR search_key IS NULL"
            ).fetchall()
            for row in rows:
                connection.execute(
                    f"UPDATE {table} SET search_key = ? WHERE id = ?",
                    (search_key(row["english_name"]), row["id"]),
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
            connection.execute("DELETE FROM treatment WHERE herb_id = ?", (herb_id,))
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
            return herb_id

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
                INSERT INTO illness (english_name, search_key)
                VALUES (?, ?)
                ON CONFLICT(english_name) DO NOTHING
                """,
                (
                    ascii_text(illness_name) or illness_name,
                    search_key(ascii_text(illness_name) or illness_name),
                ),
            )
            illness_id = connection.execute(
                "SELECT id FROM illness WHERE english_name = ?",
                (ascii_text(illness_name) or illness_name,),
            ).fetchone()["id"]
            connection.execute(
                """
                INSERT INTO treatment (herb_id, illness_id)
                VALUES (?, ?)
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
                "INSERT INTO illness (id, english_name) VALUES (?, ?)",
                (id, english_name),
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
                "INSERT INTO illness (english_name, search_key) VALUES (?, ?)",
                (name, search_key(name)),
            )
            return cursor.lastrowid

    def add_treatment(self, herb_id: int, illness_id: int) -> None:
        """Create one herb/illness relationship, enforcing foreign keys."""
        if herb_id <= 0 or illness_id <= 0:
            raise ValueError("herb_id and illness_id must be positive integers")

        self.create_database()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO treatment (herb_id, illness_id) VALUES (?, ?)",
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
                SELECT id, english_name
                FROM illness
                ORDER BY english_name
                """,
            ).fetchall()
        return self._rank_rows(rows, query, ("english_name",))

    @staticmethod
    def _rank_rows(
        rows: Iterable[sqlite3.Row],
        query: str,
        fields: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        normalized = search_key(query)
        ranked: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            item = dict(row)
            candidates = [search_key(str(item.get(field) or "")) for field in fields]
            score = max(
                1.0 if normalized and normalized in candidate else
                SequenceMatcher(None, normalized, candidate).ratio()
                for candidate in candidates
            ) if normalized else 1.0
            item["match_score"] = round(score, 4)
            ranked.append((score, item))
        ranked.sort(key=lambda pair: (-pair[0], str(pair[1].get(fields[0], "")).casefold()))
        return [item for _, item in ranked]

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
                "SELECT id, english_name FROM illness ORDER BY id"
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
        return {
            "herbs": [dict(row) for row in herbs],
            "illnesses": [dict(row) for row in illnesses],
            "treatments": [dict(row) for row in treatments],
            "attributes": [dict(row) for row in attributes],
        }


if __name__ == "__main__":
    AyurvedicAlmanac().create_database()
