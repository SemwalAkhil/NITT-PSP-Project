from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from cleaning import PlantRecord, clean_text


class AyurvedicAlmanac:
    """SQLite persistence for cleaned DRAVYA plant records."""

    supported_languages = [
        "Assamese", "Bengali", "Bodo", "Dogri", "Gujarati", "Hindi",
        "Kannada", "Kashmiri", "Konkani", "Maithili", "Malayalam",
        "Manipuri", "Marathi", "Nepali", "Odia", "Punjabi", "Sanskrit",
        "Santali", "Sindhi", "Tamil", "Telugu", "Urdu",
    ]

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path or Path(__file__).with_name("AyurvedicDB.db"))

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.row_factory = sqlite3.Row
        return connection

    def create_database(self) -> None:
        """Create the schema and apply small migrations to the prototype DB."""
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS herbs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    english_name TEXT NOT NULL,
                    source TEXT,
                    source_record_id INTEGER,
                    source_url TEXT,
                    botanical_name TEXT,
                    family TEXT,
                    UNIQUE(source, source_record_id)
                );

                CREATE TABLE IF NOT EXISTS illness (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    english_name TEXT NOT NULL UNIQUE
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
                    PRIMARY KEY (herb_id, field_name, value),
                    FOREIGN KEY (herb_id) REFERENCES herbs(id) ON DELETE CASCADE
                );
                """
            )
            self._migrate_legacy_herbs(connection)

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
        ):
            if name not in columns:
                connection.execute(f"ALTER TABLE herbs ADD COLUMN {name} {definition}")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_herbs_source_record "
            "ON herbs(source, source_record_id)"
        )

    def insert_record(self, record: PlantRecord) -> int:
        """Upsert one record and its attributes in a single transaction."""
        self.create_database()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO herbs (
                    english_name, source, source_record_id, source_url,
                    botanical_name, family
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, source_record_id) DO UPDATE SET
                    english_name = excluded.english_name,
                    source_url = excluded.source_url,
                    botanical_name = excluded.botanical_name,
                    family = excluded.family
                """,
                (
                    record.ayurvedic_name,
                    record.source,
                    record.source_record_id,
                    record.source_url,
                    record.botanical_name,
                    record.family,
                ),
            )
            herb_id = connection.execute(
                "SELECT id FROM herbs WHERE source = ? AND source_record_id = ?",
                (record.source, record.source_record_id),
            ).fetchone()["id"]

            connection.execute("DELETE FROM herb_attributes WHERE herb_id = ?", (herb_id,))
            connection.executemany(
                """
                INSERT INTO herb_attributes
                    (herb_id, field_name, value, source_text)
                VALUES (?, ?, ?, ?)
                """,
                (
                    (herb_id, field, value, record.source_values.get(field, value))
                    for field, values in record.attributes.items()
                    for value in values
                ),
            )
            self._insert_treatments_from_attributes(connection, herb_id, record.attributes)
            return herb_id

    @staticmethod
    def _insert_treatments_from_attributes(
        connection: sqlite3.Connection,
        herb_id: int,
        attributes: dict[str, list[str]],
    ) -> None:
        therapeutic_values = [
            value
            for field, values in attributes.items()
            if "therapeutic" in field.casefold()
            and ("use" in field.casefold() or "usage" in field.casefold())
            for value in values
        ]
        for illness_name in therapeutic_values:
            connection.execute(
                """
                INSERT INTO illness (english_name)
                VALUES (?)
                ON CONFLICT(english_name) DO NOTHING
                """,
                (illness_name,),
            )
            illness_id = connection.execute(
                "SELECT id FROM illness WHERE english_name = ?",
                (illness_name,),
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
                    botanical_name, family
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    clean_text(source) if source else None,
                    source_record_id,
                    source_url,
                    clean_text(botanical_name) if botanical_name else None,
                    clean_text(family) if family else None,
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
                "INSERT INTO illness (english_name) VALUES (?)",
                (name,),
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
        """Return herbs whose names or botanical names contain the query."""
        self.create_database()
        pattern = f"%{clean_text(query)}%"
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, english_name, botanical_name, family, source
                FROM herbs
                WHERE english_name LIKE ?
                   OR botanical_name LIKE ?
                ORDER BY english_name
                """,
                (pattern, pattern),
            ).fetchall()
        return [dict(row) for row in rows]

    def search_illnesses(self, query: str = "") -> list[dict[str, Any]]:
        """Return illnesses whose names contain the query."""
        self.create_database()
        pattern = f"%{clean_text(query)}%"
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, english_name
                FROM illness
                WHERE english_name LIKE ?
                ORDER BY english_name
                """,
                (pattern,),
            ).fetchall()
        return [dict(row) for row in rows]

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
                       a.field_name, a.value, a.source_text
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
                SELECT id, english_name, source, source_record_id,
                       source_url, botanical_name, family
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
                       a.field_name, a.value, a.source_text
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
