"""Rich table renderers for the ``pomo`` CLI."""

from __future__ import annotations

from rich.table import Table

from pomo.storage.models import Session


def _format_duration(seconds: int) -> str:
    minutes, secs = divmod(max(seconds, 0), 60)
    return f"{minutes:02d}:{secs:02d}"


def render_history_table(sessions: list[Session]) -> Table:
    """Build a Rich table for ``pomo history``.

    Columns: Started, Duration, Kind, Tag, Completed. Rows appear in the
    order supplied (callers pass newest-first).

    Args:
        sessions: Sessions to render. May be empty; callers should decide
            whether to print an empty table or a friendly message instead.
    """
    table = Table(title="Recent sessions")
    table.add_column("Started", no_wrap=True)
    table.add_column("Duration", justify="right")
    table.add_column("Kind")
    table.add_column("Tag")
    table.add_column("Completed")

    for s in sessions:
        table.add_row(
            s.started_at,
            _format_duration(s.duration_s),
            s.kind,
            s.tag if s.tag is not None else "-",
            "yes" if s.completed else "no",
        )
    return table
