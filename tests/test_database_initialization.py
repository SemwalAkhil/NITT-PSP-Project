
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier

from herbal_almanac.database_operator import (
    AyurvedicAlmanac,
    MIGRATION_1_VERSION,
    MIGRATION_2_VERSION,
)


def test_concurrent_database_initialization(tmp_path):
    """Multiple instances should safely initialize the same database."""
    db_path = tmp_path / "concurrent_test.db"

    workers = 10
    barrier = Barrier(workers)

    def initialize():
        database = AyurvedicAlmanac(db_path)
        barrier.wait()
        database.create_database()
        return True

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(initialize)
            for _ in range(workers)
        ]
        results = [future.result() for future in futures]

    assert all(results)
    assert db_path.exists()

    database = AyurvedicAlmanac(db_path)

    with closing(database.connect()) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }

    assert {
        "herbs",
        "illness",
        "treatment",
        "herb_attributes",
        "herb_doshas",
        "schema_migrations",
    }.issubset(tables)


def test_database_initialization_is_idempotent(tmp_path):
    """Repeated initialization must not duplicate migrations."""
    db_path = tmp_path / "idempotent_test.db"
    database = AyurvedicAlmanac(db_path)

    database.create_database()
    database.create_database()
    database.create_database()

    with closing(database.connect()) as connection:
        migrations = connection.execute(
            """
            SELECT version, name
            FROM schema_migrations
            ORDER BY version
            """
        ).fetchall()

    versions = [row["version"] for row in migrations]

    assert versions == [
        MIGRATION_1_VERSION,
        MIGRATION_2_VERSION,
    ]
    assert len(versions) == len(set(versions))


def test_database_initialization_creates_required_tables(tmp_path):
    """A fresh database must contain all required core tables."""
    db_path = tmp_path / "fresh_test.db"
    database = AyurvedicAlmanac(db_path)

    database.create_database()

    with closing(database.connect()) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }

    required_tables = {
        "herbs",
        "illness",
        "treatment",
        "herb_attributes",
        "herb_doshas",
        "sources",
        "source_records",
        "source_claims",
        "herb_names",
        "schema_migrations",
    }

    assert required_tables.issubset(tables)
