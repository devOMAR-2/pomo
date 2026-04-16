"""Command-line entry point for the Pomodoro timer."""

from __future__ import annotations

import typer

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


if __name__ == "__main__":  # pragma: no cover
    app()
