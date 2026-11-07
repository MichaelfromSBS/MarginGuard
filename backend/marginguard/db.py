"""SQLite foundation. Initialization migrates schemas but never seeds business data."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3

MIGRATIONS_DIR = Path(__file__).with_name("migrations")
SCHEMA_VERSION = 1


class MigrationError(RuntimeError):
    """A migration cannot be applied safely without operator review."""


@contextmanager
def connect(path: str | Path) -> Iterator[sqlite3.Connection]:
    """Open a connection with foreign keys and transactional commit/rollback.

    Each request/worker should use its own short-lived connection. Exceptions
    roll back pending writes; no connection may span a model/network request.
    """
    if str(path) != ":memory:":
        Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _statements(sql: str) -> Iterator[str]:
    """Split complete SQLite statements without executescript's implicit commit."""
    pending = ""
    for line in sql.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            yield pending
            pending = ""
    if pending.strip():
        raise MigrationError("Migration has an incomplete SQL statement.")


def initialize_database(path: str | Path) -> int:
    """Apply versioned, checksummed migrations atomically and return the version."""
    files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))
    if not files:
        raise MigrationError("No database migrations were found.")
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
        """)
        applied = {row["version"]: row for row in connection.execute("SELECT * FROM schema_migrations")}
        known = {int(file.name.split("_", 1)[0]) for file in files}
        if any(version not in known for version in applied):
            raise MigrationError("Database has a schema version this application does not recognize.")
        for file in files:
            version = int(file.name.split("_", 1)[0])
            # Normalize platform line endings before checksumming a migration.
            content = file.read_text(encoding="utf-8")
            checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if version in applied:
                if applied[version]["checksum"] != checksum:
                    raise MigrationError(f"Applied migration {file.name} was modified; create a new migration instead.")
                continue
            for statement in _statements(content):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations(version, name, checksum, applied_at) VALUES (?, ?, ?, ?)",
                (version, file.name, checksum, datetime.now(timezone.utc).isoformat()),
            )
        return max(known)


def get_schema_version(path: str | Path) -> int:
    with connect(path) as connection:
        row = connection.execute("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations").fetchone()
        return int(row["version"])
