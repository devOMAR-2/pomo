"""Session repository — CRUD and aggregate queries over the sessions table."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from pomo.storage.models import DayAggregate, Session, TagAggregate


class SessionRepository:
    """Thin data-access layer around the ``sessions`` table.

    Args:
        conn: An open SQLite connection (with migrations already applied).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def insert(self, session: Session) -> Session:
        """Persist a new session row and return it with ``id`` populated.

        Args:
            session: A :class:`Session` with ``id=None``.

        Returns:
            A copy of *session* whose ``id`` is now the auto-generated PK.
        """
        cur = self._conn.execute(
            """
            INSERT INTO sessions (started_at, ended_at, duration_s, kind, tag, completed)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session.started_at,
                session.ended_at,
                session.duration_s,
                session.kind,
                session.tag,
                int(session.completed),
            ),
        )
        self._conn.commit()
        return Session(
            id=cur.lastrowid,
            started_at=session.started_at,
            ended_at=session.ended_at,
            duration_s=session.duration_s,
            kind=session.kind,
            tag=session.tag,
            completed=session.completed,
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_recent(self, limit: int = 10) -> list[Session]:
        """Return the *limit* most-recent sessions, newest first.

        Args:
            limit: Maximum number of rows to return.
        """
        rows = self._conn.execute(
            "SELECT id, started_at, ended_at, duration_s, kind, tag, completed "
            "FROM sessions ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def list_between(self, start: str, end: str) -> list[Session]:
        """Return sessions whose ``started_at`` falls in ``[start, end)``.

        Args:
            start: Inclusive lower bound (``YYYY-MM-DD`` or ISO 8601).
            end: Exclusive upper bound.
        """
        rows = self._conn.execute(
            "SELECT id, started_at, ended_at, duration_s, kind, tag, completed "
            "FROM sessions WHERE started_at >= ? AND started_at < ? "
            "ORDER BY started_at",
            (start, end),
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def aggregate_by_day(self, start: str, end: str) -> list[DayAggregate]:
        """Return one row per calendar day in ``[start, end]``, filling gaps with zeros.

        Args:
            start: First date (``YYYY-MM-DD``), inclusive.
            end: Last date (``YYYY-MM-DD``), inclusive.

        Returns:
            A list of :class:`DayAggregate` covering every calendar day in the
            range, including days with no sessions.
        """
        rows = self._conn.execute(
            "SELECT DATE(started_at) AS day, COUNT(*) AS cnt, "
            "SUM(duration_s) / 60 AS mins "
            "FROM sessions "
            "WHERE DATE(started_at) >= ? AND DATE(started_at) <= ? "
            "AND completed = 1 AND kind = 'work' "
            "GROUP BY day ORDER BY day",
            (start, end),
        ).fetchall()

        by_day: dict[str, tuple[int, int]] = {r[0]: (r[1], r[2]) for r in rows}

        result: list[DayAggregate] = []
        current = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        while current <= end_date:
            day_str = current.isoformat()
            count, minutes = by_day.get(day_str, (0, 0))
            result.append(DayAggregate(date=day_str, count=count, total_minutes=minutes))
            current += timedelta(days=1)

        return result

    def aggregate_by_tag(self, start: str, end: str) -> list[TagAggregate]:
        """Return per-tag aggregates for sessions in ``[start, end)``.

        Sessions with a ``NULL`` tag are grouped under ``"untagged"``.

        Args:
            start: Inclusive lower bound (``YYYY-MM-DD`` or ISO 8601).
            end: Exclusive upper bound.
        """
        rows = self._conn.execute(
            "SELECT COALESCE(tag, 'untagged') AS t, COUNT(*) AS cnt, "
            "SUM(duration_s) / 60 AS mins "
            "FROM sessions "
            "WHERE started_at >= ? AND started_at < ? "
            "AND completed = 1 AND kind = 'work' "
            "GROUP BY t ORDER BY cnt DESC",
            (start, end),
        ).fetchall()
        return [TagAggregate(tag=r[0], count=r[1], total_minutes=r[2]) for r in rows]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_session(row: tuple[object, ...]) -> Session:
        id_val: int = row[0]  # type: ignore[assignment]
        dur_val: int = row[3]  # type: ignore[assignment]
        return Session(
            id=id_val,
            started_at=str(row[1]),
            ended_at=str(row[2]),
            duration_s=dur_val,
            kind=str(row[4]),
            tag=str(row[5]) if row[5] is not None else None,
            completed=bool(row[6]),
        )
