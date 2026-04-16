"""Tests for pomo.storage.repository — SessionRepository CRUD and aggregates."""

from __future__ import annotations

import sqlite3

import pytest

from pomo.storage.db import get_connection
from pomo.storage.models import Session
from pomo.storage.repository import SessionRepository


@pytest.fixture(autouse=True)
def _use_memory_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POMO_DB_PATH", ":memory:")


@pytest.fixture()
def conn() -> sqlite3.Connection:
    return get_connection()


@pytest.fixture()
def repo(conn: sqlite3.Connection) -> SessionRepository:
    return SessionRepository(conn)


def _make_session(
    *,
    started_at: str = "2026-04-17T10:00:00",
    ended_at: str = "2026-04-17T10:25:00",
    duration_s: int = 1500,
    kind: str = "work",
    tag: str | None = "test-tag",
    completed: bool = True,
) -> Session:
    return Session(
        id=None,
        started_at=started_at,
        ended_at=ended_at,
        duration_s=duration_s,
        kind=kind,
        tag=tag,
        completed=completed,
    )


class TestInsertAndListRecent:
    """AC: Round-trip test — insert → list_recent returns the same session."""

    def test_round_trip(self, repo: SessionRepository) -> None:
        original = _make_session()
        inserted = repo.insert(original)
        assert inserted.id is not None

        recent = repo.list_recent(limit=1)
        assert len(recent) == 1
        got = recent[0]
        assert got.id == inserted.id
        assert got.started_at == original.started_at
        assert got.ended_at == original.ended_at
        assert got.duration_s == original.duration_s
        assert got.kind == original.kind
        assert got.tag == original.tag
        assert got.completed == original.completed

    def test_insert_returns_session_with_id(self, repo: SessionRepository) -> None:
        session = _make_session()
        result = repo.insert(session)
        assert result.id is not None
        assert result.id > 0

    def test_list_recent_respects_limit(self, repo: SessionRepository) -> None:
        for i in range(5):
            repo.insert(_make_session(started_at=f"2026-04-17T{10 + i}:00:00"))
        assert len(repo.list_recent(limit=3)) == 3

    def test_list_recent_ordered_newest_first(self, repo: SessionRepository) -> None:
        repo.insert(_make_session(started_at="2026-04-17T09:00:00"))
        repo.insert(_make_session(started_at="2026-04-17T11:00:00"))
        recent = repo.list_recent(limit=2)
        assert recent[0].started_at > recent[1].started_at


class TestListBetween:
    def test_returns_sessions_in_range(self, repo: SessionRepository) -> None:
        repo.insert(_make_session(started_at="2026-04-16T10:00:00"))
        repo.insert(_make_session(started_at="2026-04-17T10:00:00"))
        repo.insert(_make_session(started_at="2026-04-18T10:00:00"))

        results = repo.list_between("2026-04-17", "2026-04-18")
        assert len(results) == 1
        assert results[0].started_at.startswith("2026-04-17")

    def test_empty_range(self, repo: SessionRepository) -> None:
        repo.insert(_make_session(started_at="2026-04-17T10:00:00"))
        results = repo.list_between("2026-04-20", "2026-04-21")
        assert results == []


class TestAggregateByDay:
    """AC: aggregate_by_day returns one row per day with zeros for missing days."""

    def test_fills_missing_days_with_zeros(self, repo: SessionRepository) -> None:
        repo.insert(
            _make_session(
                started_at="2026-04-14T10:00:00",
                duration_s=1500,
            )
        )
        repo.insert(
            _make_session(
                started_at="2026-04-17T10:00:00",
                duration_s=1500,
            )
        )

        rows = repo.aggregate_by_day("2026-04-14", "2026-04-17")
        assert len(rows) == 4  # 14, 15, 16, 17
        dates = [r.date for r in rows]
        assert dates == ["2026-04-14", "2026-04-15", "2026-04-16", "2026-04-17"]

        # Days with no sessions have zero counts
        assert rows[1].count == 0
        assert rows[1].total_minutes == 0
        assert rows[2].count == 0

        # Days with sessions have real data
        assert rows[0].count == 1
        assert rows[0].total_minutes == 25
        assert rows[3].count == 1

    def test_multiple_sessions_same_day(self, repo: SessionRepository) -> None:
        repo.insert(_make_session(started_at="2026-04-17T09:00:00", duration_s=1500))
        repo.insert(_make_session(started_at="2026-04-17T10:00:00", duration_s=1500))

        rows = repo.aggregate_by_day("2026-04-17", "2026-04-17")
        assert len(rows) == 1
        assert rows[0].count == 2
        assert rows[0].total_minutes == 50


class TestAggregateByTag:
    """AC: aggregate_by_tag handles NULL tag (grouped as 'untagged')."""

    def test_null_tag_grouped_as_untagged(self, repo: SessionRepository) -> None:
        repo.insert(_make_session(tag=None, duration_s=1500))
        repo.insert(_make_session(tag=None, duration_s=1500))
        repo.insert(_make_session(tag="focus", duration_s=1500))

        rows = repo.aggregate_by_tag("2026-04-17", "2026-04-18")
        by_tag = {r.tag: r for r in rows}
        assert "untagged" in by_tag
        assert by_tag["untagged"].count == 2
        assert by_tag["focus"].count == 1

    def test_all_tagged(self, repo: SessionRepository) -> None:
        repo.insert(_make_session(tag="a", duration_s=600))
        repo.insert(_make_session(tag="b", duration_s=1200))

        rows = repo.aggregate_by_tag("2026-04-17", "2026-04-18")
        tags = {r.tag for r in rows}
        assert tags == {"a", "b"}

    def test_empty_range(self, repo: SessionRepository) -> None:
        rows = repo.aggregate_by_tag("2026-04-17", "2026-04-18")
        assert rows == []
