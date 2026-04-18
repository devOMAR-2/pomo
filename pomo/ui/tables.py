"""Rich table renderers for the ``pomo`` CLI."""

from __future__ import annotations

from rich.table import Table

from pomo.storage.models import DayAggregate, Session, TagAggregate


def _format_duration(seconds: int) -> str:
    minutes, secs = divmod(max(seconds, 0), 60)
    return f"{minutes:02d}:{secs:02d}"


def render_today_summary(*, day: str, work_count: int, focus_minutes: int) -> Table:
    """One-row summary table for today's completed work: sessions + minutes."""
    table = Table(title=f"Today ({day})")
    table.add_column("Date", no_wrap=True)
    table.add_column("Work sessions", justify="right")
    table.add_column("Focus minutes", justify="right")
    table.add_row(day, str(work_count), str(focus_minutes))
    return table


def render_tag_breakdown(aggregates: list[TagAggregate]) -> Table:
    """Per-tag table showing session count and total minutes, highest first."""
    table = Table(title="By tag")
    table.add_column("Tag")
    table.add_column("Sessions", justify="right")
    table.add_column("Minutes", justify="right")
    for a in aggregates:
        table.add_row(a.tag, str(a.count), str(a.total_minutes))
    return table


def render_week_bars(aggregates: list[DayAggregate]) -> Table:
    """Seven-row ASCII bar chart: one row per calendar day in the window.

    Callers should pass a list covering every day in the window (gaps
    filled with zeros) — :meth:`SessionRepository.aggregate_by_day` already
    does this. Each bar is one ``█`` per completed work session, capped at
    40 columns.
    """
    max_count = max((a.count for a in aggregates), default=0)
    bar_width = 40
    table = Table(title="Last 7 days")
    table.add_column("Date", no_wrap=True)
    table.add_column("Work", justify="right")
    table.add_column("Bar")
    for a in aggregates:
        if max_count == 0:
            bar = ""
        else:
            filled = round(a.count / max_count * bar_width)
            bar = "█" * filled
        table.add_row(a.date, str(a.count), bar)
    return table


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
