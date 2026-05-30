"""Tests for keysmith.cli — typer CliRunner with mocked Protocol & discovery."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import List, Optional

import pytest
from typer.testing import CliRunner

from keysmith.cli import app
from keysmith.protocol import KeySmithError, PingFailedError


runner = CliRunner()


def _err(result) -> str:
    """Newer Click/Typer merges stderr into stdout. This helper makes
    intent clear at call sites — we're checking error text, regardless
    of which stream it landed in."""
    # If stderr is separately captured (older Click), use it; else fall
    # back to combined output.
    try:
        return result.stderr  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        return result.output


# ---- Test doubles -----------------------------------------------------


class FakeProto:
    """Minimal stand-in for keysmith.protocol.Protocol for CLI tests.

    Instances are created by `proto_factory` (a fixture). Each instance
    records calls and can be configured to fail at specific points to
    exercise error paths.
    """

    def __init__(self, port: str, **kwargs):
        self.port = port
        self.kwargs = kwargs
        self.calls: List[tuple] = []
        # Failure injection knobs (set by tests via the factory).
        self.fail_on: Optional[str] = None
        self.fail_with: Exception = KeySmithError("boom")
        self.ping_version: int = 1
        # Marker: factory swaps in this template's fail config when set.
        self._template: bool = False

    # -- pyserial-shaped lifecycle --
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    # -- protocol primitives --
    def _maybe_fail(self, op: str):
        if self.fail_on == op:
            raise self.fail_with

    def press(self, code):
        self.calls.append(("press", code))
        self._maybe_fail("press")

    def release(self, code):
        self.calls.append(("release", code))
        self._maybe_fail("release")

    def tap(self, code):
        self.calls.append(("tap", code))
        self._maybe_fail("tap")

    def release_all(self):
        self.calls.append(("release_all",))
        self._maybe_fail("release_all")

    def ping(self):
        self.calls.append(("ping",))
        self._maybe_fail("ping")
        return self.ping_version


@pytest.fixture
def proto_factory(monkeypatch):
    """Patch cli's _open_protocol to return controllable FakeProto instances."""
    instances: List[FakeProto] = []

    def _factory(port, cfg_device):
        fake = FakeProto(port, baud=cfg_device.baud, open_delay_s=cfg_device.open_delay_s)
        if instances and getattr(instances[-1], "_template", False):
            # Copy failure config from the template the test set up.
            template = instances.pop()
            fake.fail_on = template.fail_on
            fake.fail_with = template.fail_with
            fake.ping_version = template.ping_version
        instances.append(fake)
        return fake

    monkeypatch.setattr("keysmith.cli._open_protocol", _factory)
    return instances


@pytest.fixture
def discover_stub(monkeypatch):
    """Patch cli.discover_port to return a deterministic value or raise."""
    state = {"return": "/dev/discovered", "raise": None, "calls": []}

    def _discover(**kwargs):
        state["calls"].append(kwargs)
        if state["raise"] is not None:
            raise state["raise"]
        return state["return"]

    monkeypatch.setattr("keysmith.cli.discover_port", _discover)
    return state


@pytest.fixture
def empty_config_env(monkeypatch, tmp_path):
    """Isolate the test from any real config files in the user's home."""
    monkeypatch.delenv("KEYSMITH_CONFIG_FILE", raising=False)
    # Steer XDG_CONFIG_HOME to an empty tmp dir so no real config picked up.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def write_config(tmp_path: Path, body: str) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(dedent(body), encoding="utf-8")
    return cfg


# ---- version & basic plumbing -----------------------------------------


class TestVersion:
    def test_prints_version(self, empty_config_env):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "keysmith" in result.stdout

    def test_no_args_shows_help(self, empty_config_env):
        result = runner.invoke(app, [])
        assert result.exit_code in (0, 2)
        assert "Usage" in result.stdout or "Usage" in _err(result)


# ---- ping --------------------------------------------------------------


class TestPing:
    def test_success(self, empty_config_env, proto_factory, discover_stub):
        result = runner.invoke(app, ["ping"])
        assert result.exit_code == 0, _err(result)
        assert "OK" in result.stdout
        assert "/dev/discovered" in result.stdout

    def test_explicit_port_skips_discovery(
        self, empty_config_env, proto_factory, discover_stub
    ):
        result = runner.invoke(app, ["ping", "--port", "/dev/explicit"])
        assert result.exit_code == 0
        assert "/dev/explicit" in result.stdout
        assert discover_stub["calls"] == []

    def test_ping_failure_exit_1(
        self, empty_config_env, proto_factory, discover_stub
    ):
        template = FakeProto("/dev/x")
        template._template = True
        template.fail_on = "ping"
        template.fail_with = PingFailedError("no reply")
        proto_factory.append(template)

        result = runner.invoke(app, ["ping"])
        assert result.exit_code == 1
        assert "PING failed" in _err(result)

    def test_discovery_failure_exit_2(
        self, empty_config_env, proto_factory, discover_stub
    ):
        discover_stub["raise"] = KeySmithError("no candidates")
        result = runner.invoke(app, ["ping"])
        assert result.exit_code == 2
        assert "no candidates" in _err(result)


# ---- list -------------------------------------------------------------


class TestList:
    def test_no_config_warns_exit_1(self, empty_config_env):
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 1
        assert "No config" in _err(result)

    def test_empty_actions(self, empty_config_env, tmp_path):
        cfg = write_config(tmp_path, "device: {}\n")
        result = runner.invoke(app, ["list", "--config", str(cfg)])
        assert result.exit_code == 0
        assert "no actions defined" in result.stdout

    def test_lists_actions(self, empty_config_env, tmp_path):
        cfg = write_config(tmp_path, """
            actions:
              unlock:
                - tap: international3
              long-shift:
                - press: shift
                - delay-ms: 500
                - release: shift
              panic:
                - release-all: true
        """)
        result = runner.invoke(app, ["list", "--config", str(cfg)])
        assert result.exit_code == 0
        assert "unlock" in result.stdout
        assert "long-shift" in result.stdout
        assert "panic" in result.stdout
        # P1.1 fix verification: kebab-case used, snake_case absent.
        assert "release-all" in result.stdout
        assert "release_all" not in result.stdout


# ---- tap --------------------------------------------------------------


class TestTap:
    def test_alias(self, empty_config_env, proto_factory, discover_stub):
        result = runner.invoke(app, ["tap", "right_shift"])
        assert result.exit_code == 0
        assert "0xE5" in result.stdout

    def test_hex_code(self, empty_config_env, proto_factory, discover_stub):
        result = runner.invoke(app, ["tap", "0x89"])
        assert result.exit_code == 0
        assert "0x89" in result.stdout

    def test_unknown_key_exit_2(self, empty_config_env, proto_factory, discover_stub):
        result = runner.invoke(app, ["tap", "totally-not-a-key"])
        assert result.exit_code == 2
        assert "key error" in _err(result)


# ---- run --------------------------------------------------------------


class TestRun:
    def test_unknown_action_exit_2(
        self, empty_config_env, proto_factory, discover_stub, tmp_path
    ):
        cfg = write_config(tmp_path, """
            actions:
              foo:
                - tap: a
        """)
        result = runner.invoke(app, ["run", "bar", "--config", str(cfg)])
        assert result.exit_code == 2
        assert "unknown action" in _err(result)
        assert "foo" in _err(result)

    def test_simple_action_executes(
        self, empty_config_env, proto_factory, discover_stub, tmp_path
    ):
        cfg = write_config(tmp_path, """
            actions:
              shout:
                - press: shift
                - tap: a
                - release: shift
        """)
        result = runner.invoke(app, ["run", "shout", "--config", str(cfg)])
        assert result.exit_code == 0, _err(result)
        fake = proto_factory[-1]
        ops = [c[0] for c in fake.calls]
        assert ops == ["press", "tap", "release"]

    def test_release_all_step(
        self, empty_config_env, proto_factory, discover_stub, tmp_path
    ):
        cfg = write_config(tmp_path, """
            actions:
              panic:
                - release-all: true
        """)
        result = runner.invoke(app, ["run", "panic", "--config", str(cfg)])
        assert result.exit_code == 0, _err(result)
        fake = proto_factory[-1]
        assert ("release_all",) in fake.calls

    def test_failure_midsequence_calls_release_all(
        self, empty_config_env, proto_factory, discover_stub, tmp_path
    ):
        # P1.3 guard: a step failure mid-sequence must trigger best-effort
        # release_all() so a held key isn't stranded.
        template = FakeProto("/dev/x")
        template._template = True
        template.fail_on = "release"
        template.fail_with = KeySmithError("usb went away")
        proto_factory.append(template)

        cfg = write_config(tmp_path, """
            actions:
              shout:
                - press: shift
                - tap: a
                - release: shift
        """)
        result = runner.invoke(app, ["run", "shout", "--config", str(cfg)])
        assert result.exit_code == 1
        assert "runtime error" in _err(result)

        fake = proto_factory[-1]
        assert ("release_all",) in fake.calls

    def test_delay_ms_validation(
        self, empty_config_env, proto_factory, discover_stub, tmp_path
    ):
        cfg = write_config(tmp_path, """
            actions:
              broken:
                - delay-ms: -100
        """)
        result = runner.invoke(app, ["run", "broken", "--config", str(cfg)])
        assert result.exit_code == 1
        assert "delay-ms" in _err(result)

    def test_delay_seconds_step_runs(
        self, empty_config_env, proto_factory, discover_stub, tmp_path
    ):
        # The new `delay` step takes seconds (float). Use 0.0 to avoid
        # making the test slow — we only care that it parses and dispatches.
        cfg = write_config(tmp_path, """
            actions:
              fast:
                - tap: a
                - delay: 0.0
                - tap: b
        """)
        result = runner.invoke(app, ["run", "fast", "--config", str(cfg)])
        assert result.exit_code == 0, _err(result)
        fake = proto_factory[-1]
        # Both taps must have fired around the delay.
        ops = [c[0] for c in fake.calls]
        assert ops.count("tap") == 2

    def test_delay_seconds_validation_negative(
        self, empty_config_env, proto_factory, discover_stub, tmp_path
    ):
        cfg = write_config(tmp_path, """
            actions:
              broken:
                - delay: -0.5
        """)
        result = runner.invoke(app, ["run", "broken", "--config", str(cfg)])
        assert result.exit_code == 1
        assert "delay" in _err(result)

    def test_delay_seconds_validation_string(
        self, empty_config_env, proto_factory, discover_stub, tmp_path
    ):
        cfg = write_config(tmp_path, """
            actions:
              broken:
                - delay: "soon"
        """)
        result = runner.invoke(app, ["run", "broken", "--config", str(cfg)])
        assert result.exit_code == 1
        assert "delay" in _err(result)

    def test_delay_seconds_actually_sleeps(
        self, empty_config_env, proto_factory, discover_stub, tmp_path, monkeypatch
    ):
        # Verify `delay: <float>` reaches time.sleep with the right value
        # (not e.g. divided by 1000 like delay-ms).
        slept = []
        import keysmith.cli
        monkeypatch.setattr(keysmith.cli.time, "sleep", lambda s: slept.append(s))
        cfg = write_config(tmp_path, """
            actions:
              wait:
                - delay: 1.5
        """)
        result = runner.invoke(app, ["run", "wait", "--config", str(cfg)])
        assert result.exit_code == 0, _err(result)
        assert 1.5 in slept

    def test_delay_ms_legacy_actually_sleeps(
        self, empty_config_env, proto_factory, discover_stub, tmp_path, monkeypatch
    ):
        # Lock in that the legacy `delay-ms: <int>` still divides by 1000.
        slept = []
        import keysmith.cli
        monkeypatch.setattr(keysmith.cli.time, "sleep", lambda s: slept.append(s))
        cfg = write_config(tmp_path, """
            actions:
              wait:
                - delay-ms: 250
        """)
        result = runner.invoke(app, ["run", "wait", "--config", str(cfg)])
        assert result.exit_code == 0, _err(result)
        assert 0.25 in slept

    def test_kebab_case_key_alias_in_action(
        self, empty_config_env, proto_factory, discover_stub, tmp_path
    ):
        # The README documents kebab-case key aliases (right-shift, page-up).
        # Make sure such configs actually run end-to-end through the keymap
        # normalizer.
        cfg = write_config(tmp_path, """
            actions:
              modifier-test:
                - tap: right-shift
                - tap: page-up
        """)
        result = runner.invoke(app, ["run", "modifier-test", "--config", str(cfg)])
        assert result.exit_code == 0, _err(result)
        fake = proto_factory[-1]
        # right-shift = 0xE5, page-up = 0x4B.
        codes = [c[1] for c in fake.calls if c[0] == "tap"]
        assert 0xE5 in codes
        assert 0x4B in codes


# ---- release-all command (separate from step) -------------------------


class TestReleaseAllCommand:
    def test_success(self, empty_config_env, proto_factory, discover_stub):
        result = runner.invoke(app, ["release-all"])
        assert result.exit_code == 0
        assert "released" in result.stdout
        fake = proto_factory[-1]
        assert ("release_all",) in fake.calls


# ---- Config precedence ------------------------------------------------


class TestConfigPrecedence:
    def test_explicit_config_overrides_env(
        self, empty_config_env, proto_factory, discover_stub, tmp_path, monkeypatch
    ):
        explicit = write_config(tmp_path, """
            actions:
              from_explicit:
                - tap: a
        """)
        env_path = tmp_path / "env_config.yaml"
        env_path.write_text("actions:\n  from_env:\n    - tap: b\n")
        monkeypatch.setenv("KEYSMITH_CONFIG_FILE", str(env_path))

        result = runner.invoke(app, ["list", "--config", str(explicit)])
        assert result.exit_code == 0
        assert "from_explicit" in result.stdout
        assert "from_env" not in result.stdout

    def test_env_var_used_when_no_cli_flag(
        self, empty_config_env, tmp_path, monkeypatch
    ):
        env_path = write_config(tmp_path, """
            actions:
              from_env:
                - tap: a
        """)
        monkeypatch.setenv("KEYSMITH_CONFIG_FILE", str(env_path))

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "from_env" in result.stdout

    def test_port_flag_overrides_config(
        self, empty_config_env, proto_factory, discover_stub, tmp_path
    ):
        cfg = write_config(tmp_path, """
            device:
              port: /dev/from-config
        """)
        result = runner.invoke(
            app, ["ping", "--config", str(cfg), "--port", "/dev/from-flag"],
        )
        assert result.exit_code == 0
        assert "/dev/from-flag" in result.stdout
        assert "/dev/from-config" not in result.stdout
