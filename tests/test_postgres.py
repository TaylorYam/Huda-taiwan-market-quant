from __future__ import annotations

from typing import Any

from src.data import PostgresObservationStore


class FakeCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute(self, statement: str, params: object = None) -> None:
        del params
        self.statements.append(statement)


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()
        self.commit_count = 0

    def cursor(self) -> FakeCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        raise AssertionError("schema initialization should not roll back")

    def close(self) -> None:
        return None


def test_postgres_store_loads_shared_observation_schema_without_driver() -> None:
    connection = FakeConnection()

    with PostgresObservationStore(
        "postgresql://example.invalid/database",
        connection_factory=lambda _dsn: connection,
    ):
        pass

    assert connection.commit_count == 1
    assert "CREATE TABLE IF NOT EXISTS observations" in connection.cursor_instance.statements[0]
    assert "JSONB NOT NULL" in connection.cursor_instance.statements[0]
