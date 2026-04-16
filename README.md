# pomo

A Python 3.10+ command-line Pomodoro timer with SQLite session logging.

The full product spec lives in [`docs/prd-pomodoro-cli.md`](docs/prd-pomodoro-cli.md).

## Install (development)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Usage

```bash
pomo --help          # show available commands
python -m pomo --help # equivalent module invocation
```

The CLI is currently a scaffold; subcommands are added in subsequent tickets.

## Development

```bash
pytest -q                 # run tests
ruff check .              # lint
ruff format --check .     # formatting check
mypy pomo/                # type-check
```

See [`CLAUDE.md`](CLAUDE.md) for repository conventions.
