"""Auto-discovery of KeySmith boards by USB serial PING.

Scans `/dev/cu.usbmodem*` (and Linux equivalents via pyserial's port
listing), opens each candidate, sends PING, and returns the first port
that replies with the KeySmith REPLY_MAGIC + version byte.

This sidesteps the fragility of hardcoded port names: the trailing
number in `/dev/cu.usbmodem8401` can change across reboots or re-plugs.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

import serial.tools.list_ports

from keysmith.protocol import (
    Protocol,
    PingFailedError,
    KeySmithError,
)


# USB descriptor identifiers we recognise as candidate KeySmith boards.
# The clone Pro Micro reports as Arduino Leonardo (0x2341 / 0x8036), but
# we also accept SparkFun's official Pro Micro VIDs and a generic glob
# match on `usbmodem*` so we don't miss other ATmega32U4 boards.
KNOWN_VID_PIDS: List[tuple[int, int]] = [
    (0x2341, 0x8036),  # Arduino Leonardo
    (0x2341, 0x0036),  # Arduino Leonardo bootloader
    (0x2341, 0x8037),  # Arduino Micro
    (0x2341, 0x0037),  # Arduino Micro bootloader
    (0x1B4F, 0x9205),  # SparkFun Pro Micro 5V/16MHz
    (0x1B4F, 0x9203),  # SparkFun Pro Micro 3.3V/8MHz
]


def list_candidates() -> List[str]:
    """Return device paths that look like a KeySmith board could live on.

    Order-preserving deduplication: a device path appears at most once
    even if it matches multiple heuristic branches. Order is the order
    pyserial reports the ports, which on macOS roughly matches plug
    order — useful for "the first one is most likely the right one"
    intuition during PING probing.
    """
    found: List[str] = []
    seen: set[str] = set()

    def _add(device: Optional[str]) -> None:
        if device and device not in seen:
            seen.add(device)
            found.append(device)

    for p in serial.tools.list_ports.comports():
        device = p.device or ""
        device_lc = device.lower()

        if p.vid is not None and p.pid is not None and (p.vid, p.pid) in KNOWN_VID_PIDS:
            _add(device)
            continue

        # Fallback name heuristics. Cover the common USB-CDC device-name
        # patterns across platforms:
        #   - macOS:   /dev/cu.usbmodem*   (Apple's CDC class)
        #   - Linux:   /dev/ttyACM*        (CDC ACM driver)
        #   - Linux:   /dev/ttyUSB*        (some USB-serial bridges)
        # We match case-insensitively because Windows COM names are
        # uppercase but pyserial reports them as-is.
        if any(token in device_lc for token in ("usbmodem", "ttyacm", "ttyusb")):
            _add(device)

    return found


def discover_port(
    *,
    candidates: Optional[Iterable[str]] = None,
    baud: int = 115200,
    open_delay_s: float = 0.05,
    timeout_s: float = 0.5,
) -> str:
    """Find and return the device path of a responsive KeySmith board.

    If `candidates` is None, scans the system for likely USB CDC ports.
    Probes each in order; the first one to answer PING wins.

    Raises KeySmithError if no candidate responds.
    """
    paths = list(candidates) if candidates is not None else list_candidates()
    if not paths:
        raise KeySmithError(
            "No candidate USB serial ports found. "
            "Is the KeySmith board connected?"
        )

    last_err: Optional[Exception] = None
    for path in paths:
        try:
            with Protocol(
                path,
                baud=baud,
                open_delay_s=open_delay_s,
                timeout_s=timeout_s,
            ) as p:
                p.ping()
                return path
        except (PingFailedError, OSError, KeySmithError) as err:
            last_err = err
            continue

    tried = ", ".join(paths)
    raise KeySmithError(
        f"No KeySmith board responded to PING. Probed: {tried}. "
        f"Last error: {last_err!r}"
    )
