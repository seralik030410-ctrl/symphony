from __future__ import annotations

import json
import shutil
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
        self.recovery_report: dict[str, Any] = {
            "status": "not_needed",
            "restored_from": None,
            "preserved_files": [],
        }

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists()
        if existed:
            healthy, reason = self.quick_check(self.path)
            if not healthy:
                self._recover(reason)
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
            connection.commit()
        migrations = [migration for migration in sorted(self.migrations_dir.glob("*.sql"))
                      if migration.name not in applied]
        if existed and migrations:
            self.create_backup("pre-migration")
        with self._connect() as connection:
            for migration in migrations:
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
        self.create_backup("startup")

    @property
    def backup_dir(self) -> Path:
        return self.path.parent / f"{self.path.stem}.backups"

    def create_backup(self, reason: str) -> Path:
        """Create a consistent online SQLite backup and retain the five newest copies."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        destination = self.backup_dir / f"{self.path.stem}-{stamp}-{reason}.sqlite3"
        with self._write_lock:
            source = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
                target.commit()
            except Exception:
                target.close()
                source.close()
                destination.unlink(missing_ok=True)
                raise
            else:
                target.close()
                source.close()
        try:
            healthy, reason_text = self.quick_check(destination)
        except RuntimeError:
            destination.unlink(missing_ok=True)
            raise
        if not healthy:
            destination.unlink(missing_ok=True)
            raise RuntimeError(f"SQLite backup validation failed: {reason_text}")
        backups = sorted(self.backup_dir.glob(f"{self.path.stem}-*.sqlite3"),
                         key=lambda item: item.stat().st_mtime, reverse=True)
        for obsolete in backups[5:]:
            obsolete.unlink(missing_ok=True)
        return destination

    def _recover(self, reason: str) -> None:
        candidates = sorted(self.backup_dir.glob(f"{self.path.stem}-*.sqlite3"),
                            key=lambda item: item.stat().st_mtime, reverse=True)
        valid: Path | None = None
        for candidate in candidates:
            try:
                if self.quick_check(candidate)[0]:
                    valid = candidate
                    break
            except RuntimeError:
                continue
        if valid is None:
            raise RuntimeError("SQLite database is corrupt and no valid recovery backup is available")

        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        staged = self.path.parent / f".{self.path.name}.restore-{stamp}.tmp"
        shutil.copy2(valid, staged)
        try:
            healthy, staged_reason = self.quick_check(staged)
        except RuntimeError:
            staged.unlink(missing_ok=True)
            raise
        if not healthy:
            staged.unlink(missing_ok=True)
            raise RuntimeError(f"SQLite recovery copy failed validation: {staged_reason}")

        preserved: list[Path] = []
        moved: list[tuple[Path, Path]] = []
        companions = [self.path, Path(f"{self.path}-wal"), Path(f"{self.path}-shm")]
        try:
            for source in companions:
                if not source.exists():
                    continue
                suffix = "primary" if source == self.path else source.name.removeprefix(self.path.name).lstrip("-")
                target = self.path.parent / f"{self.path.name}.corrupt-{stamp}.{suffix}"
                source.replace(target)
                preserved.append(target)
                moved.append((source, target))
            staged.replace(self.path)
        except Exception:
            staged.unlink(missing_ok=True)
            for original, saved in reversed(moved):
                if saved.exists() and not original.exists():
                    saved.replace(original)
            raise
        self.recovery_report = {
            "status": "restored",
            "reason": "primary_quick_check_failed",
            "restored_from": valid.name,
            "preserved_files": [item.name for item in preserved],
        }

    @staticmethod
    def quick_check(path: Path) -> tuple[bool, str]:
        if not path.exists():
            return False, "file is missing"
        connection: sqlite3.Connection | None = None
        try:
            uri = path.resolve().as_uri() + "?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=5)
            rows = connection.execute("PRAGMA quick_check").fetchall()
            messages = [str(row[0]) for row in rows]
            return messages == ["ok"], "; ".join(messages[:3])
        except sqlite3.Error as exc:
            corrupt_codes = {getattr(sqlite3, "SQLITE_CORRUPT", 11), getattr(sqlite3, "SQLITE_NOTADB", 26)}
            error_code = getattr(exc, "sqlite_errorcode", None)
            if isinstance(error_code, int) and (error_code & 0xFF) in corrupt_codes:
                return False, "database content is corrupt"
            raise RuntimeError("SQLite integrity check could not be completed; primary was left untouched") from exc
        finally:
            if connection is not None:
                connection.close()

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
