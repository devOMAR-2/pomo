"""Tests for pomo.core.config — layered config loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _clear_pomo_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip all POMO_* config env vars so tests start from a known state."""
    for name in (
        "POMO_WORK_MIN",
        "POMO_SHORT_BREAK_MIN",
        "POMO_LONG_BREAK_MIN",
        "POMO_CYCLES_BEFORE_LONG_BREAK",
        "POMO_SOUND",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def cfg_path(tmp_path: Path) -> Path:
    """Return a config path inside tmp_path that does not yet exist."""
    return tmp_path / "config.toml"


def _write_toml(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


class TestDefaults:
    """With no file, no env, no CLI, load_config returns built-in defaults."""

    def test_defaults_are_pomodoro_classic(self, cfg_path: Path) -> None:
        from pomo.core.config import Config, load_config

        cfg = load_config({}, config_path=cfg_path)
        assert cfg == Config(
            work_min=25,
            short_break_min=5,
            long_break_min=15,
            cycles_before_long_break=4,
            sound=True,
        )


class TestFileAutoCreate:
    """AC: Missing config file is silently created with defaults."""

    def test_missing_file_created_on_first_run(self, cfg_path: Path) -> None:
        from pomo.core.config import load_config

        assert not cfg_path.exists()
        load_config({}, config_path=cfg_path)
        assert cfg_path.is_file()

    def test_created_file_contains_default_values(self, cfg_path: Path) -> None:
        from pomo.core.config import Config, load_config

        load_config({}, config_path=cfg_path)
        # Re-loading from the just-created file must yield the same defaults.
        cfg = load_config({}, config_path=cfg_path)
        assert cfg == Config()

    def test_existing_file_is_not_overwritten(self, cfg_path: Path) -> None:
        from pomo.core.config import load_config

        _write_toml(cfg_path, "work_min = 42\n")
        load_config({}, config_path=cfg_path)
        assert "42" in cfg_path.read_text(encoding="utf-8")

    def test_parent_dir_is_created(self, tmp_path: Path) -> None:
        from pomo.core.config import load_config

        nested = tmp_path / "deep" / "nested" / "config.toml"
        assert not nested.parent.exists()
        load_config({}, config_path=nested)
        assert nested.is_file()


class TestPrecedence:
    """AC: CLI override beats env var beats config file beats default."""

    def test_file_overrides_default(self, cfg_path: Path) -> None:
        from pomo.core.config import load_config

        _write_toml(cfg_path, "work_min = 50\n")
        cfg = load_config({}, config_path=cfg_path)
        assert cfg.work_min == 50
        assert cfg.short_break_min == 5  # unchanged default

    def test_env_overrides_file(self, cfg_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from pomo.core.config import load_config

        _write_toml(cfg_path, "work_min = 50\n")
        monkeypatch.setenv("POMO_WORK_MIN", "30")
        cfg = load_config({}, config_path=cfg_path)
        assert cfg.work_min == 30

    def test_cli_overrides_env(self, cfg_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from pomo.core.config import load_config

        monkeypatch.setenv("POMO_WORK_MIN", "30")
        cfg = load_config({"work_min": 99}, config_path=cfg_path)
        assert cfg.work_min == 99

    def test_cli_overrides_file(self, cfg_path: Path) -> None:
        from pomo.core.config import load_config

        _write_toml(cfg_path, "work_min = 50\n")
        cfg = load_config({"work_min": 99}, config_path=cfg_path)
        assert cfg.work_min == 99

    def test_full_precedence_chain(self, cfg_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """File sets a, env overrides a+b, CLI overrides a; defaults fill c,d,e."""
        from pomo.core.config import load_config

        _write_toml(
            cfg_path,
            "work_min = 10\nshort_break_min = 11\n",
        )
        monkeypatch.setenv("POMO_WORK_MIN", "20")
        monkeypatch.setenv("POMO_LONG_BREAK_MIN", "22")

        cfg = load_config({"work_min": 99}, config_path=cfg_path)

        assert cfg.work_min == 99  # CLI wins
        assert cfg.short_break_min == 11  # file wins (no env, no CLI)
        assert cfg.long_break_min == 22  # env wins (no CLI, no file)
        assert cfg.cycles_before_long_break == 4  # default
        assert cfg.sound is True  # default

    def test_cli_none_values_are_ignored(
        self, cfg_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missing CLI flag (None) must not stomp on lower-precedence sources."""
        from pomo.core.config import load_config

        monkeypatch.setenv("POMO_WORK_MIN", "30")
        overrides: dict[str, Any] = {"work_min": None, "sound": None}
        cfg = load_config(overrides, config_path=cfg_path)
        assert cfg.work_min == 30
        assert cfg.sound is True  # still the default


class TestEnvParsing:
    """Env var strings are coerced to the right type, or fail cleanly."""

    def test_int_env_vars(self, cfg_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from pomo.core.config import load_config

        monkeypatch.setenv("POMO_WORK_MIN", "45")
        monkeypatch.setenv("POMO_SHORT_BREAK_MIN", "7")
        monkeypatch.setenv("POMO_LONG_BREAK_MIN", "20")
        monkeypatch.setenv("POMO_CYCLES_BEFORE_LONG_BREAK", "6")

        cfg = load_config({}, config_path=cfg_path)
        assert cfg.work_min == 45
        assert cfg.short_break_min == 7
        assert cfg.long_break_min == 20
        assert cfg.cycles_before_long_break == 6

    @pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "on"])
    def test_sound_env_truthy(
        self, value: str, cfg_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pomo.core.config import load_config

        monkeypatch.setenv("POMO_SOUND", value)
        assert load_config({}, config_path=cfg_path).sound is True

    @pytest.mark.parametrize("value", ["false", "False", "0", "no", "off"])
    def test_sound_env_falsy(
        self, value: str, cfg_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pomo.core.config import load_config

        monkeypatch.setenv("POMO_SOUND", value)
        assert load_config({}, config_path=cfg_path).sound is False

    def test_invalid_int_env_raises(self, cfg_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from pomo.core.config import ConfigError, load_config

        monkeypatch.setenv("POMO_WORK_MIN", "not-an-int")
        with pytest.raises(ConfigError, match="POMO_WORK_MIN"):
            load_config({}, config_path=cfg_path)

    def test_invalid_bool_env_raises(self, cfg_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from pomo.core.config import ConfigError, load_config

        monkeypatch.setenv("POMO_SOUND", "maybe")
        with pytest.raises(ConfigError, match="POMO_SOUND"):
            load_config({}, config_path=cfg_path)


class TestMalformedFile:
    """AC: Malformed config file raises a friendly error, not a stack trace."""

    def test_malformed_toml_raises_config_error(self, cfg_path: Path) -> None:
        from pomo.core.config import ConfigError, load_config

        _write_toml(cfg_path, "work_min = = 25\n")  # syntactically invalid
        with pytest.raises(ConfigError, match="parse"):
            load_config({}, config_path=cfg_path)

    def test_unknown_key_raises_config_error(self, cfg_path: Path) -> None:
        from pomo.core.config import ConfigError, load_config

        _write_toml(cfg_path, 'work_min = 25\nmystery = "hi"\n')
        with pytest.raises(ConfigError, match="mystery"):
            load_config({}, config_path=cfg_path)

    def test_wrong_type_for_int_field(self, cfg_path: Path) -> None:
        from pomo.core.config import ConfigError, load_config

        _write_toml(cfg_path, 'work_min = "twenty-five"\n')
        with pytest.raises(ConfigError, match="work_min"):
            load_config({}, config_path=cfg_path)

    def test_bool_rejected_for_int_field(self, cfg_path: Path) -> None:
        """bool is an int subclass in Python — reject it explicitly."""
        from pomo.core.config import ConfigError, load_config

        _write_toml(cfg_path, "work_min = true\n")
        with pytest.raises(ConfigError, match="work_min"):
            load_config({}, config_path=cfg_path)

    def test_wrong_type_for_bool_field(self, cfg_path: Path) -> None:
        from pomo.core.config import ConfigError, load_config

        _write_toml(cfg_path, "sound = 1\n")
        with pytest.raises(ConfigError, match="sound"):
            load_config({}, config_path=cfg_path)


class TestDefaultPath:
    """default_config_path returns a platform-appropriate location."""

    def test_default_path_used_when_not_overridden(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pomo.core import config as config_mod
        from pomo.core.config import load_config

        fake_path = tmp_path / "default" / "config.toml"
        monkeypatch.setattr(config_mod, "default_config_path", lambda: fake_path)

        load_config({})
        assert fake_path.is_file()

    def test_default_config_path_ends_with_config_toml(self) -> None:
        from pomo.core.config import default_config_path

        assert default_config_path().name == "config.toml"
