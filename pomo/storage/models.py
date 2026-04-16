"""Domain models for the storage layer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Session:
    """A single Pomodoro interval (work, short break, or long break).

    Args:
        id: Database primary key.  ``None`` before the row is inserted.
        started_at: ISO 8601 timestamp when the interval began.
        ended_at: ISO 8601 timestamp when the interval ended.
        duration_s: Elapsed seconds.
        kind: One of ``"work"``, ``"short_break"``, ``"long_break"``.
        tag: Optional user-supplied label.
        completed: Whether the interval finished naturally (vs. aborted).
    """

    id: int | None
    started_at: str
    ended_at: str
    duration_s: int
    kind: str
    tag: str | None
    completed: bool


@dataclass
class DayAggregate:
    """One row of the per-day aggregation query.

    Args:
        date: ``YYYY-MM-DD`` string.
        count: Number of completed work sessions.
        total_minutes: Sum of ``duration_s / 60``, rounded down.
    """

    date: str
    count: int
    total_minutes: int


@dataclass
class TagAggregate:
    """One row of the per-tag aggregation query.

    Args:
        tag: Tag label (``"untagged"`` for sessions with no tag).
        count: Number of completed work sessions.
        total_minutes: Sum of ``duration_s / 60``, rounded down.
    """

    tag: str
    count: int
    total_minutes: int
