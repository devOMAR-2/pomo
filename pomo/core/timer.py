"""Pomodoro timer state machine.

The :class:`Timer` drives the Pomodoro cycle (``idle → work → short_break →
work → … → long_break``) on top of an injected :class:`~pomo.core.clock.Clock`.
It emits events through optional callbacks so the UI can subscribe without
being coupled to the timing logic.

Time is advanced by the caller: the driver (a CLI loop or a test) keeps
calling :meth:`Timer.tick`, and the timer decides whether the current
interval has ended, fires the appropriate events, and transitions to the
next state. This keeps the whole module pure and unit-testable with a
:class:`~pomo.core.clock.FakeClock`.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from pomo.core.clock import Clock
from pomo.core.config import Config


class State(str, Enum):
    """Discrete states the timer can be in.

    The three "interval" states — ``WORK``, ``SHORT_BREAK``, ``LONG_BREAK`` —
    are the only ones that consume time. ``PAUSED`` remembers the interval
    it was paused from so :meth:`Timer.resume` can restore it.
    """

    IDLE = "idle"
    WORK = "work"
    SHORT_BREAK = "short_break"
    LONG_BREAK = "long_break"
    PAUSED = "paused"
    ABORTED = "aborted"


OnTick = Callable[[State, int], None]
"""``(state, remaining_seconds)`` — fired once per :meth:`Timer.tick` while running."""

OnTransition = Callable[[State, State], None]
"""``(from_state, to_state)`` — fired every time the state changes."""

OnComplete = Callable[[State], None]
"""``(interval_state)`` — fired when an interval ends naturally (not aborted)."""

OnAbort = Callable[[State], None]
"""``(interval_state)`` — fired when :meth:`Timer.abort` is called mid-interval."""


_INTERVAL_STATES: frozenset[State] = frozenset({State.WORK, State.SHORT_BREAK, State.LONG_BREAK})


class Timer:
    """Pomodoro state machine driven by a caller-supplied :class:`Clock`.

    Args:
        config: Resolved :class:`Config` providing interval durations and
            the cycles-between-long-breaks cadence.
        clock: Time source. Production code passes
            :class:`~pomo.core.clock.SystemClock`; tests pass
            :class:`~pomo.core.clock.FakeClock`.
        on_tick: Invoked with ``(state, remaining_seconds)`` at the end of
            every :meth:`tick` call where the timer is in an interval state.
        on_transition: Invoked with ``(from, to)`` whenever the state
            changes, including pause/resume and abort.
        on_complete: Invoked with the just-finished interval's state when
            an interval ends naturally. Not invoked on :meth:`abort`.
        on_abort: Invoked with the state the timer was aborted *from*.
    """

    def __init__(
        self,
        config: Config,
        clock: Clock,
        *,
        on_tick: OnTick | None = None,
        on_transition: OnTransition | None = None,
        on_complete: OnComplete | None = None,
        on_abort: OnAbort | None = None,
    ) -> None:
        self._config = config
        self._clock = clock
        self._on_tick = on_tick
        self._on_transition = on_transition
        self._on_complete = on_complete
        self._on_abort = on_abort

        self._state: State = State.IDLE
        self._paused_from: State | None = None
        self._interval_end_at: float = 0.0
        self._pause_started_at: float = 0.0
        self._work_cycles_completed: int = 0

    # ------------------------------------------------------------------
    # Public read-only view
    # ------------------------------------------------------------------

    @property
    def state(self) -> State:
        return self._state

    @property
    def remaining_seconds(self) -> int:
        """Seconds left in the current interval.

        Returns ``0`` when not in an interval (or when paused, returns the
        frozen remainder captured at pause time).
        """
        if self._state in _INTERVAL_STATES:
            return max(0, int(round(self._interval_end_at - self._clock.now())))
        if self._state is State.PAUSED:
            return max(0, int(round(self._interval_end_at - self._pause_started_at)))
        return 0

    @property
    def work_cycles_completed(self) -> int:
        return self._work_cycles_completed

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Begin the first work interval. Only valid from :attr:`State.IDLE`."""
        if self._state is not State.IDLE:
            raise RuntimeError(f"start() requires IDLE state, got {self._state.value}")
        self._begin_interval(State.WORK)

    def tick(self) -> None:
        """Advance the state machine based on the current clock reading.

        Idempotent and cheap. In an interval state, may fire at most one
        ``on_complete`` + ``on_transition`` pair per elapsed interval
        (repeated if the caller advanced across several intervals at once).
        Always ends by emitting ``on_tick`` if still in an interval.
        """
        if self._state not in _INTERVAL_STATES:
            return

        # Consume every interval whose deadline has already passed. In the
        # common case (driver ticks at ~1 Hz) the loop runs zero times; it
        # only iterates when a test advances across multiple intervals.
        while self._state in _INTERVAL_STATES and self._clock.now() >= self._interval_end_at:
            finished = self._state
            if finished is State.WORK:
                self._work_cycles_completed += 1
            if self._on_complete is not None:
                self._on_complete(finished)
            self._begin_interval(self._next_state_after(finished))

        if self._on_tick is not None and self._state in _INTERVAL_STATES:
            self._on_tick(self._state, self.remaining_seconds)

    def pause(self) -> None:
        """Freeze the current interval. Only valid while running."""
        if self._state not in _INTERVAL_STATES:
            raise RuntimeError(f"pause() requires a running interval, got {self._state.value}")
        self._paused_from = self._state
        self._pause_started_at = self._clock.now()
        self._transition_to(State.PAUSED)

    def resume(self) -> None:
        """Return to the interval paused by :meth:`pause` with its clock shifted forward."""
        if self._state is not State.PAUSED:
            raise RuntimeError(f"resume() requires PAUSED state, got {self._state.value}")
        assert self._paused_from is not None  # set whenever state == PAUSED
        paused_duration = self._clock.now() - self._pause_started_at
        self._interval_end_at += paused_duration
        target = self._paused_from
        self._paused_from = None
        self._transition_to(target)

    def abort(self) -> None:
        """Cancel the current run. Fires ``on_abort`` with the pre-abort state."""
        if self._state is State.IDLE or self._state is State.ABORTED:
            raise RuntimeError(f"abort() not valid from {self._state.value}")
        if self._state is State.PAUSED:
            assert self._paused_from is not None  # invariant while PAUSED
            aborted_from = self._paused_from
        else:
            aborted_from = self._state
        if self._on_abort is not None:
            self._on_abort(aborted_from)
        self._paused_from = None
        self._transition_to(State.ABORTED)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _begin_interval(self, new_state: State) -> None:
        duration = self._duration_for(new_state)
        self._interval_end_at = self._clock.now() + duration
        self._transition_to(new_state)

    def _duration_for(self, state: State) -> int:
        if state is State.WORK:
            return self._config.work_min * 60
        if state is State.SHORT_BREAK:
            return self._config.short_break_min * 60
        if state is State.LONG_BREAK:
            return self._config.long_break_min * 60
        raise ValueError(f"no duration defined for {state.value}")

    def _next_state_after(self, finished: State) -> State:
        if finished is State.WORK:
            if self._work_cycles_completed % self._config.cycles_before_long_break == 0:
                return State.LONG_BREAK
            return State.SHORT_BREAK
        return State.WORK

    def _transition_to(self, new_state: State) -> None:
        previous = self._state
        self._state = new_state
        if self._on_transition is not None:
            self._on_transition(previous, new_state)
