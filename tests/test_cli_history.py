"""Tests for the ``pomo history`` CLI command."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pomo.cli import app
from pomo.storage.db import get_connection
from pomo.storage.models import Session
from pomo.storage.repository import SessionRepository

runner = CliRunner()


def _has_tag(output: str, i: int) -> bool:
    """True iff ``tag-{i}`` appears as a whole token (not a substring of tag-1N)."""
    return re.search(rf"\btag-{i}\b", output) is not None


@pytest.fixture()
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the CLI at a fresh file-based SQLite inside tmp_path."""
    path = tmp_path / "pomo.db"
    monkeypatch.setenv("POMO_DB_PATH", str(path))
    return path


def _seed(n: int) -> None:
    """Insert *n* work sessions with strictly increasing ``started_at``."""
    conn = get_connection()
    repo = SessionRepository(conn)
    for i in range(n):
        repo.insert(
            Session(
                id=None,
                started_at=f"2026-04-17T10:{i:02d}:00",
                ended_at=f"2026-04-17T10:{i:02d}:30",
                duration_s=1500,
                kind="work",
                tag=f"tag-{i}",
                completed=True,
            )
        )
    conn.close()


class TestHistoryDefaults:
    """AC: ``pomo history`` shows up to 10 rows (newest first)."""

    def test_caps_at_ten_rows_by_default(self, db_path: Path) -> None:
        _seed(12)

        result = runner.invoke(app, ["history"])

        assert result.exit_code == 0, result.stdout
        # The two oldest tags (tag-0, tag-1) should be excluded; the ten newest present.
        for i in range(2, 12):
            assert _has_tag(result.stdout, i)
        assert not _has_tag(result.stdout, 0)
        assert not _has_tag(result.stdout, 1)

    def test_exact_ten_rows_all_shown(self, db_path: Path) -> None:
        _seed(10)

        result = runner.invoke(app, ["history"])

        assert result.exit_code == 0, result.stdout
        for i in range(10):
            assert _has_tag(result.stdout, i)


class TestHistoryLimit:
    """AC: ``pomo history --limit 3`` shows 3."""

    def test_limit_three(self, db_path: Path) -> None:
        _seed(10)

        result = runner.invoke(app, ["history", "--limit", "3"])

        assert result.exit_code == 0, result.stdout
        # Newest three are tag-9, tag-8, tag-7.
        for i in (7, 8, 9):
            assert _has_tag(result.stdout, i)
        # Anything older should not appear.
        for i in range(0, 7):
            assert not _has_tag(result.stdout, i)

    def test_limit_larger_than_rows_shows_all(self, db_path: Path) -> None:
        _seed(3)

        result = runner.invoke(app, ["history", "--limit", "50"])

        assert result.exit_code == 0, result.stdout
        for i in range(3):
            assert _has_tag(result.stdout, i)

    def test_limit_must_be_positive(self, db_path: Path) -> None:
        _seed(3)

        result = runner.invoke(app, ["history", "--limit", "0"])

        assert result.exit_code != 0


class TestHistoryEmpty:
    """AC: Empty DB prints a helpful 'No sessions yet' message."""

    def test_empty_database_prints_friendly_message(self, db_path: Path) -> None:
        result = runner.invoke(app, ["history"])

        assert result.exit_code == 0, result.stdout
        assert "No sessions yet" in result.stdout


class TestHistoryColumns:
    """The table surfaces started_at, duration, kind, tag, completed."""

    def test_headers_present(self, db_path: Path) -> None:
        _seed(1)

        result = runner.invoke(app, ["history"])

        assert result.exit_code == 0, result.stdout
        lowered = result.stdout.lower()
        assert "started" in lowered
        assert "duration" in lowered
        assert "kind" in lowered
        assert "tag" in lowered
        assert "completed" in lowered
