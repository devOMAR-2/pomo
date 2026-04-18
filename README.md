# pomo

[![CI](https://github.com/devOMAR-2/pomo/actions/workflows/ci.yml/badge.svg)](https://github.com/devOMAR-2/pomo/actions/workflows/ci.yml)
[![TestPyPI version](https://img.shields.io/pypi/v/pomo-devOMAR?pypiBaseUrl=https://test.pypi.org&label=TestPyPI)](https://test.pypi.org/project/pomo-devOMAR/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](#license)

A command-line Pomodoro timer with SQLite session logging. Run work/break
cycles from the terminal, tag your sessions, and get a history and daily
stats — all local, no accounts, no sync.

> Full product spec: [`docs/prd-pomodoro-cli.md`](docs/prd-pomodoro-cli.md)

## Install

Once published:

```bash
pip install pomo-devOMAR
```

The distribution name on PyPI is `pomo-devOMAR`; the installed command
and Python import name are both still `pomo`.

From source:

```bash
git clone https://github.com/devOMAR-2/pomo.git
cd pomo
pip install -e .
```

`pomo` requires Python 3.10 or newer.

## Quickstart

```bash
# One 25 / 5-minute cycle, tagged "writing"
pomo start --tag writing

# Two custom-length cycles without the terminal bell
pomo start --work 50 --break 10 --cycles 2 --no-sound

# See the last 10 sessions
pomo history

# Today's focus summary + per-tag breakdown
pomo stats

# Same, plus a 7-day bar chart
pomo stats --week
```

`Ctrl+C` pauses the current interval; press it again to abort. Aborted
intervals are not written to the database.

## Commands

### `pomo start`

Run one or more work/break cycles and log each completed interval.

| Flag | Default | Description |
| --- | --- | --- |
| `--work N` | from config | Work interval length in minutes |
| `--break N` | from config | Short break length in minutes |
| `--long-break N` | from config | Long break length in minutes |
| `--cycles N` | `1` | Number of work intervals to run |
| `--tag TEXT` | none | Tag stored on every session row in this run |
| `--no-sound` | off | Disable the terminal bell on interval completion |

### `pomo history`

Show the most recent sessions, newest first.

| Flag | Default | Description |
| --- | --- | --- |
| `--limit N`, `-n N` | `10` | Maximum rows to show |

### `pomo stats`

Today's completed-work count, total focus minutes, and a per-tag breakdown.

| Flag | Description |
| --- | --- |
| `--week` | Add a 7-row ASCII bar chart of the last 7 days |

## Configuration

Settings are resolved in order: **CLI flags > environment variables >
TOML file > built-in defaults**.

The config file is created automatically on first run at the platform's
user config directory (`~/.config/pomo/config.toml` on Linux,
`~/Library/Application Support/pomo/config.toml` on macOS,
`%APPDATA%\pomo\config.toml` on Windows).

```toml
# config.toml
work_min = 25
short_break_min = 5
long_break_min = 15
cycles_before_long_break = 4
sound = true
```

Corresponding environment variables:

```bash
POMO_WORK_MIN=50
POMO_SHORT_BREAK_MIN=10
POMO_LONG_BREAK_MIN=20
POMO_CYCLES_BEFORE_LONG_BREAK=4
POMO_SOUND=false
POMO_DB_PATH=/custom/path/to/pomo.db   # override session DB location
```

## Development

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

pytest -q                          # run tests
pytest --cov=pomo --cov-report=term-missing
ruff check .                       # lint
ruff format --check .              # formatting check
mypy pomo/                         # type-check
```

Repository conventions (commit style, branching, test philosophy) live in
[`CLAUDE.md`](CLAUDE.md).

## License

MIT. See [`pyproject.toml`](pyproject.toml) for the package metadata.
