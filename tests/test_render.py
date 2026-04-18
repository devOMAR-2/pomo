"""Tests for pomo.ui.render — live countdown renderer."""

from __future__ import annotations

import re
from io import StringIO

import pytest
from rich.console import Console

from pomo.ui.render import Renderer

# Matches SGR sequences that set a foreground or background color
# (30-37, 90-97, 40-47, 100-107, plus the 256/truecolor prefixes 38 and 48).
_COLOR_SGR_RE = re.compile(r"\x1b\[(?:3[0-9]|4[0-9]|9[0-9]|10[0-9]|38|48)(?:;[\d;]*)?m")


def _plain_console() -> tuple[Console, StringIO]:
    buf = StringIO()
    # No force_terminal -> stdout is treated as a file (not a TTY).
    return Console(file=buf, force_terminal=False, width=80), buf


def _tty_console(*, no_color: bool = False) -> tuple[Console, StringIO]:
    buf = StringIO()
    return Console(
        file=buf,
        force_terminal=True,
        no_color=no_color,
        width=80,
    ), buf


def _render_once(console: Console, **render_kwargs: object) -> None:
    defaults: dict[str, object] = {
        "state": "work",
        "remaining_seconds": 600,
        "tag": "deep-work",
        "cycle": 1,
        "cycles_before_long_break": 4,
    }
    defaults.update(render_kwargs)
    with Renderer(console=console) as r:
        r.render(**defaults)  # type: ignore[arg-type]


class TestPlainModeFallback:
    """AC: piping `pomo start` to a file produces plain-text line-per-tick."""

    def test_non_tty_console_uses_plain_mode(self) -> None:
        console, _ = _plain_console()
        with Renderer(console=console) as r:
            assert r.is_live is False

    def test_plain_output_contains_state_time_tag_and_cycle(self) -> None:
        console, buf = _plain_console()
        _render_once(
            console,
            state="work",
            remaining_seconds=10 * 60,
            tag="deep-work",
            cycle=2,
            cycles_before_long_break=4,
        )
        out = buf.getvalue()
        assert "work" in out
        assert "10:00" in out
        assert "deep-work" in out
        assert "2/4" in out

    def test_plain_output_has_no_ansi_escape_codes(self) -> None:
        console, buf = _plain_console()
        _render_once(console)
        assert "\x1b" not in buf.getvalue()

    def test_plain_mode_emits_one_line_per_render_call(self) -> None:
        console, buf = _plain_console()
        with Renderer(console=console) as r:
            r.render(
                state="work",
                remaining_seconds=120,
                tag=None,
                cycle=1,
                cycles_before_long_break=4,
            )
            r.render(
                state="work",
                remaining_seconds=119,
                tag=None,
                cycle=1,
                cycles_before_long_break=4,
            )

        # One trailing newline per line. Filter blanks from any final flush.
        lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
        assert len(lines) == 2
        assert "02:00" in lines[0]
        assert "01:59" in lines[1]


class TestNoColor:
    """AC: NO_COLOR produces uncolored output even when stdout is a TTY."""

    def test_tty_with_no_color_has_no_color_sgr_codes(self) -> None:
        console, buf = _tty_console(no_color=True)
        _render_once(console)
        # NO_COLOR bans color codes specifically; bold/italic SGR and
        # terminal control sequences (cursor, clear-line) are still fine.
        assert _COLOR_SGR_RE.search(buf.getvalue()) is None

    def test_no_color_content_still_renders(self) -> None:
        console, buf = _tty_console(no_color=True)
        _render_once(
            console,
            state="short_break",
            remaining_seconds=5 * 60,
            tag=None,
            cycle=1,
            cycles_before_long_break=4,
        )
        out = buf.getvalue()
        assert "short_break" in out
        assert "05:00" in out
        assert "1/4" in out


class TestLiveMode:
    """On a real TTY the renderer drives Rich's Live display."""

    def test_tty_console_uses_live_mode(self) -> None:
        console, _ = _tty_console()
        with Renderer(console=console) as r:
            assert r.is_live is True

    def test_tty_output_contains_rendered_values(self) -> None:
        console, buf = _tty_console()
        _render_once(
            console,
            state="work",
            remaining_seconds=25 * 60,
            tag="writing",
            cycle=3,
            cycles_before_long_break=4,
        )
        out = buf.getvalue()
        assert "work" in out
        assert "25:00" in out
        assert "writing" in out
        assert "3/4" in out


class TestRenderEdgeCases:
    def test_none_tag_renders_placeholder(self) -> None:
        console, buf = _plain_console()
        _render_once(console, tag=None)
        assert "-" in buf.getvalue()

    def test_zero_remaining_formats_as_double_zero(self) -> None:
        console, buf = _plain_console()
        _render_once(console, remaining_seconds=0)
        assert "00:00" in buf.getvalue()

    def test_negative_remaining_clamps_to_zero(self) -> None:
        console, buf = _plain_console()
        _render_once(console, remaining_seconds=-5)
        assert "00:00" in buf.getvalue()

    def test_render_outside_context_raises(self) -> None:
        console, _ = _plain_console()
        r = Renderer(console=console)
        with pytest.raises(RuntimeError):
            r.render(
                state="work",
                remaining_seconds=60,
                tag=None,
                cycle=1,
                cycles_before_long_break=4,
            )
