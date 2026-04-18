"""Tests for the ``pomo start`` CLI command."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from pomo.cli import app, run_pomo_loop
from pomo.core.clock import FakeClock
from pomo.core.config import Config
from pomo.storage.db import get_connection
from pomo.storage.repository import SessionRepository

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def _strip_ansi(s: str) -> str:
    """Remove ANSI SGR/CSI sequences Rich injects into Typer's --help output."""
    return _ANSI_RE.sub("", s)


# --------------------------------------------------------------------------
# Shared fakes
# --------------------------------------------------------------------------


class AdvancingFakeClock(FakeClock):
    """Test clock whose ``sleep`` also advances ``now``."""

    def sleep(self, seconds: float) -> None:
        super().sleep(seconds)
        self.advance(seconds)


class InterruptingClock(FakeClock):
    """Raises ``KeyboardInterrupt`` on the first N calls to ``sleep``."""

    def __init__(self, *, interrupts: int = 2) -> None:
        super().__init__()
        self._interrupts_remaining = interrupts

    def sleep(self, seconds: float) -> None:
        super().sleep(seconds)
        if self._interrupts_remaining > 0:
            self._interrupts_remaining -= 1
            raise KeyboardInterrupt
        self.advance(seconds)


def _advancing_now(clock: FakeClock) -> callable:
    """Return a now_fn that tracks ``clock.now`` but returns datetimes."""
    origin = datetime(2026, 4, 17, 10, 0, 0)
    return lambda: origin + timedelta(seconds=clock.now())


def _silent_console() -> Console:
    """Non-TTY console that swallows output so tests don't spam stdout."""
    return Console(file=StringIO(), force_terminal=False, width=80)


def _cfg(
    *,
    work_min: int = 1,
    short_break_min: int = 1,
    long_break_min: int = 1,
    cycles_before_long_break: int = 4,
    sound: bool = False,
) -> Config:
    return Config(
        work_min=work_min,
        short_break_min=short_break_min,
        long_break_min=long_break_min,
        cycles_before_long_break=cycles_before_long_break,
        sound=sound,
    )


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SessionRepository:
    monkeypatch.setenv("POMO_DB_PATH", str(tmp_path / "pomo.db"))
    return SessionRepository(get_connection())


# --------------------------------------------------------------------------
# AC: flag parsing
# --------------------------------------------------------------------------


class TestFlagParsing:
    def test_help_mentions_all_documented_flags(self) -> None:
        # Typer renders --help via Rich, which injects ANSI SGR codes and
        # wraps at the terminal width. Force a wide no-color terminal so
        # flag names don't get hyphenated across lines, and strip any
        # remaining escapes before asserting.
        result = runner.invoke(
            app,
            ["start", "--help"],
            color=False,
            env={"COLUMNS": "200", "NO_COLOR": "1", "TERM": "dumb"},
        )
        assert result.exit_code == 0, result.stdout
        cleaned = _strip_ansi(result.stdout)
        for flag in ("--work", "--break", "--long-break", "--cycles", "--tag", "--no-sound"):
            assert flag in cleaned, f"--help is missing {flag}"

    def test_invalid_work_value_rejected(self) -> None:
        # Non-positive --work should be rejected by Typer's min constraint.
        result = runner.invoke(app, ["start", "--work", "0"])
        assert result.exit_code != 0


# --------------------------------------------------------------------------
# AC: --cycles 1 --work 1 --break 1 --tag test persists exactly 2 rows
# --------------------------------------------------------------------------


class TestFullCycleRun:
    def test_single_cycle_persists_one_work_and_one_short_break(
        self,
        repo: SessionRepository,
    ) -> None:
        clock = AdvancingFakeClock()
        exit_code = run_pomo_loop(
            config=_cfg(work_min=1, short_break_min=1),
            clock=clock,
            cycles=1,
            tag="test",
            repo=repo,
            console=_silent_console(),
            poll_interval=1.0,  # 60 iterations per minute — fast
            now_fn=_advancing_now(clock),
        )

        assert exit_code == 0
        rows = repo.list_recent(limit=10)
        kinds = sorted(r.kind for r in rows)
        assert kinds == ["short_break", "work"]
        assert all(r.tag == "test" for r in rows)
        assert all(r.completed for r in rows)
        # Each interval is 60 s in wall time.
        for r in rows:
            assert r.duration_s == 60

    def test_two_cycles_persists_two_works_and_two_breaks(
        self,
        repo: SessionRepository,
    ) -> None:
        clock = AdvancingFakeClock()
        exit_code = run_pomo_loop(
            config=_cfg(work_min=1, short_break_min=1),
            clock=clock,
            cycles=2,
            tag=None,
            repo=repo,
            console=_silent_console(),
            poll_interval=1.0,
            now_fn=_advancing_now(clock),
        )

        assert exit_code == 0
        rows = repo.list_recent(limit=10)
        assert len(rows) == 4
        assert [r.kind for r in rows].count("work") == 2
        assert [r.kind for r in rows].count("short_break") == 2


# --------------------------------------------------------------------------
# AC: two Ctrl+C leaves DB untouched
# --------------------------------------------------------------------------


class TestAbort:
    def test_two_keyboard_interrupts_during_first_interval_persists_nothing(
        self,
        repo: SessionRepository,
    ) -> None:
        clock = InterruptingClock(interrupts=2)
        exit_code = run_pomo_loop(
            config=_cfg(work_min=25, short_break_min=5),
            clock=clock,
            cycles=1,
            tag="aborted",
            repo=repo,
            console=_silent_console(),
            poll_interval=1.0,
            now_fn=_advancing_now(clock),
        )

        assert exit_code == 130  # SIGINT convention
        assert repo.list_recent(limit=10) == []

    def test_first_interrupt_pauses_then_second_aborts(
        self,
        repo: SessionRepository,
    ) -> None:
        clock = InterruptingClock(interrupts=2)
        exit_code = run_pomo_loop(
            config=_cfg(work_min=25, short_break_min=5),
            clock=clock,
            cycles=1,
            tag=None,
            repo=repo,
            console=_silent_console(),
            poll_interval=1.0,
            now_fn=_advancing_now(clock),
        )

        # After abort, no partial session row should exist.
        assert exit_code == 130
        assert repo.list_recent() == []
