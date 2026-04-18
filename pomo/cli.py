"""Command-line entry point for the Pomodoro timer."""

from __future__ import annotations

import typer
from rich.console import Console

from pomo.storage.db import get_connection
from pomo.storage.repository import SessionRepository
from pomo.ui.tables import render_history_table

app = typer.Typer(
    name="pomo",
    help="Command-line Pomodoro timer with SQLite session logging.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main() -> None:
    """Pomodoro CLI root command.

    Subcommands will be registered here as they are implemented.
    """


@app.command("history")
def history(
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        min=1,
        help="Maximum number of recent sessions to show.",
    ),
) -> None:
    """Show the most recent sessions."""
    conn = get_connection()
    try:
        sessions = SessionRepository(conn).list_recent(limit=limit)
    finally:
        conn.close()

    console = Console()
    if not sessions:
        console.print("No sessions yet. Start one with `pomo start`.")
        return

    console.print(render_history_table(sessions))


if __name__ == "__main__":  # pragma: no cover
    app()
