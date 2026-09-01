from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class Database:
    """Small SQLite event store with ordered, file-based migrations."""

    def __init__(self, path: Path, migrations_dir: Path | None = None) -> None:
        self.path = Path(path)
        self.migrations_dir = migrations_dir or Path(__file__).with_name("migrations")
        self._write_lock = threading.RLock()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = {
                row["version"]
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for migration in sorted(self.migrations_dir.glob("*.sql")):
                if migration.name in applied:
                    continue
                script = migration.read_text(encoding="utf-8")
                # executescript otherwise commits DDL before the version record.
                # Keep both atomic so a failed migration can be safely retried.
                try:
                    connection.executescript("BEGIN IMMEDIATE;\n" + script)
                    connection.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                        (migration.name, utc_now()),
                    )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
            connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._write_lock:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    yield connection
                except Exception:
                    connection.rollback()
                    raise
                else:
                    connection.commit()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        with self._connect() as connection:
            connection.execute("BEGIN")
            try:
                yield connection
            finally:
                connection.rollback()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
        finally:
            connection.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def event_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    value["payload"] = json.loads(value.pop("payload_json"))
    return value
