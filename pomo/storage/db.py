"""SQLite connection factory and migration runner.

Provides :func:`get_connection` which returns an already-configured
:class:`sqlite3.Connection` with WAL mode, foreign keys enabled, and all
pending migrations applied.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import platformdirs


def _migrations_dir() -> Path:
    """Return the path to the bundled SQL migration files."""
    return Path(__file__).resolve().parent / "migrations"


def _default_db_path() -> Path:
    """Return the platform-appropriate default database path."""
    return Path(platformdirs.user_data_dir("pomo")) / "pomo.db"


def _resolve_db_path(db_path: str | Path | None = None) -> str:
    """Determine which database path to use.

    Priority: *POMO_DB_PATH* env var > explicit *db_path* arg > platform default.

    Returns:
        A string suitable for :func:`sqlite3.connect` (may be ``":memory:"``).
    """
    env = os.environ.get("POMO_DB_PATH")
    if env is not None:
        return env
    if db_path is not None:
        return str(db_path)
    return str(_default_db_path())


def _ensure_parent(db_path_str: str) -> None:
    """Create the parent directory for a file-based database."""
    if db_path_str == ":memory:":
        return
    Path(db_path_str).parent.mkdir(parents=True, exist_ok=True)


def _apply_pragmas(conn: sqlite3.Connection, db_path_str: str) -> None:
    """Enable WAL journal mode (file DBs only) and foreign keys."""
    if db_path_str != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")


def _ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    """Create the ``schema_migrations`` bookkeeping table if absent."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Apply any unapplied ``*.sql`` files from the migrations directory."""
    mdir = _migrations_dir()
    if not mdir.is_dir():
        return

    applied: set[str] = {
        row[0] for row in conn.execute("SELECT filename FROM schema_migrations").fetchall()
    }

    pending = sorted(p for p in mdir.iterdir() if p.suffix == ".sql" and p.name not in applied)

    for migration in pending:
        sql = migration.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (filename) VALUES (?)",
            (migration.name,),
        )
        conn.commit()


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Return a configured SQLite connection with all migrations applied.

    Args:
        db_path: Explicit database path.  Overridden by the ``POMO_DB_PATH``
            environment variable if set.  Falls back to the platform default
            (``~/.local/share/pomo/pomo.db`` on Linux) when both are absent.

    Returns:
        An open :class:`sqlite3.Connection` with WAL mode, foreign keys
        enabled, and all pending migrations applied.
    """
    resolved = _resolve_db_path(db_path)
    _ensure_parent(resolved)
    conn = sqlite3.connect(resolved)
    _apply_pragmas(conn, resolved)
    _ensure_schema_migrations(conn)
    _run_migrations(conn)
    return conn
