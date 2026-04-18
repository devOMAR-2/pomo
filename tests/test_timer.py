"""Tests for pomo.core.timer — Pomodoro state machine.

All time-dependent behaviour is driven by :class:`FakeClock`. There are no
real sleeps anywhere in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from pomo.core.clock import FakeClock
from pomo.core.config import Config
from pomo.core.timer import State, Timer

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


@dataclass
class EventRecorder:
    """Collect the callback events a timer emits, in order."""

    ticks: list[tuple[State, int]] = field(default_factory=list)
    transitions: list[tuple[State, State]] = field(default_factory=list)
    completes: list[State] = field(default_factory=list)
    aborts: list[State] = field(default_factory=list)

    def install(self, timer_kwargs: dict[str, Any]) -> dict[str, Any]:
        timer_kwargs["on_tick"] = lambda s, r: self.ticks.append((s, r))
        timer_kwargs["on_transition"] = lambda f, t: self.transitions.append((f, t))
        timer_kwargs["on_complete"] = lambda s: self.completes.append(s)
        timer_kwargs["on_abort"] = lambda s: self.aborts.append(s)
        return timer_kwargs


def _cfg(
    *,
    work_min: int = 25,
    short_break_min: int = 5,
    long_break_min: int = 15,
    cycles_before_long_break: int = 4,
) -> Config:
    return Config(
        work_min=work_min,
        short_break_min=short_break_min,
        long_break_min=long_break_min,
        cycles_before_long_break=cycles_before_long_break,
        sound=False,
    )


def _make_timer(
    *,
    config: Config | None = None,
    clock: FakeClock | None = None,
    recorder: EventRecorder | None = None,
) -> tuple[Timer, FakeClock, EventRecorder]:
    clock = clock or FakeClock(start=0.0)
    recorder = recorder or EventRecorder()
    kwargs: dict[str, Any] = {}
    recorder.install(kwargs)
    timer = Timer(config=config or _cfg(), clock=clock, **kwargs)
    return timer, clock, recorder


# --------------------------------------------------------------------------
# AC: single work cycle
# --------------------------------------------------------------------------


class TestSingleWorkCycle:
    """AC: single work cycle completes cleanly and transitions to a break."""

    def test_start_moves_idle_to_work_and_emits_transition(self) -> None:
        timer, _clock, rec = _make_timer()

        timer.start()

        assert timer.state is State.WORK
        assert rec.transitions == [(State.IDLE, State.WORK)]
        assert rec.completes == []
        assert rec.aborts == []

    def test_remaining_counts_down_with_elapsed_time(self) -> None:
        timer, clock, _rec = _make_timer(config=_cfg(work_min=25))
        timer.start()

        assert timer.remaining_seconds == 25 * 60

        clock.advance(60)
        assert timer.remaining_seconds == 24 * 60

    def test_tick_before_completion_emits_on_tick_not_on_complete(self) -> None:
        timer, clock, rec = _make_timer(config=_cfg(work_min=25))
        timer.start()

        clock.advance(60)
        timer.tick()

        assert rec.ticks == [(State.WORK, 24 * 60)]
        assert rec.completes == []

    def test_work_completes_after_exact_duration_and_transitions_to_short_break(self) -> None:
        timer, clock, rec = _make_timer(
            config=_cfg(work_min=25, short_break_min=5, cycles_before_long_break=4)
        )
        timer.start()

        clock.advance(25 * 60)
        timer.tick()

        assert rec.completes == [State.WORK]
        assert timer.state is State.SHORT_BREAK
        # First transition: IDLE→WORK, second: WORK→SHORT_BREAK.
        assert rec.transitions[-1] == (State.WORK, State.SHORT_BREAK)
        assert timer.remaining_seconds == 5 * 60


# --------------------------------------------------------------------------
# AC: full 4-work → long break cycle
# --------------------------------------------------------------------------


class TestFullCycleToLongBreak:
    """AC: 4 work intervals in, a long break follows (not a short one)."""

    def test_fourth_work_completion_transitions_to_long_break(self) -> None:
        cfg = _cfg(
            work_min=25,
            short_break_min=5,
            long_break_min=15,
            cycles_before_long_break=4,
        )
        timer, clock, rec = _make_timer(config=cfg)

        timer.start()
        # Drive three full work+short_break pairs.
        for _ in range(3):
            clock.advance(25 * 60)
            timer.tick()
            assert timer.state is State.SHORT_BREAK
            clock.advance(5 * 60)
            timer.tick()
            assert timer.state is State.WORK

        # Fourth work completion should go to LONG_BREAK, not SHORT_BREAK.
        clock.advance(25 * 60)
        timer.tick()

        assert timer.state is State.LONG_BREAK
        assert timer.remaining_seconds == 15 * 60
        assert rec.completes.count(State.WORK) == 4
        assert rec.completes.count(State.SHORT_BREAK) == 3
        # A transition WORK → LONG_BREAK must have been emitted exactly once.
        assert (State.WORK, State.LONG_BREAK) in rec.transitions
        assert (State.WORK, State.SHORT_BREAK) in rec.transitions

    def test_work_cycles_completed_counter_tracks_work_completions(self) -> None:
        timer, clock, _rec = _make_timer(config=_cfg(work_min=1, short_break_min=1))

        timer.start()
        assert timer.work_cycles_completed == 0

        clock.advance(60)
        timer.tick()
        assert timer.work_cycles_completed == 1

        clock.advance(60)
        timer.tick()  # completes short break → work; counter unchanged
        assert timer.work_cycles_completed == 1

        clock.advance(60)
        timer.tick()  # completes second work
        assert timer.work_cycles_completed == 2


# --------------------------------------------------------------------------
# AC: pause + resume
# --------------------------------------------------------------------------


class TestPauseAndResume:
    """AC: paused time does not count against the current interval."""

    def test_pause_sets_state_and_freezes_remaining(self) -> None:
        timer, clock, rec = _make_timer(config=_cfg(work_min=25))
        timer.start()
        clock.advance(10 * 60)

        timer.pause()
        frozen = timer.remaining_seconds
        clock.advance(5 * 60)

        assert timer.state is State.PAUSED
        assert timer.remaining_seconds == frozen
        assert (State.WORK, State.PAUSED) in rec.transitions

    def test_tick_while_paused_is_noop(self) -> None:
        timer, clock, rec = _make_timer(config=_cfg(work_min=25))
        timer.start()
        clock.advance(10 * 60)
        timer.pause()
        before = (list(rec.ticks), list(rec.completes))

        clock.advance(60 * 60)  # would complete if we weren't paused
        timer.tick()

        assert (list(rec.ticks), list(rec.completes)) == before

    def test_resume_restores_prior_interval_and_extends_deadline(self) -> None:
        timer, clock, rec = _make_timer(config=_cfg(work_min=25))
        timer.start()
        clock.advance(10 * 60)  # 15 min left
        timer.pause()
        clock.advance(5 * 60)  # paused; interval should shift
        timer.resume()

        assert timer.state is State.WORK
        assert timer.remaining_seconds == 15 * 60
        assert (State.PAUSED, State.WORK) in rec.transitions

        # Completing the remaining 15 minutes should finish the work interval.
        clock.advance(15 * 60)
        timer.tick()

        assert rec.completes == [State.WORK]
        assert timer.state is State.SHORT_BREAK


# --------------------------------------------------------------------------
# AC: abort does not emit on_complete
# --------------------------------------------------------------------------


class TestAbort:
    """AC: aborted sessions emit on_abort and NOT on_complete."""

    def test_abort_during_work_emits_on_abort_and_moves_to_aborted(self) -> None:
        timer, clock, rec = _make_timer(config=_cfg(work_min=25))
        timer.start()
        clock.advance(10 * 60)

        timer.abort()

        assert timer.state is State.ABORTED
        assert rec.aborts == [State.WORK]
        assert rec.completes == []

    def test_abort_can_happen_from_paused(self) -> None:
        timer, clock, rec = _make_timer(config=_cfg(work_min=25))
        timer.start()
        clock.advance(60)
        timer.pause()

        timer.abort()

        assert timer.state is State.ABORTED
        assert rec.aborts == [State.WORK]
        assert rec.completes == []

    def test_tick_after_abort_is_noop(self) -> None:
        timer, clock, rec = _make_timer(config=_cfg(work_min=25))
        timer.start()
        timer.abort()

        clock.advance(10 * 60)
        timer.tick()

        assert rec.completes == []
        assert rec.ticks == []


# --------------------------------------------------------------------------
# Edge cases — guarding misuse
# --------------------------------------------------------------------------


class TestInvalidTransitions:
    def test_start_from_non_idle_raises(self) -> None:
        timer, _clock, _rec = _make_timer()
        timer.start()
        with pytest.raises(RuntimeError):
            timer.start()

    def test_pause_when_not_running_raises(self) -> None:
        timer, _clock, _rec = _make_timer()
        with pytest.raises(RuntimeError):
            timer.pause()

    def test_resume_when_not_paused_raises(self) -> None:
        timer, _clock, _rec = _make_timer()
        timer.start()
        with pytest.raises(RuntimeError):
            timer.resume()

    def test_abort_from_idle_raises(self) -> None:
        timer, _clock, _rec = _make_timer()
        with pytest.raises(RuntimeError):
            timer.abort()

    def test_abort_after_abort_raises(self) -> None:
        timer, _clock, _rec = _make_timer()
        timer.start()
        timer.abort()
        with pytest.raises(RuntimeError):
            timer.abort()

    def test_tick_from_idle_is_noop(self) -> None:
        timer, clock, rec = _make_timer()
        clock.advance(999)
        timer.tick()
        assert rec.ticks == []
        assert rec.completes == []


class TestCallbacksAreOptional:
    """The timer works without any callbacks wired up."""

    def test_start_tick_complete_without_callbacks(self) -> None:
        clock = FakeClock()
        timer = Timer(config=_cfg(work_min=1), clock=clock)
        timer.start()
        clock.advance(60)
        timer.tick()
        assert timer.state is State.SHORT_BREAK
