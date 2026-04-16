---
title: "Product Requirements Document — Pomodoro CLI"
author: "The Inner Clocks (Omar) + Claude (AI PM)"
date: "April 2026"
version: "1.0"
---

# Pomodoro CLI — Product Requirements Document

**Project codename:** `pomo`
**Version:** 1.0
**Status:** Draft, ready for engineering
**Owner:** Omar
**AI PM:** Claude

---

## 1. Summary

A fast, minimal command-line Pomodoro timer that runs in the terminal, logs every completed session to a local SQLite database, and shows daily/weekly productivity stats. Single binary, zero external services, fully offline.

This project exists primarily as the pilot for a larger automated workflow: **PRD → task breakdown → GitHub Projects → Claude Code implementation**. It is intentionally small (≈1 day of work) so the full pipeline can be exercised end-to-end without the pilot itself becoming the bottleneck.

## 2. Goals

1. Run a Pomodoro session (default 25 min work / 5 min short break / 15 min long break every 4 cycles) with one command.
2. Persist every completed interval to a local SQLite database, tagged with an optional project/task label.
3. Show a stats view: today, this week, per-tag breakdown.
4. Ship as a single `pip install pomo` package with a working `pomo` entry-point.
5. ≥ 80% test coverage on core domain logic (timer state machine, storage, stats).

## 3. Non-goals (v1.0)

- GUI or TUI animations beyond a simple countdown line.
- Cloud sync, accounts, or sharing.
- Mobile app.
- Calendar integration.
- Notifications beyond a terminal bell / optional `say`/`notify-send` hook.

## 4. Users & use cases

**Primary user:** A developer who lives in the terminal and wants lightweight focus tracking without opening a browser tab.

**Core use cases:**
- `pomo start` — begin a 25-minute work interval.
- `pomo start --tag haunt-hide` — tag the session for later reporting.
- `pomo start --work 50 --break 10` — custom durations.
- `pomo stats` — today's completed pomodoros, total focus minutes.
- `pomo stats --week` — per-day and per-tag breakdown for the last 7 days.
- `pomo history` — list recent sessions.

## 5. Functional requirements

### 5.1 Timer core
- State machine with states: `idle`, `work`, `short_break`, `long_break`, `paused`, `completed`.
- Default cycle: 4× (work → short_break) then long_break.
- Must render a live countdown (updated at least once per second) without flickering.
- Ctrl+C pauses; second Ctrl+C aborts the session (aborted sessions are NOT logged).
- On natural completion: write session row, play terminal bell, print summary.

### 5.2 Configuration
- Config file at `~/.config/pomo/config.toml` (created on first run with defaults).
- Overrides: CLI flags > env vars (`POMO_WORK_MIN`, `POMO_BREAK_MIN`) > config file > built-in defaults.

### 5.3 Storage
- SQLite database at `~/.local/share/pomo/pomo.db`.
- Schema:
  - `sessions(id INTEGER PK, started_at TEXT ISO8601, ended_at TEXT ISO8601, duration_s INTEGER, kind TEXT CHECK(kind IN ('work','short_break','long_break')), tag TEXT NULL, completed INTEGER DEFAULT 1)`.
  - One migration file per schema change; applied automatically on startup.

### 5.4 Stats
- `pomo stats` (today): count of completed work sessions, total focus minutes, per-tag breakdown.
- `pomo stats --week`: same, grouped by day, 7-day ASCII bar chart.
- `pomo history [--limit N]`: most recent N sessions in a formatted table (default 10).

### 5.5 CLI ergonomics
- Built with [Typer](https://typer.tiangolo.com/) (Click under the hood).
- `--help` on every command with examples.
- Colored output via Rich; respects `NO_COLOR` env var.

## 6. Non-functional requirements

- **Python:** 3.10+.
- **Dependencies:** Typer, Rich, platformdirs. No others without review.
- **Startup time:** `pomo --help` under 150 ms on a modern laptop.
- **Binary size / install:** `pip install pomo` under 5 MB.
- **Cross-platform:** macOS, Linux, Windows (WSL tested; native Windows best-effort).

## 7. Architecture

```
pomo/
├── __init__.py
├── cli.py              # Typer app, command definitions
├── core/
│   ├── timer.py        # State machine, tick loop
│   ├── config.py       # Load + merge config sources
│   └── clock.py        # Injectable clock for testing
├── storage/
│   ├── db.py           # Connection, migrations
│   ├── models.py       # Session dataclass
│   └── repository.py   # insert_session, list_sessions, stats queries
├── ui/
│   ├── render.py       # Countdown renderer (Rich Live)
│   └── tables.py       # History + stats tables
└── __main__.py         # `python -m pomo`
tests/
├── test_timer.py
├── test_config.py
├── test_repository.py
├── test_stats.py
└── test_cli.py         # Typer CliRunner
```

## 8. Milestones

| # | Milestone | Outcome |
|---|-----------|---------|
| M1 | Project scaffold | Repo, pyproject, CI, linting, empty `pomo` command runs |
| M2 | Storage layer | SQLite + migrations + repository with passing tests |
| M3 | Timer core | State machine + clock abstraction, unit-tested |
| M4 | CLI `start` | End-to-end: run a session, see countdown, row persisted |
| M5 | Stats + history | `stats`, `stats --week`, `history` commands working |
| M6 | Polish + release | README, example GIF, v1.0.0 tagged on PyPI (test index OK) |

## 9. Acceptance criteria (release)

- `pip install pomo` installs cleanly in a fresh venv.
- `pomo start --work 1 --break 1 --tag test` runs a full cycle, persists 2 rows.
- `pomo stats` shows non-zero counts afterward.
- `pytest` passes with ≥ 80% coverage on `pomo/core/` and `pomo/storage/`.
- CI (GitHub Actions) is green on Linux + macOS for Python 3.10, 3.11, 3.12.
- README has install, usage, example output, and a short screencast.

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Live terminal rendering flickers on slow terminals | Use Rich's `Live` with `refresh_per_second=4`, fall back to plain print if `sys.stdout.isatty()` is false |
| SQLite concurrent access (if user opens two shells) | Use `PRAGMA journal_mode=WAL`, single-writer assumption documented |
| Windows terminal bell / cross-platform audio quirks | Make sound optional, controlled by `--sound/--no-sound` flag |

## 11. Open questions

- Should we support a "resume interrupted session" feature, or is aborting + restarting fine for v1? → **Defer to v1.1.**
- Should tags be hierarchical (`haunt-hide/networking`)? → **Treat as plain strings in v1; hierarchy is just convention.**

---

*End of PRD. This document is the input to the task-decomposition stage. See `02-tasks/tasks.json`.*
