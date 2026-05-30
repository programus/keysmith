"""Low-level serial wire protocol for KeySmith firmware.

Wire protocol (binary, all bytes literal):

    [0xA5][0x01][hid_code]   PRESS
    [0xA5][0x02][hid_code]   RELEASE
    [0xA5][0x03]             RELEASE_ALL
    [0xA5][0x04]             PING -> board replies [0x5A][version]

The Protocol class is a thin wrapper around pyserial. It owns no policy
(retries, key aliases, action sequences) — that lives in higher layers.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator, Optional

import serial


# Protocol constants (must match firmware/src/main.cpp)
MAGIC: int = 0xA5
REPLY_MAGIC: int = 0x5A

OP_PRESS: int = 0x01
OP_RELEASE: int = 0x02
OP_RELEASE_ALL: int = 0x03
OP_PING: int = 0x04

# Time to wait after opening the serial port before talking to the board.
#
# Some ATmega32U4 boards (notably the official SparkFun Pro Micro and
# Arduino Leonardo with stock Caterina bootloader behaviour) reset on
# DTR toggle and need ~2 seconds for USB re-enumeration before they
# accept commands. Many third-party clones, however, do not exhibit
# this behaviour and respond essentially immediately.
#
# We default to a small but non-zero value that's safe for clones and
# fast for interactive use. If you have a stock SparkFun board and see
# PING failures, bump this up via Protocol(open_delay_s=2.0).
DEFAULT_OPEN_DELAY_S: float = 0.05

# Default tap hold duration. 50ms is well above any HID polling interval
# (1ms standard) but short enough not to feel laggy.
DEFAULT_TAP_HOLD_S: float = 0.05


class KeySmithError(Exception):
    """Base exception for KeySmith host errors."""


class PingFailedError(KeySmithError):
    """The board did not respond to PING with the expected reply."""


class Protocol:
    """USB CDC serial connection to a KeySmith board.

    Use as a context manager to guarantee the port is closed:

        with Protocol("/dev/cu.usbmodem8401") as p:
            p.ping()
            p.tap(0x89)
    """

    def __init__(
        self,
        port: str,
        baud: int = 115200,
        open_delay_s: float = DEFAULT_OPEN_DELAY_S,
        timeout_s: float = 1.0,
    ) -> None:
        self.port = port
        self.baud = baud
        self.open_delay_s = open_delay_s
        self.timeout_s = timeout_s
        self._serial: Optional[serial.Serial] = None

    # ---- lifecycle ----------------------------------------------------

    def open(self) -> None:
        """Open the serial port and wait for the board to settle."""
        if self._serial is not None:
            return
        self._serial = serial.Serial(
            self.port,
            self.baud,
            timeout=self.timeout_s,
        )
        # Wait for Caterina bootloader handoff + USB re-enumeration.
        time.sleep(self.open_delay_s)
        # Drain any stale bytes from the port (boot diagnostics, etc.)
        self._serial.reset_input_buffer()

    def close(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            finally:
                self._serial = None

    def __enter__(self) -> "Protocol":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ---- raw write ----------------------------------------------------

    def _write(self, data: bytes) -> None:
        if self._serial is None:
            raise KeySmithError("Protocol not open; call open() first")
        self._serial.write(data)
        self._serial.flush()

    # ---- protocol primitives -----------------------------------------

    def press(self, hid_code: int) -> None:
        """Press a key (does not release)."""
        _validate_hid(hid_code)
        self._write(bytes([MAGIC, OP_PRESS, hid_code]))

    def release(self, hid_code: int) -> None:
        """Release a previously pressed key."""
        _validate_hid(hid_code)
        self._write(bytes([MAGIC, OP_RELEASE, hid_code]))

    def release_all(self) -> None:
        """Release every key (panic / safety reset)."""
        self._write(bytes([MAGIC, OP_RELEASE_ALL]))

    def tap(self, hid_code: int, hold_s: float = DEFAULT_TAP_HOLD_S) -> None:
        """Press, briefly hold, then release a key."""
        self.press(hid_code)
        time.sleep(hold_s)
        self.release(hid_code)

    def ping(self) -> int:
        """Send PING; return the firmware protocol version.

        Raises PingFailedError on no reply or wrong magic.
        """
        if self._serial is None:
            raise KeySmithError("Protocol not open; call open() first")
        self._serial.reset_input_buffer()
        self._write(bytes([MAGIC, OP_PING]))
        reply = self._serial.read(2)
        if len(reply) != 2:
            raise PingFailedError(
                f"PING got {len(reply)} bytes, expected 2 "
                f"(port={self.port}, raw={reply!r})"
            )
        if reply[0] != REPLY_MAGIC:
            raise PingFailedError(
                f"PING reply magic mismatch: got 0x{reply[0]:02X}, "
                f"expected 0x{REPLY_MAGIC:02X} "
                f"(port={self.port}, raw={reply!r})"
            )
        return reply[1]


# ---- helpers -----------------------------------------------------------


def _validate_hid(code: int) -> None:
    if not isinstance(code, int):
        raise TypeError(f"HID code must be int, got {type(code).__name__}")
    if not (0 <= code <= 0xFF):
        raise ValueError(f"HID code out of byte range: 0x{code:X}")


@contextmanager
def open_protocol(
    port: str,
    baud: int = 115200,
    **kwargs,
) -> Iterator[Protocol]:
    """Convenience: open a Protocol and close it on exit."""
    p = Protocol(port, baud, **kwargs)
    p.open()
    try:
        yield p
    finally:
        p.close()
