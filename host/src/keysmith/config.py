"""YAML configuration loading with layered precedence.

Lookup order (highest precedence first):
    1. CLI flag: --config <path>
    2. Environment: $KEYSMITH_CONFIG_FILE
    3. XDG: ~/.config/keysmith/config.yaml
    4. Legacy: ~/.keysmith.yaml

The config file is required for `keysmith run` (which needs an action
table), but optional for ad-hoc commands like `keysmith ping` or
`keysmith tap` that take their parameters on the command line.

Schema (YAML keys use kebab-case throughout):

    device:
      port: /dev/cu.usbmodem*    # optional — autodiscovered if omitted
      baud: 115200               # optional — default 115200
      open-delay-s: 0.05         # optional — see DeviceConfig.open_delay_s

    actions:
      <action-name>:
        - press: <key>           # press without release
        - release: <key>         # release a previously pressed key
        - tap: <key>             # press + brief hold + release
        - delay-ms: <int>        # sleep N milliseconds
        - release-all: true      # safety reset
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml


CONFIG_ENV_VAR = "KEYSMITH_CONFIG_FILE"
XDG_CONFIG_PATH = Path.home() / ".config" / "keysmith" / "config.yaml"
LEGACY_CONFIG_PATH = Path.home() / ".keysmith.yaml"

DEFAULT_BAUD = 115200
DEFAULT_OPEN_DELAY_S = 0.05


class ConfigError(Exception):
    """Raised when the config file is missing, malformed, or invalid."""


# ---- Action step types (validated, not parsed into rich objects) ------
#
# A step is a single-key dict. We keep them as raw dicts here and let the
# CLI layer translate to Protocol calls — this keeps the config layer
# free of pyserial / runtime dependencies for easy testing.
#
# YAML keys arrive in kebab-case (e.g. "delay-ms") and are kept verbatim
# here so the executor (cli._execute_step) can dispatch on them. We do
# not silently rewrite to snake_case to avoid hiding typos.

Step = Dict[str, Any]


@dataclass(frozen=True)
class DeviceConfig:
    port: Optional[str] = None  # None -> autodiscover
    baud: int = DEFAULT_BAUD
    # Seconds to wait after opening the serial port before talking to
    # the board. 0.05 is enough for typical third-party Pro Micro
    # clones; bump to ~2.0 if you have a stock SparkFun Pro Micro or
    # Arduino Leonardo whose Caterina bootloader resets on DTR toggle.
    open_delay_s: float = DEFAULT_OPEN_DELAY_S


@dataclass(frozen=True)
class Config:
    device: DeviceConfig = field(default_factory=DeviceConfig)
    actions: Dict[str, List[Step]] = field(default_factory=dict)
    source: Optional[Path] = None  # path the config was loaded from

    def has_action(self, name: str) -> bool:
        return name in self.actions

    def list_actions(self) -> List[str]:
        return sorted(self.actions.keys())


# ---- Resolution -------------------------------------------------------


def resolve_config_path(explicit: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """Resolve which config file to use, applying precedence order.

    Returns None if no config file is found at any standard location.
    Raises ConfigError if `explicit` (or $KEYSMITH_CONFIG_FILE) points
    to a file that does not exist — explicit > implicit.
    """
    if explicit is not None:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ConfigError(f"--config path does not exist: {path}")
        return path

    env = os.environ.get(CONFIG_ENV_VAR)
    if env:
        path = Path(env).expanduser()
        if not path.is_file():
            raise ConfigError(
                f"${CONFIG_ENV_VAR} points to non-existent file: {path}"
            )
        return path

    if XDG_CONFIG_PATH.is_file():
        return XDG_CONFIG_PATH
    if LEGACY_CONFIG_PATH.is_file():
        return LEGACY_CONFIG_PATH
    return None


# ---- Loading & validation ---------------------------------------------


def load_config(explicit: Optional[Union[str, Path]] = None) -> Config:
    """Load + validate config from the highest-precedence source.

    Returns an empty Config (no actions, no port) if no config file
    exists at any standard location and `explicit` is None.
    """
    path = resolve_config_path(explicit)
    if path is None:
        return Config()

    try:
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as err:
        raise ConfigError(f"YAML parse error in {path}: {err}") from err
    except OSError as err:
        raise ConfigError(f"Could not read {path}: {err}") from err

    return _build_config(raw, source=path)


def _build_config(raw: Any, *, source: Path) -> Config:
    if raw is None:
        return Config(source=source)
    if not isinstance(raw, dict):
        raise ConfigError(
            f"{source}: top-level must be a mapping, got {type(raw).__name__}"
        )
    _reject_unknown_keys(raw, {"device", "actions"}, ctx="top-level", source=source)

    device = _build_device(raw.get("device"), source=source)
    actions = _build_actions(raw.get("actions"), source=source)
    return Config(device=device, actions=actions, source=source)


_DEVICE_KEYS = {"port", "baud", "open-delay-s"}


def _build_device(raw: Any, *, source: Path) -> DeviceConfig:
    if raw is None:
        return DeviceConfig()
    if not isinstance(raw, dict):
        raise ConfigError(
            f"{source}: 'device' must be a mapping, got {type(raw).__name__}"
        )
    _reject_unknown_keys(raw, _DEVICE_KEYS, ctx="device", source=source)

    port = raw.get("port")
    if port is not None and not isinstance(port, str):
        raise ConfigError(f"{source}: device.port must be a string")

    baud = raw.get("baud", DEFAULT_BAUD)
    if not isinstance(baud, int) or isinstance(baud, bool) or baud <= 0:
        raise ConfigError(f"{source}: device.baud must be a positive integer")

    open_delay = raw.get("open-delay-s", DEFAULT_OPEN_DELAY_S)
    if isinstance(open_delay, bool) or not isinstance(open_delay, (int, float)):
        raise ConfigError(
            f"{source}: device.open-delay-s must be a non-negative number"
        )
    if open_delay < 0:
        raise ConfigError(
            f"{source}: device.open-delay-s must be non-negative, got {open_delay}"
        )

    return DeviceConfig(port=port, baud=baud, open_delay_s=float(open_delay))


# Step type names as they appear in YAML (kebab-case).
_VALID_STEP_KEYS = {"press", "release", "tap", "delay-ms", "release-all"}


def _build_actions(raw: Any, *, source: Path) -> Dict[str, List[Step]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(
            f"{source}: 'actions' must be a mapping, got {type(raw).__name__}"
        )
    out: Dict[str, List[Step]] = {}
    for name, steps in raw.items():
        if not isinstance(name, str):
            raise ConfigError(f"{source}: action name must be a string, got {name!r}")
        if not isinstance(steps, list):
            raise ConfigError(
                f"{source}: action '{name}' must be a list of steps"
            )
        validated: List[Step] = []
        for i, step in enumerate(steps):
            if not isinstance(step, dict) or len(step) != 1:
                raise ConfigError(
                    f"{source}: action '{name}' step {i}: must be a single-key "
                    f"mapping like {{tap: <key>}}, got {step!r}"
                )
            key = next(iter(step))
            if key not in _VALID_STEP_KEYS:
                raise ConfigError(
                    f"{source}: action '{name}' step {i}: unknown step type "
                    f"'{key}'. Valid: {sorted(_VALID_STEP_KEYS)}"
                )
            validated.append(step)
        out[name] = validated
    return out


def _reject_unknown_keys(
    mapping: Dict[str, Any],
    allowed: set,
    *,
    ctx: str,
    source: Path,
) -> None:
    """Raise ConfigError if `mapping` contains keys outside `allowed`.

    This catches typos like `open_delay_s:` (snake_case) when
    `open-delay-s:` is expected — without this, YAML would silently
    ignore the unknown key and the user would wonder why their config
    has no effect.
    """
    extra = set(mapping) - allowed
    if extra:
        # Friendliest order: alphabetical for stable error messages.
        bad = ", ".join(repr(k) for k in sorted(extra))
        wanted = ", ".join(repr(k) for k in sorted(allowed))
        raise ConfigError(
            f"{source}: unknown key(s) in {ctx}: {bad}. "
            f"Allowed: {wanted}. (Note: keys use kebab-case, e.g. "
            f"'open-delay-s' not 'open_delay_s'.)"
        )
