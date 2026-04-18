"""Live countdown renderer for the ``pomo`` CLI.

When stdout is a real terminal, the renderer drives a Rich ``Live``
panel that refreshes at 4 fps so the countdown stays smooth even if
the caller ticks less often. When stdout is not a terminal (piping
into a file, CI logs, etc.) it falls back to a plain single-line
``print`` per :meth:`Renderer.render` call so downstream consumers
get clean line-per-tick output. ``NO_COLOR`` is honoured automatically
by :class:`rich.console.Console`.
"""

from __future__ import annotations

from types import TracebackType

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def _format_mmss(seconds: int) -> str:
    minutes, secs = divmod(max(int(seconds), 0), 60)
    return f"{minutes:02d}:{secs:02d}"


def _build_panel(
    *,
    state: str,
    remaining_seconds: int,
    tag: str | None,
    cycle: int,
    cycles_before_long_break: int,
) -> Panel:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(justify="right", style="bold")
    grid.add_column()
    grid.add_row("Phase", Text(state, style="bold cyan"))
    grid.add_row("Remaining", Text(_format_mmss(remaining_seconds), style="bold"))
    grid.add_row("Tag", tag if tag is not None else "-")
    grid.add_row("Cycle", f"{cycle}/{cycles_before_long_break}")
    return Panel(grid, title="pomo", border_style="cyan")


def _build_plain_line(
    *,
    state: str,
    remaining_seconds: int,
    tag: str | None,
    cycle: int,
    cycles_before_long_break: int,
) -> str:
    tag_display = tag if tag is not None else "-"
    return (
        f"[{state}] {_format_mmss(remaining_seconds)}  "
        f"tag={tag_display}  cycle {cycle}/{cycles_before_long_break}"
    )


class Renderer:
    """Render timer state to a :class:`rich.console.Console`.

    Use as a context manager. On a TTY console, a Rich ``Live`` panel is
    installed that refreshes ``refresh_per_second`` times a second (4 by
    default). On a non-TTY console, :meth:`render` prints one plain
    line per call instead.

    Args:
        console: Rich console to render into. Defaults to the global
            ``Console()``, which honours ``NO_COLOR`` and detects TTYs
            automatically.
        refresh_per_second: Live-mode refresh rate. Ignored in plain mode.
    """

    def __init__(
        self,
        *,
        console: Console | None = None,
        refresh_per_second: int = 4,
    ) -> None:
        self._console = console if console is not None else Console()
        self._refresh_per_second = refresh_per_second
        self._live: Live | None = None
        self._entered: bool = False

    @property
    def console(self) -> Console:
        return self._console

    @property
    def is_live(self) -> bool:
        """Whether this renderer is using Rich's ``Live`` display."""
        return self._console.is_terminal

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------

    def __enter__(self) -> Renderer:
        self._entered = True
        if self.is_live:
            self._live = Live(
                Text(""),
                console=self._console,
                refresh_per_second=self._refresh_per_second,
                transient=False,
            )
            self._live.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._entered = False
        if self._live is not None:
            self._live.__exit__(exc_type, exc, tb)
            self._live = None

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(
        self,
        *,
        state: str,
        remaining_seconds: int,
        tag: str | None,
        cycle: int,
        cycles_before_long_break: int,
    ) -> None:
        """Render one frame of the countdown."""
        if not self._entered:
            raise RuntimeError("Renderer.render() must be called inside a 'with' block")

        if self._live is not None:
            self._live.update(
                _build_panel(
                    state=state,
                    remaining_seconds=remaining_seconds,
                    tag=tag,
                    cycle=cycle,
                    cycles_before_long_break=cycles_before_long_break,
                ),
                refresh=True,
            )
        else:
            line = _build_plain_line(
                state=state,
                remaining_seconds=remaining_seconds,
                tag=tag,
                cycle=cycle,
                cycles_before_long_break=cycles_before_long_break,
            )
            self._console.print(line, markup=False, highlight=False)
