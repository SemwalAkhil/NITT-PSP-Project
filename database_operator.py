from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from cleaning import PlantRecord


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
            return herb_id

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
        self.create_database()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO illness (id, english_name) VALUES (?, ?)",
                (id, english_name),
            )
        return True


if __name__ == "__main__":
    AyurvedicAlmanac().create_database()
