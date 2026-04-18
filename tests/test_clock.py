"""Tests for pomo.core.clock — injectable clock abstraction."""

from __future__ import annotations

import time

import pytest


class TestFakeClockAdvance:
    """AC: ``FakeClock.advance(10)`` advances ``now()`` by exactly 10 seconds."""

    def test_advance_by_ten_moves_now_by_exactly_ten(self) -> None:
        from pomo.core.clock import FakeClock

        clock = FakeClock(start=0.0)
        before = clock.now()
        clock.advance(10)
        after = clock.now()
        assert after - before == 10.0

    def test_advance_is_additive(self) -> None:
        from pomo.core.clock import FakeClock

        clock = FakeClock(start=100.0)
        clock.advance(2.5)
        clock.advance(7.5)
        assert clock.now() == 110.0

    def test_advance_accepts_float_seconds(self) -> None:
        from pomo.core.clock import FakeClock

        clock = FakeClock(start=0.0)
        clock.advance(0.25)
        assert clock.now() == pytest.approx(0.25)

    def test_advance_rejects_negative(self) -> None:
        from pomo.core.clock import FakeClock

        clock = FakeClock(start=0.0)
        with pytest.raises(ValueError):
            clock.advance(-1)

    def test_default_start_is_zero(self) -> None:
        from pomo.core.clock import FakeClock

        assert FakeClock().now() == 0.0

    def test_now_is_stable_without_advance(self) -> None:
        from pomo.core.clock import FakeClock

        clock = FakeClock(start=42.0)
        assert clock.now() == 42.0
        assert clock.now() == 42.0


class TestFakeClockSleep:
    """AC: ``FakeClock.sleep(n)`` is a no-op that records calls."""

    def test_sleep_does_not_block(self) -> None:
        from pomo.core.clock import FakeClock

        clock = FakeClock()
        wall_before = time.monotonic()
        clock.sleep(5)
        wall_after = time.monotonic()
        assert wall_after - wall_before < 0.1

    def test_sleep_does_not_advance_now_by_itself(self) -> None:
        from pomo.core.clock import FakeClock

        clock = FakeClock(start=0.0)
        clock.sleep(30)
        assert clock.now() == 0.0

    def test_sleep_records_each_call_in_order(self) -> None:
        from pomo.core.clock import FakeClock

        clock = FakeClock()
        clock.sleep(1)
        clock.sleep(2.5)
        clock.sleep(0)
        assert clock.sleep_calls == [1, 2.5, 0]

    def test_sleep_calls_is_empty_by_default(self) -> None:
        from pomo.core.clock import FakeClock

        assert FakeClock().sleep_calls == []

    def test_sleep_calls_is_isolated_per_instance(self) -> None:
        from pomo.core.clock import FakeClock

        a = FakeClock()
        b = FakeClock()
        a.sleep(1)
        assert b.sleep_calls == []


class TestClockProtocol:
    """The public ``Clock`` protocol is satisfied by both implementations."""

    def test_system_clock_satisfies_protocol(self) -> None:
        from pomo.core.clock import Clock, SystemClock

        clock: Clock = SystemClock()
        assert callable(clock.now)
        assert callable(clock.sleep)

    def test_fake_clock_satisfies_protocol(self) -> None:
        from pomo.core.clock import Clock, FakeClock

        clock: Clock = FakeClock()
        assert callable(clock.now)
        assert callable(clock.sleep)


class TestSystemClock:
    """The real clock wraps ``time.monotonic`` / ``time.sleep`` honestly."""

    def test_now_returns_float(self) -> None:
        from pomo.core.clock import SystemClock

        assert isinstance(SystemClock().now(), float)

    def test_now_is_monotonic_non_decreasing(self) -> None:
        from pomo.core.clock import SystemClock

        clock = SystemClock()
        a = clock.now()
        b = clock.now()
        assert b >= a

    def test_sleep_delegates_to_time_sleep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pomo.core import clock as clock_module
        from pomo.core.clock import SystemClock

        calls: list[float] = []
        monkeypatch.setattr(clock_module.time, "sleep", lambda s: calls.append(s))

        SystemClock().sleep(0.01)
        assert calls == [0.01]
