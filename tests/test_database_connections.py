
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import pytest

from herbal_almanac.database_operator import AyurvedicAlmanac


def test_connect_returns_independent_connections(tmp_path):
    """Each connect() call should return a separate connection."""
    database = AyurvedicAlmanac(tmp_path / "connections.db")
    database.create_database()

    first = database.connect()
    second = database.connect()

    try:
        assert first is not second

        assert first.row_factory is sqlite3.Row
        assert second.row_factory is sqlite3.Row

        first_foreign_keys = first.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]

        second_foreign_keys = second.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]

        assert first_foreign_keys == 1
        assert second_foreign_keys == 1

    finally:
        first.close()
        second.close()


def test_concurrent_database_access_uses_separate_connections(tmp_path):
    """Concurrent threads should create and use independent connections."""
    database = AyurvedicAlmanac(tmp_path / "thread_test.db")
    database.create_database()

    workers = 10
    created_connections = []
    lock = Lock()

    def read_database():
        connection = database.connect()

        try:
            with lock:
                created_connections.append(connection)

            result = connection.execute(
                "SELECT COUNT(*) FROM herbs"
            ).fetchone()[0]

            return result

        finally:
            # Each connection is closed in the thread that created it.
            connection.close()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(
            executor.map(
                lambda _: read_database(),
                range(workers),
            )
        )

    assert len(results) == workers
    assert all(result == 0 for result in results)

    # Keep references to the connections so their identities
    # can be compared even after they have been closed.
    connection_ids = {
        id(connection)
        for connection in created_connections
    }

    assert len(connection_ids) == workers


def test_connection_enforces_foreign_keys(tmp_path):
    """Invalid foreign-key references must be rejected."""
    database = AyurvedicAlmanac(tmp_path / "foreign_keys.db")
    database.create_database()

    connection = database.connect()

    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO treatment (herb_id, illness_id)
                VALUES (?, ?)
                """,
                (99999, 99999),
            )

    finally:
        connection.close()


def test_transaction_rolls_back_on_exception(tmp_path):
    """An unsuccessful transaction must not persist partial data."""
    database = AyurvedicAlmanac(tmp_path / "rollback.db")
    database.create_database()

    with pytest.raises(RuntimeError):
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO herbs (english_name)
                VALUES (?)
                """,
                ("Temporary Herb",),
            )

            raise RuntimeError("Simulated transaction failure")

    # Verify that the insert was rolled back.
    connection = database.connect()

    try:
        count = connection.execute(
            """
            SELECT COUNT(*)
            FROM herbs
            WHERE english_name = ?
            """,
            ("Temporary Herb",),
        ).fetchone()[0]

        assert count == 0

    finally:
        connection.close()
