"""Command-line entry point for the Pomodoro timer."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import typer
from rich.console import Console

from pomo.core.clock import Clock, SystemClock
from pomo.core.config import Config, load_config
from pomo.core.timer import State, Timer
from pomo.storage.db import get_connection
from pomo.storage.models import Session
from pomo.storage.repository import SessionRepository
from pomo.ui.render import Renderer
from pomo.ui.tables import render_history_table

app = typer.Typer(
    name="pomo",
    help="Command-line Pomodoro timer with SQLite session logging.",
    no_args_is_help=True,
    add_completion=False,
)


_INTERVAL_STATES: frozenset[State] = frozenset({State.WORK, State.SHORT_BREAK, State.LONG_BREAK})


@app.callback()
def main() -> None:
    """Pomodoro CLI root command.

    Subcommands will be registered here as they are implemented.
    """


# --------------------------------------------------------------------------
# pomo history
# --------------------------------------------------------------------------


@app.command("history")
def history(
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        min=1,
        help="Maximum number of recent sessions to show.",
    ),
) -> None:
    """Show the most recent sessions."""
    conn = get_connection()
    try:
        sessions = SessionRepository(conn).list_recent(limit=limit)
    finally:
        conn.close()

    console = Console()
    if not sessions:
        console.print("No sessions yet. Start one with `pomo start`.")
        return

    console.print(render_history_table(sessions))


# --------------------------------------------------------------------------
# pomo start
# --------------------------------------------------------------------------


@app.command("start")
def start(
    work: int | None = typer.Option(None, "--work", min=1, help="Work interval length in minutes."),
    short_break: int | None = typer.Option(
        None, "--break", min=1, help="Short break length in minutes."
    ),
    long_break: int | None = typer.Option(
        None, "--long-break", min=1, help="Long break length in minutes."
    ),
    cycles: int = typer.Option(
        1, "--cycles", min=1, help="Number of work sessions to run before stopping."
    ),
    tag: str | None = typer.Option(None, "--tag", help="Optional tag applied to every session."),
    no_sound: bool = typer.Option(
        False, "--no-sound", help="Disable the terminal bell on interval completion."
    ),
) -> None:
    """Run a Pomodoro session and log each completed interval to the database."""
    cli_overrides: dict[str, Any] = {
        "work_min": work,
        "short_break_min": short_break,
        "long_break_min": long_break,
    }
    if no_sound:
        cli_overrides["sound"] = False
    config = load_config(cli_overrides)

    conn = get_connection()
    try:
        repo = SessionRepository(conn)
        exit_code = run_pomo_loop(
            config=config,
            clock=SystemClock(),
            cycles=cycles,
            tag=tag,
            repo=repo,
            console=Console(),
        )
    finally:
        conn.close()
    if exit_code != 0:
        raise typer.Exit(code=exit_code)


def run_pomo_loop(
    *,
    config: Config,
    clock: Clock,
    cycles: int,
    tag: str | None,
    repo: SessionRepository,
    console: Console,
    poll_interval: float = 0.25,
    now_fn: Callable[[], datetime] = datetime.now,
) -> int:
    """Drive a Pomodoro session until ``cycles`` work intervals complete.

    This function is split out of :func:`start` so tests can drive it with
    a :class:`~pomo.core.clock.FakeClock` subclass whose ``sleep`` advances
    time, instead of waiting on real wall-clock durations.

    Args:
        config: Resolved configuration (interval durations + sound flag).
        clock: Time source used for both the timer and the poll-loop sleeps.
        cycles: Number of ``work`` intervals to run before stopping. The
            final break after the last work is allowed to complete.
        tag: Stored on every persisted session row for this run.
        repo: Where completed sessions are written.
        console: Rich console for the live countdown.
        poll_interval: Seconds between timer ticks / renders.
        now_fn: Callable returning the current ``datetime`` used for
            ``started_at``/``ended_at`` on persisted rows. Test code passes
            a clock-tracking callable; production uses :func:`datetime.now`.

    Returns:
        ``0`` on a clean completion, ``130`` if the run was aborted
        (SIGINT convention).
    """
    interval_started: dict[str, datetime] = {}

    def on_transition(_prev: State, nxt: State) -> None:
        if nxt in _INTERVAL_STATES:
            interval_started["t"] = now_fn()

    def on_complete(finished: State) -> None:
        started = interval_started.pop("t", None)
        if started is None:
            return
        ended = now_fn()
        repo.insert(
            Session(
                id=None,
                started_at=started.isoformat(),
                ended_at=ended.isoformat(),
                duration_s=int((ended - started).total_seconds()),
                kind=finished.value,
                tag=tag,
                completed=True,
            )
        )
        if config.sound:
            console.print("\a", end="")

    timer = Timer(
        config=config,
        clock=clock,
        on_transition=on_transition,
        on_complete=on_complete,
    )

    interrupts = 0
    with Renderer(console=console) as renderer:
        timer.start()
        while timer.state is not State.ABORTED:
            try:
                timer.tick()

                # Stop once we've completed the requested number of work
                # intervals *and* the trailing break: Timer will have just
                # transitioned back to WORK, so that's our cue to exit
                # before the unwanted next interval runs.
                if timer.work_cycles_completed >= cycles and timer.state is State.WORK:
                    break

                if timer.state in _INTERVAL_STATES:
                    renderer.render(
                        state=timer.state.value,
                        remaining_seconds=timer.remaining_seconds,
                        tag=tag,
                        cycle=_display_cycle(timer, config),
                        cycles_before_long_break=config.cycles_before_long_break,
                    )
                clock.sleep(poll_interval)
            except KeyboardInterrupt:
                interrupts += 1
                if interrupts == 1 and timer.state in _INTERVAL_STATES:
                    timer.pause()
                    console.print("\nPaused. Press Ctrl+C again to abort.")
                else:
                    timer.abort()
                    break

    return 130 if timer.state is State.ABORTED else 0


def _display_cycle(timer: Timer, config: Config) -> int:
    """Position within the current long-break round, 1-indexed."""
    m = config.cycles_before_long_break
    n = timer.work_cycles_completed
    if timer.state is State.WORK:
        return (n % m) + 1
    return n % m or m


if __name__ == "__main__":  # pragma: no cover
    app()
