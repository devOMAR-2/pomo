"""Allow ``python -m pomo`` to invoke the CLI."""

from pomo.cli import app

if __name__ == "__main__":  # pragma: no cover
    app()
