"""KeySmith host CLI — drives a Pro Micro firmware over USB serial.

Public API:
    Protocol            — low-level serial wire protocol
    KeySmithError       — base exception
    PingFailedError     — board did not respond to PING
    UnknownKeyError     — key alias not in keymap
    Config              — parsed YAML config
    discover_port       — find a KeySmith board by PING

The CLI entry point is `keysmith.cli:app` (typer).
"""

from keysmith.protocol import (
    Protocol,
    KeySmithError,
    PingFailedError,
)
from keysmith.keymap import (
    UnknownKeyError,
    resolve_key,
    KEYMAP,
)
from keysmith.config import Config, ConfigError, load_config
from keysmith.discovery import discover_port

__version__ = "0.1.0"
PROTOCOL_VERSION = 1

__all__ = [
    "Protocol",
    "KeySmithError",
    "PingFailedError",
    "UnknownKeyError",
    "resolve_key",
    "KEYMAP",
    "Config",
    "ConfigError",
    "load_config",
    "discover_port",
    "__version__",
    "PROTOCOL_VERSION",
]
