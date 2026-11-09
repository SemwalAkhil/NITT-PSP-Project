import pytest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier

from herbal_almanac.database_operator import (
    AyurvedicAlmanac,
    MIGRATION_1_VERSION,
    MIGRATION_2_VERSION,
)


def test_concurrent_database_initialization(tmp_path):
    """Independent instances serialize migration checks for one SQLite file."""
    db_path = tmp_path / "concurrent_test.db"
    workers = 10
    barrier = Barrier(workers)

    def initialize():
        database = AyurvedicAlmanac(db_path)
        barrier.wait()
        database.create_database()
        return True

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(lambda _: initialize(), range(workers)))

    assert all(results)
    assert db_path.exists()
    with closing(AyurvedicAlmanac(db_path).connect()) as connection:
        versions = [
            row["version"]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
    assert versions == [MIGRATION_1_VERSION, MIGRATION_2_VERSION]


def test_database_initialization_is_idempotent(tmp_path):
    database = AyurvedicAlmanac(tmp_path / "idempotent_test.db")
    database.create_database()
    database.create_database()
    database.create_database()
    with closing(database.connect()) as connection:
        migrations = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
    versions = [row["version"] for row in migrations]
    assert versions == [MIGRATION_1_VERSION, MIGRATION_2_VERSION]
    assert len(versions) == len(set(versions))


def test_database_initialization_creates_required_tables(tmp_path):
    database = AyurvedicAlmanac(tmp_path / "fresh_test.db")
    database.create_database()
    with closing(database.connect()) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "herbs", "illness", "treatment", "herb_attributes", "herb_doshas",
        "sources", "source_records", "source_claims", "legacy_herb_map",
        "herb_names", "schema_migrations", "taxa", "taxon_relationships", "herb_taxa",
    }.issubset(tables)



def test_same_instance_initialization_is_thread_safe(tmp_path):
    """Threads sharing one instance should initialize exactly once safely."""
    database = AyurvedicAlmanac(tmp_path / "shared_instance.db")
    workers = 10
    barrier = Barrier(workers)

    def initialize():
        barrier.wait()
        database.create_database()
        return True

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(lambda _: initialize(), range(workers)))

    assert all(results)
    with closing(database.connect()) as connection:
        versions = [
            row["version"]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
    assert versions == [MIGRATION_1_VERSION, MIGRATION_2_VERSION]


def test_failed_migration_can_be_retried_without_recording_partial_version(tmp_path, monkeypatch):
    """A failed migration rolls back its ledger row and a retry completes."""
    database = AyurvedicAlmanac(tmp_path / "migration_retry.db")
    original_migration = database._migration_1_core_identity_and_provenance
    attempts = 0

    def fail_once(connection):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("simulated first attempt failure")
        original_migration(connection)

    monkeypatch.setattr(database, "_migration_1_core_identity_and_provenance", fail_once)

    with pytest.raises(RuntimeError, match="simulated first attempt failure"):
        database.create_database()

    assert not database._initialized
    # The versioned migration transaction rolled back its ledger creation.
    with closing(database.connect()) as connection:
        ledger_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
    assert ledger_exists is None

    database.create_database()
    assert database._initialized
    with closing(database.connect()) as connection:
        versions = [
            row["version"]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
    assert versions == [MIGRATION_1_VERSION, MIGRATION_2_VERSION]
