import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import pytest

from herbal_almanac.database_operator import AyurvedicAlmanac


def test_connect_returns_independent_connections(tmp_path):
    database = AyurvedicAlmanac(tmp_path / "connections.db")
    database.create_database()
    first = database.connect()
    second = database.connect()
    try:
        assert first is not second
        assert first.row_factory is sqlite3.Row
        assert second.row_factory is sqlite3.Row
        assert first.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert second.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        first.close()
        second.close()


def test_concurrent_database_access_uses_separate_connections(tmp_path):
    database = AyurvedicAlmanac(tmp_path / "thread_test.db")
    database.create_database()
    workers = 10
    connections = []
    lock = Lock()

    def read_database():
        connection = database.connect()
        try:
            with lock:
                connections.append(connection)
            return connection.execute("SELECT COUNT(*) FROM herbs").fetchone()[0]
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(lambda _: read_database(), range(workers)))

    assert results == [0] * workers
    assert len({id(connection) for connection in connections}) == workers


def test_connection_enforces_foreign_keys(tmp_path):
    database = AyurvedicAlmanac(tmp_path / "foreign_keys.db")
    database.create_database()
    connection = database.connect()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO treatment (herb_id, illness_id) VALUES (?, ?)",
                (99999, 99999),
            )
    finally:
        connection.close()


def test_transaction_rolls_back_on_exception(tmp_path):
    database = AyurvedicAlmanac(tmp_path / "rollback.db")
    database.create_database()
    with pytest.raises(RuntimeError):
        with database._connection() as connection:
            connection.execute("INSERT INTO herbs (english_name) VALUES (?)", ("Temporary Herb",))
            raise RuntimeError("Simulated transaction failure")

    with database._connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM herbs WHERE english_name = ?", ("Temporary Herb",)
        ).fetchone()[0]
    assert count == 0


@pytest.mark.parametrize("operation", ["add_herb", "search_herbs"])
def test_public_operations_close_connections_on_success(tmp_path, monkeypatch, operation):
    database = AyurvedicAlmanac(tmp_path / f"{operation}.db")
    database.create_database()
    created = []
    original_connect = database.connect

    def tracked_connect():
        connection = original_connect()
        created.append(connection)
        return connection

    monkeypatch.setattr(database, "connect", tracked_connect)
    if operation == "add_herb":
        database.add_herb("Tulsi")
    else:
        database.search_herbs()

    assert len(created) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        created[0].execute("SELECT 1")


def test_public_operation_closes_connection_on_failure(tmp_path, monkeypatch):
    database = AyurvedicAlmanac(tmp_path / "failure.db")
    database.create_database()
    created = []
    original_connect = database.connect

    def tracked_connect():
        connection = original_connect()
        created.append(connection)
        return connection

    monkeypatch.setattr(database, "connect", tracked_connect)
    with pytest.raises(sqlite3.IntegrityError):
        database.add_treatment(99999, 99999)

    assert len(created) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        created[0].execute("SELECT 1")


def test_initialization_connection_closes_after_success(tmp_path, monkeypatch):
    database = AyurvedicAlmanac(tmp_path / "initialization.db")
    created = []
    original_connect = database.connect

    def tracked_connect():
        connection = original_connect()
        created.append(connection)
        return connection

    monkeypatch.setattr(database, "connect", tracked_connect)
    database.create_database()

    assert len(created) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        created[0].execute("SELECT 1")


def test_initialization_connection_closes_after_failure(tmp_path, monkeypatch):
    database = AyurvedicAlmanac(tmp_path / "initialization_failure.db")
    created = []
    original_connect = database.connect

    def tracked_connect():
        connection = original_connect()
        created.append(connection)
        return connection

    def fail_migration(connection):
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(database, "connect", tracked_connect)
    monkeypatch.setattr(database, "_migration_1_core_identity_and_provenance", fail_migration)

    with pytest.raises(RuntimeError, match="simulated migration failure"):
        database.create_database()

    assert len(created) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        created[0].execute("SELECT 1")
    assert not database._initialized
