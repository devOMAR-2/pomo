"""Injectable clock abstraction for deterministic, testable timing.

The timer core depends on this ``Clock`` protocol rather than calling
``time.monotonic`` / ``time.sleep`` directly. Production code wires in a
:class:`SystemClock`; tests wire in a :class:`FakeClock` and advance time
explicitly, avoiding real sleeps in the test suite.
"""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """A minimal clock: a source of "now" and a sleep primitive.

    ``now()`` is intended for measuring elapsed durations, not wall-clock
    time, so implementations should be monotonic and non-decreasing.
    """

    def now(self) -> float:
        """Return the current monotonic time, in seconds."""
        ...

    def sleep(self, seconds: float) -> None:
        """Block for approximately ``seconds`` seconds."""
        ...


class SystemClock:
    """Real clock backed by :func:`time.monotonic` and :func:`time.sleep`."""

    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class FakeClock:
    """Deterministic clock for tests.

    ``now()`` only changes when :meth:`advance` is called. ``sleep()`` does
    not block and does not advance time on its own; it only records the
    requested duration in :attr:`sleep_calls` so tests can assert on the
    sequence of sleeps a timer requested.

    Args:
        start: Initial value returned by :meth:`now`. Defaults to ``0.0``.
    """

    def __init__(self, start: float = 0.0) -> None:
        self._now: float = float(start)
        self.sleep_calls: list[float] = []

    def now(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)

    def advance(self, seconds: float) -> None:
        """Move :meth:`now` forward by ``seconds``.

        Raises:
            ValueError: If ``seconds`` is negative. Time does not run backwards.
        """
        if seconds < 0:
            raise ValueError(f"advance() requires non-negative seconds, got {seconds!r}")
        self._now += float(seconds)
