"""Configuration loader with layered precedence.

Merge order, highest first:

1. CLI flags (passed in via ``cli_overrides``)
2. Environment variables (``POMO_*``)
3. TOML file at :func:`default_config_path`
4. Built-in defaults

A missing config file is silently created with default values on first run.
A malformed config file raises :class:`ConfigError` with a readable message.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import platformdirs

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised only on Python 3.10 CI legs
    import tomli as tomllib


class ConfigError(Exception):
    """Raised when a config source is malformed or has values of the wrong type."""


@dataclass(frozen=True)
class Config:
    """Resolved Pomodoro configuration.

    Args:
        work_min: Length of a work interval, in minutes.
        short_break_min: Length of a short break, in minutes.
        long_break_min: Length of a long break, in minutes.
        cycles_before_long_break: Work cycles between long breaks.
        sound: Whether to play the terminal bell on interval completion.
    """

    work_min: int = 25
    short_break_min: int = 5
    long_break_min: int = 15
    cycles_before_long_break: int = 4
    sound: bool = True


_ENV_MAP: dict[str, str] = {
    "work_min": "POMO_WORK_MIN",
    "short_break_min": "POMO_SHORT_BREAK_MIN",
    "long_break_min": "POMO_LONG_BREAK_MIN",
    "cycles_before_long_break": "POMO_CYCLES_BEFORE_LONG_BREAK",
    "sound": "POMO_SOUND",
}

_INT_FIELDS: frozenset[str] = frozenset(
    {"work_min", "short_break_min", "long_break_min", "cycles_before_long_break"}
)
_BOOL_FIELDS: frozenset[str] = frozenset({"sound"})

_TRUE_STRINGS: frozenset[str] = frozenset({"1", "true", "yes", "on"})
_FALSE_STRINGS: frozenset[str] = frozenset({"0", "false", "no", "off"})


def default_config_path() -> Path:
    """Return the platform-appropriate default config file path."""
    return Path(platformdirs.user_config_dir("pomo")) / "config.toml"


def _known_fields() -> set[str]:
    return {f.name for f in fields(Config)}


def _render_defaults_toml() -> str:
    c = Config()
    return (
        "# pomo config file — edit values below or override via env vars / CLI.\n"
        f"work_min = {c.work_min}\n"
        f"short_break_min = {c.short_break_min}\n"
        f"long_break_min = {c.long_break_min}\n"
        f"cycles_before_long_break = {c.cycles_before_long_break}\n"
        f"sound = {'true' if c.sound else 'false'}\n"
    )


def _ensure_config_file(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_defaults_toml(), encoding="utf-8")


def _read_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Could not parse config file {path}: {exc}") from exc

    unknown = set(raw) - _known_fields()
    if unknown:
        joined = ", ".join(sorted(unknown))
        raise ConfigError(
            f"Unknown keys in config file {path}: {joined}. "
            f"Valid keys are: {', '.join(sorted(_known_fields()))}."
        )

    source = f"config file {path}"
    coerced: dict[str, Any] = {}
    for key, value in raw.items():
        if key in _INT_FIELDS:
            # bool is a subclass of int in Python; exclude it explicitly.
            if isinstance(value, bool) or not isinstance(value, int):
                raise ConfigError(f"{source}: {key!r} must be an integer, got {value!r}")
            coerced[key] = value
        else:  # bool field
            if not isinstance(value, bool):
                raise ConfigError(f"{source}: {key!r} must be true or false, got {value!r}")
            coerced[key] = value
    return coerced


def _parse_bool_env(raw: str, *, env_name: str) -> bool:
    lowered = raw.strip().lower()
    if lowered in _TRUE_STRINGS:
        return True
    if lowered in _FALSE_STRINGS:
        return False
    raise ConfigError(f"{env_name}: expected a boolean (true/false/1/0/yes/no/on/off), got {raw!r}")


def _parse_int_env(raw: str, *, env_name: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{env_name}: expected an integer, got {raw!r}") from exc


def _read_env() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field_name, env_name in _ENV_MAP.items():
        raw = os.environ.get(env_name)
        if raw is None:
            continue
        if field_name in _BOOL_FIELDS:
            out[field_name] = _parse_bool_env(raw, env_name=env_name)
        else:
            out[field_name] = _parse_int_env(raw, env_name=env_name)
    return out


def _filter_cli(cli_overrides: dict[str, Any]) -> dict[str, Any]:
    known = _known_fields()
    return {k: v for k, v in cli_overrides.items() if k in known and v is not None}


def load_config(
    cli_overrides: dict[str, Any],
    *,
    config_path: Path | None = None,
) -> Config:
    """Resolve configuration from CLI > env > file > defaults.

    Args:
        cli_overrides: Mapping of :class:`Config` field names to values supplied
            on the command line. ``None`` values are treated as "flag not given"
            and ignored so they do not override lower-precedence sources.
        config_path: Override the config file location. Defaults to
            :func:`default_config_path`. The file is created with default
            values if it does not already exist.

    Returns:
        A fully-resolved :class:`Config` instance.

    Raises:
        ConfigError: If the config file is not valid TOML, contains unknown
            keys, or has values of the wrong type; or if an environment
            variable cannot be parsed to the expected type.
    """
    path = config_path if config_path is not None else default_config_path()
    _ensure_config_file(path)

    merged: dict[str, Any] = {}
    merged.update(_read_file(path))
    merged.update(_read_env())
    merged.update(_filter_cli(cli_overrides))

    return Config(**merged)
