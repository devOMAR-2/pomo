"""Tests for the ``pomo stats`` CLI command."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pomo.cli import app
from pomo.storage.db import get_connection
from pomo.storage.models import Session
from pomo.storage.repository import SessionRepository

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


@pytest.fixture()
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "pomo.db"
    monkeypatch.setenv("POMO_DB_PATH", str(path))
    return path


def _iso(day: date, hour: int, minute: int = 0) -> str:
    return datetime(day.year, day.month, day.day, hour, minute, 0).isoformat()


def _insert(
    repo: SessionRepository,
    *,
    day: date,
    hour: int,
    duration_s: int,
    kind: str,
    tag: str | None,
    completed: bool = True,
) -> None:
    repo.insert(
        Session(
            id=None,
            started_at=_iso(day, hour),
            ended_at=_iso(day, hour + (duration_s // 3600), (duration_s % 3600) // 60),
            duration_s=duration_s,
            kind=kind,
            tag=tag,
            completed=completed,
        )
    )


class TestStatsToday:
    """AC: `pomo stats` reports correct totals after seeding fixtures."""

    def test_today_totals_count_only_completed_work(self, db_path: Path) -> None:
        today = date.today()
        conn = get_connection()
        repo = SessionRepository(conn)
        _insert(repo, day=today, hour=9, duration_s=1500, kind="work", tag="writing")
        _insert(repo, day=today, hour=10, duration_s=1500, kind="work", tag="writing")
        _insert(repo, day=today, hour=11, duration_s=1800, kind="work", tag="research")
        _insert(repo, day=today, hour=12, duration_s=300, kind="short_break", tag=None)
        _insert(
            repo,
            day=today,
            hour=13,
            duration_s=1500,
            kind="work",
            tag="ignored",
            completed=False,
        )
        conn.close()

        result = runner.invoke(app, ["stats"])

        assert result.exit_code == 0, result.stdout
        out = _strip_ansi(result.stdout)
        # 3 completed work sessions today (1500 + 1500 + 1800 = 4800 s = 80 min).
        assert "3" in out
        assert "80" in out
        # Per-tag breakdown should list both tags seen in completed work today.
        assert "writing" in out
        assert "research" in out
        # Aborted and non-work rows must not be counted in the tag table.
        assert "ignored" not in out

    def test_empty_database_still_exits_cleanly(self, db_path: Path) -> None:
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0, result.stdout

    def test_yesterdays_sessions_do_not_affect_today(self, db_path: Path) -> None:
        today = date.today()
        yesterday = today - timedelta(days=1)
        conn = get_connection()
        repo = SessionRepository(conn)
        _insert(repo, day=yesterday, hour=9, duration_s=1500, kind="work", tag="old")
        _insert(repo, day=today, hour=9, duration_s=1500, kind="work", tag="new")
        conn.close()

        result = runner.invoke(app, ["stats"])

        assert result.exit_code == 0, result.stdout
        out = _strip_ansi(result.stdout)
        assert "new" in out
        assert "old" not in out


class TestStatsWeek:
    """AC: `--week` shows 7 bars even when some days have no data."""

    def test_week_shows_seven_rows_even_with_sparse_data(self, db_path: Path) -> None:
        today = date.today()
        conn = get_connection()
        repo = SessionRepository(conn)
        # Seed only two of the last seven days.
        _insert(repo, day=today, hour=9, duration_s=1500, kind="work", tag="a")
        _insert(repo, day=today - timedelta(days=3), hour=9, duration_s=1500, kind="work", tag="b")
        conn.close()

        result = runner.invoke(app, ["stats", "--week"])

        assert result.exit_code == 0, result.stdout
        out = _strip_ansi(result.stdout)

        # Every one of the last 7 calendar dates must appear in the output.
        for i in range(7):
            d = (today - timedelta(days=i)).isoformat()
            assert d in out, f"week chart missing date {d}"


class TestStatsCli:
    """AC: CliRunner test asserts exit 0 and expected column headers."""

    def test_headers_present_without_week(self, db_path: Path) -> None:
        today = date.today()
        conn = get_connection()
        repo = SessionRepository(conn)
        _insert(repo, day=today, hour=9, duration_s=1500, kind="work", tag="focus")
        conn.close()

        result = runner.invoke(app, ["stats"])

        assert result.exit_code == 0, result.stdout
        lowered = _strip_ansi(result.stdout).lower()
        # Today summary table headers.
        assert "work" in lowered or "sessions" in lowered
        assert "focus" in lowered or "minutes" in lowered
        # Per-tag breakdown headers.
        assert "tag" in lowered

    def test_headers_present_with_week(self, db_path: Path) -> None:
        today = date.today()
        conn = get_connection()
        repo = SessionRepository(conn)
        _insert(repo, day=today, hour=9, duration_s=1500, kind="work", tag="focus")
        conn.close()

        result = runner.invoke(app, ["stats", "--week"])

        assert result.exit_code == 0, result.stdout
        lowered = _strip_ansi(result.stdout).lower()
        # Week chart header row.
        assert "date" in lowered
        # Bar glyph present for the day(s) with data.
        assert "█" in result.stdout or "bar" in lowered
