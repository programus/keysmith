"""Tests for keysmith.config."""

from pathlib import Path
from textwrap import dedent

import pytest

from keysmith.config import (
    CONFIG_ENV_VAR,
    Config,
    ConfigError,
    DEFAULT_BAUD,
    DEFAULT_OPEN_DELAY_S,
    load_config,
    resolve_config_path,
)


def write(path: Path, body: str) -> Path:
    path.write_text(dedent(body), encoding="utf-8")
    return path


class TestResolveConfigPath:
    def test_explicit_overrides_everything(self, tmp_path, monkeypatch):
        cfg = write(tmp_path / "explicit.yaml", "device: {}\n")
        decoy = write(tmp_path / "decoy.yaml", "device: {}\n")
        monkeypatch.setenv(CONFIG_ENV_VAR, str(decoy))
        assert resolve_config_path(cfg) == cfg

    def test_explicit_missing_raises(self, tmp_path):
        with pytest.raises(ConfigError):
            resolve_config_path(tmp_path / "nope.yaml")

    def test_env_var_used(self, tmp_path, monkeypatch):
        cfg = write(tmp_path / "env.yaml", "device: {}\n")
        monkeypatch.setenv(CONFIG_ENV_VAR, str(cfg))
        assert resolve_config_path() == cfg

    def test_env_var_missing_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv(CONFIG_ENV_VAR, str(tmp_path / "nope.yaml"))
        with pytest.raises(ConfigError):
            resolve_config_path()


class TestLoadConfig:
    def test_minimal_valid(self, tmp_path):
        cfg_file = write(tmp_path / "c.yaml", """
            device:
              port: /dev/cu.usbmodem8401
              baud: 115200
            actions:
              unlock:
                - tap: international3
        """)
        cfg = load_config(cfg_file)
        assert cfg.device.port == "/dev/cu.usbmodem8401"
        assert cfg.device.baud == 115200
        assert cfg.device.open_delay_s == DEFAULT_OPEN_DELAY_S
        assert cfg.has_action("unlock")
        assert cfg.actions["unlock"] == [{"tap": "international3"}]
        assert cfg.source == cfg_file

    def test_open_delay_s_loaded(self, tmp_path):
        cfg_file = write(tmp_path / "c.yaml", """
            device:
              open-delay-s: 2.0
        """)
        cfg = load_config(cfg_file)
        assert cfg.device.open_delay_s == 2.0

    def test_open_delay_s_zero_allowed(self, tmp_path):
        cfg_file = write(tmp_path / "c.yaml", """
            device:
              open-delay-s: 0
        """)
        cfg = load_config(cfg_file)
        assert cfg.device.open_delay_s == 0.0

    def test_open_delay_s_negative_rejected(self, tmp_path):
        cfg_file = write(tmp_path / "c.yaml", """
            device:
              open-delay-s: -0.1
        """)
        with pytest.raises(ConfigError, match="non-negative"):
            load_config(cfg_file)

    def test_open_delay_s_string_rejected(self, tmp_path):
        cfg_file = write(tmp_path / "c.yaml", """
            device:
              open-delay-s: "fast"
        """)
        with pytest.raises(ConfigError, match="non-negative number"):
            load_config(cfg_file)

    def test_snake_case_key_rejected_with_helpful_message(self, tmp_path):
        # If a user types `open_delay_s:` instead of `open-delay-s:`, we
        # must error explicitly — silently ignoring it would lead to
        # mysterious "the setting has no effect" bug reports.
        cfg_file = write(tmp_path / "c.yaml", """
            device:
              open_delay_s: 2.0
        """)
        with pytest.raises(ConfigError, match="kebab-case"):
            load_config(cfg_file)

    def test_unknown_top_level_key_rejected(self, tmp_path):
        cfg_file = write(tmp_path / "c.yaml", """
            devices:
              port: /dev/null
        """)
        with pytest.raises(ConfigError, match="unknown key"):
            load_config(cfg_file)

    def test_empty_file(self, tmp_path):
        cfg_file = write(tmp_path / "empty.yaml", "")
        cfg = load_config(cfg_file)
        assert cfg.actions == {}
        assert cfg.device.port is None
        assert cfg.device.baud == DEFAULT_BAUD
        assert cfg.device.open_delay_s == DEFAULT_OPEN_DELAY_S

    def test_missing_device_section(self, tmp_path):
        cfg_file = write(tmp_path / "c.yaml", """
            actions:
              unlock:
                - tap: international3
        """)
        cfg = load_config(cfg_file)
        assert cfg.device.port is None
        assert cfg.device.baud == DEFAULT_BAUD

    def test_missing_actions_section(self, tmp_path):
        cfg_file = write(tmp_path / "c.yaml", """
            device:
              baud: 115200
        """)
        cfg = load_config(cfg_file)
        assert cfg.actions == {}

    def test_invalid_yaml_raises(self, tmp_path):
        cfg_file = write(tmp_path / "c.yaml", "device: {bad: [")
        with pytest.raises(ConfigError, match="YAML parse error"):
            load_config(cfg_file)

    def test_top_level_must_be_mapping(self, tmp_path):
        cfg_file = write(tmp_path / "c.yaml", "- just a list\n")
        with pytest.raises(ConfigError, match="top-level must be a mapping"):
            load_config(cfg_file)

    def test_baud_must_be_positive_int(self, tmp_path):
        cfg_file = write(tmp_path / "c.yaml", """
            device:
              baud: -1
        """)
        with pytest.raises(ConfigError, match="positive integer"):
            load_config(cfg_file)

    def test_action_must_be_list(self, tmp_path):
        cfg_file = write(tmp_path / "c.yaml", """
            actions:
              unlock: not_a_list
        """)
        with pytest.raises(ConfigError, match="must be a list of steps"):
            load_config(cfg_file)

    def test_step_must_be_single_key_mapping(self, tmp_path):
        cfg_file = write(tmp_path / "c.yaml", """
            actions:
              broken:
                - tap: a
                  press: b
        """)
        with pytest.raises(ConfigError, match="single-key mapping"):
            load_config(cfg_file)

    def test_unknown_step_op_rejected(self, tmp_path):
        cfg_file = write(tmp_path / "c.yaml", """
            actions:
              broken:
                - smash: international3
        """)
        with pytest.raises(ConfigError, match="unknown step type"):
            load_config(cfg_file)

    def test_snake_case_step_op_rejected(self, tmp_path):
        # Same reasoning as the device-section test: silent ignore is worse
        # than a hard error.
        cfg_file = write(tmp_path / "c.yaml", """
            actions:
              slow:
                - delay_ms: 200
        """)
        with pytest.raises(ConfigError, match="unknown step type"):
            load_config(cfg_file)

    def test_no_config_anywhere_returns_empty(self, monkeypatch, tmp_path):
        monkeypatch.delenv(CONFIG_ENV_VAR, raising=False)
        cfg = load_config(None)
        assert isinstance(cfg, Config)

    def test_release_all_step(self, tmp_path):
        cfg_file = write(tmp_path / "c.yaml", """
            actions:
              panic:
                - release-all: true
        """)
        cfg = load_config(cfg_file)
        assert cfg.actions["panic"] == [{"release-all": True}]

    def test_delay_ms_step(self, tmp_path):
        cfg_file = write(tmp_path / "c.yaml", """
            actions:
              slow:
                - press: shift
                - delay-ms: 200
                - release: shift
        """)
        cfg = load_config(cfg_file)
        assert cfg.actions["slow"][1] == {"delay-ms": 200}

    def test_kebab_case_action_name_allowed(self, tmp_path):
        # Action names are user-defined identifiers — kebab-case
        # encouraged but not enforced.
        cfg_file = write(tmp_path / "c.yaml", """
            actions:
              long-shift:
                - press: shift
                - delay-ms: 500
                - release: shift
        """)
        cfg = load_config(cfg_file)
        assert "long-shift" in cfg.actions
