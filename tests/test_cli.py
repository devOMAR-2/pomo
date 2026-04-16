"""Smoke tests for the ``pomo`` CLI scaffold."""

from __future__ import annotations

from typer.testing import CliRunner

from pomo.cli import app

runner = CliRunner()


def test_cli_help_exits_zero() -> None:
    """`pomo --help` exits 0 and renders the Typer help panel."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "pomo" in result.stdout.lower()


def test_cli_no_args_shows_help() -> None:
    """Invoking with no args shows help (no_args_is_help=True)."""
    result = runner.invoke(app, [])
    # Typer exits 2 when no_args_is_help triggers without a command.
    assert result.exit_code in (0, 2)
    assert "usage" in result.stdout.lower() or "usage" in result.stderr.lower()
