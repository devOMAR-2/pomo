"""Tests for pomo.storage.db — connection factory and migration runner."""

from __future__ import annotations

import os
import sqlite3
import textwrap
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _use_memory_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default all tests to in-memory SQLite via env var."""
    monkeypatch.setenv("POMO_DB_PATH", ":memory:")


@pytest.fixture()
def migrations_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temporary migrations directory and patch db._migrations_dir."""
    mdir = tmp_path / "migrations"
    mdir.mkdir()
    monkeypatch.setattr("pomo.storage.db._migrations_dir", lambda: mdir)
    return mdir


def _write_migration(mdir: Path, name: str, sql: str) -> Path:
    p = mdir / name
    p.write_text(textwrap.dedent(sql))
    return p


class TestGetConnectionBasics:
    """get_connection returns a usable, configured connection."""

    def test_returns_sqlite_connection(self, migrations_dir: Path) -> None:
        from pomo.storage.db import get_connection

        conn = get_connection()
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_foreign_keys_enabled(self, migrations_dir: Path) -> None:
        from pomo.storage.db import get_connection

        conn = get_connection()
        (fk,) = conn.execute("PRAGMA foreign_keys").fetchone()
        assert fk == 1
        conn.close()

    def test_wal_mode_on_file_db(
        self, tmp_path: Path, migrations_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db_file = tmp_path / "test.db"
        monkeypatch.setenv("POMO_DB_PATH", str(db_file))
        from pomo.storage.db import get_connection

        conn = get_connection()
        (mode,) = conn.execute("PRAGMA journal_mode").fetchone()
        assert mode == "wal"
        conn.close()

    def test_creates_parent_dir(
        self, tmp_path: Path, migrations_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db_file = tmp_path / "nested" / "deep" / "test.db"
        monkeypatch.setenv("POMO_DB_PATH", str(db_file))
        from pomo.storage.db import get_connection

        conn = get_connection()
        assert db_file.parent.exists()
        conn.close()


class TestMigrationRunner:
    """Migrations are applied exactly once, in numeric order."""

    def test_get_connection_twice_no_rerun(self, migrations_dir: Path) -> None:
        """AC: Calling get_connection() twice does not re-run migrations."""
        _write_migration(
            migrations_dir,
            "001_initial.sql",
            "CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY);",
        )
        from pomo.storage.db import get_connection

        conn1 = get_connection()
        rows1 = conn1.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        conn1.close()

        conn2 = get_connection()
        rows2 = conn2.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        assert rows2 == rows1 == 1
        conn2.close()

    def test_new_migration_applied_on_next_call(
        self, migrations_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC: Adding a new 002_*.sql file applies it on next call."""
        db_file = tmp_path / "mig.db"
        monkeypatch.setenv("POMO_DB_PATH", str(db_file))

        _write_migration(
            migrations_dir,
            "001_initial.sql",
            "CREATE TABLE t1 (id INTEGER PRIMARY KEY);",
        )
        from pomo.storage.db import get_connection

        conn1 = get_connection()
        count1 = conn1.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        assert count1 == 1
        conn1.close()

        _write_migration(
            migrations_dir,
            "002_add_col.sql",
            "CREATE TABLE t2 (id INTEGER PRIMARY KEY);",
        )

        conn2 = get_connection()
        count2 = conn2.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        assert count2 == 2
        # Verify the new table exists
        tables = {
            r[0]
            for r in conn2.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "t2" in tables
        conn2.close()

    def test_migrations_applied_in_order(self, migrations_dir: Path) -> None:
        _write_migration(
            migrations_dir, "001_first.sql", "CREATE TABLE first (id INTEGER PRIMARY KEY);"
        )
        _write_migration(
            migrations_dir, "002_second.sql", "CREATE TABLE second (id INTEGER PRIMARY KEY);"
        )
        from pomo.storage.db import get_connection

        conn = get_connection()
        rows = conn.execute("SELECT filename FROM schema_migrations ORDER BY filename").fetchall()
        assert [r[0] for r in rows] == ["001_first.sql", "002_second.sql"]
        conn.close()

    def test_no_migrations_dir_is_fine(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        empty_dir = tmp_path / "empty_migs"
        empty_dir.mkdir()
        monkeypatch.setattr("pomo.storage.db._migrations_dir", lambda: empty_dir)
        from pomo.storage.db import get_connection

        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        assert count == 0
        conn.close()


class TestInMemoryOverride:
    """AC: Unit tests use an in-memory DB via POMO_DB_PATH=:memory:."""

    def test_env_var_memory(self, migrations_dir: Path) -> None:
        assert os.environ.get("POMO_DB_PATH") == ":memory:"
        from pomo.storage.db import get_connection

        conn = get_connection()
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_explicit_path_arg(
        self, tmp_path: Path, migrations_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("POMO_DB_PATH", raising=False)
        db_file = tmp_path / "explicit.db"
        from pomo.storage.db import get_connection

        conn = get_connection(db_path=db_file)
        assert db_file.exists()
        conn.close()
