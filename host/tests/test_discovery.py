"""Tests for keysmith.discovery — fully mocked, no real board needed.

We mock both `serial.tools.list_ports.comports` (to control candidate
enumeration) and `Protocol` (to control which "boards" reply to PING).
"""

from __future__ import annotations

from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

from keysmith.discovery import (
    KNOWN_VID_PIDS,
    discover_port,
    list_candidates,
)
from keysmith.protocol import KeySmithError, PingFailedError


# ---- Fake comports entries --------------------------------------------


class FakePortInfo:
    """Mimics serial.tools.list_ports_common.ListPortInfo."""

    def __init__(
        self,
        device: str,
        vid: Optional[int] = None,
        pid: Optional[int] = None,
    ) -> None:
        self.device = device
        self.vid = vid
        self.pid = pid


@pytest.fixture
def patch_comports(monkeypatch):
    """Replace serial.tools.list_ports.comports with a controllable list."""
    state = {"ports": []}

    def _comports():
        return list(state["ports"])

    monkeypatch.setattr("keysmith.discovery.serial.tools.list_ports.comports", _comports)
    return state


# ---- list_candidates --------------------------------------------------


class TestListCandidates:
    def test_known_vid_pid_match(self, patch_comports):
        # Arduino Leonardo VID/PID — should be picked up regardless of name.
        patch_comports["ports"] = [
            FakePortInfo("/dev/cu.weirdname", vid=0x2341, pid=0x8036),
        ]
        assert list_candidates() == ["/dev/cu.weirdname"]

    def test_macos_usbmodem_fallback(self, patch_comports):
        patch_comports["ports"] = [
            FakePortInfo("/dev/cu.usbmodem8401", vid=0xDEAD, pid=0xBEEF),
        ]
        # Unknown VID/PID, but name matches usbmodem heuristic.
        assert list_candidates() == ["/dev/cu.usbmodem8401"]

    def test_linux_ttyacm_fallback(self, patch_comports):
        patch_comports["ports"] = [
            FakePortInfo("/dev/ttyACM0", vid=0xDEAD, pid=0xBEEF),
        ]
        assert list_candidates() == ["/dev/ttyACM0"]

    def test_linux_ttyusb_fallback(self, patch_comports):
        patch_comports["ports"] = [
            FakePortInfo("/dev/ttyUSB1", vid=0xDEAD, pid=0xBEEF),
        ]
        assert list_candidates() == ["/dev/ttyUSB1"]

    def test_no_vid_pid_with_usbmodem(self, patch_comports):
        # Bluetooth-style port: no VID/PID but device name says usbmodem.
        patch_comports["ports"] = [
            FakePortInfo("/dev/cu.usbmodem-bt", vid=None, pid=None),
        ]
        assert list_candidates() == ["/dev/cu.usbmodem-bt"]

    def test_irrelevant_port_skipped(self, patch_comports):
        patch_comports["ports"] = [
            FakePortInfo("/dev/cu.Bluetooth-Incoming-Port", vid=None, pid=None),
            FakePortInfo("/dev/cu.PrinterSerial", vid=0x0BDA, pid=0x8153),
        ]
        assert list_candidates() == []

    def test_multiple_candidates_ordered(self, patch_comports):
        patch_comports["ports"] = [
            FakePortInfo("/dev/cu.usbmodem8401", vid=0x2341, pid=0x8036),  # known
            FakePortInfo("/dev/cu.usbmodem9999", vid=0xDEAD, pid=0xBEEF),  # heuristic
            FakePortInfo("/dev/cu.SOC", vid=None, pid=None),                # ignored
        ]
        assert list_candidates() == [
            "/dev/cu.usbmodem8401",
            "/dev/cu.usbmodem9999",
        ]

    def test_dedup_same_device_listed_twice(self, patch_comports):
        # Pyserial occasionally reports the same path twice on macOS
        # (e.g. cu.* and tty.* aliases share names sometimes). Defensive
        # dedup keeps probing simple.
        patch_comports["ports"] = [
            FakePortInfo("/dev/cu.usbmodem8401", vid=0x2341, pid=0x8036),
            FakePortInfo("/dev/cu.usbmodem8401", vid=0x2341, pid=0x8036),
        ]
        assert list_candidates() == ["/dev/cu.usbmodem8401"]

    def test_known_vid_pid_takes_priority_over_heuristic(self, patch_comports):
        # If a single port matches both branches, it should appear once.
        patch_comports["ports"] = [
            FakePortInfo("/dev/cu.usbmodem8401", vid=0x2341, pid=0x8036),
        ]
        result = list_candidates()
        assert result == ["/dev/cu.usbmodem8401"]
        # And the dedup applies — only one entry, not two.
        assert len(result) == 1

    def test_known_vid_pids_table_includes_leonardo(self):
        # Sanity check — the known-VID/PID table includes Arduino Leonardo
        # (0x2341, 0x8036) since that's what stock Pro Micro clones report.
        assert (0x2341, 0x8036) in KNOWN_VID_PIDS

    def test_case_insensitive_heuristic(self, patch_comports):
        # Windows-style uppercase names should still match.
        patch_comports["ports"] = [
            FakePortInfo("USBMODEM3", vid=None, pid=None),
        ]
        assert list_candidates() == ["USBMODEM3"]


# ---- discover_port ----------------------------------------------------


class _FakeProto:
    """Fake Protocol context manager for discovery tests.

    `behavior` is a mapping from port path -> "ok" | "ping_fail" | "open_fail"
    """

    def __init__(self, behavior: dict):
        self.behavior = behavior

    def __call__(self, port, **kwargs):
        # Return a per-port instance that respects `behavior`.
        return _FakeProtoInstance(port, self.behavior.get(port, "ok"))


class _FakeProtoInstance:
    def __init__(self, port: str, mode: str):
        self.port = port
        self.mode = mode

    def __enter__(self):
        if self.mode == "open_fail":
            raise OSError(f"could not open {self.port}")
        return self

    def __exit__(self, *_):
        return False

    def ping(self):
        if self.mode == "ping_fail":
            raise PingFailedError(f"no reply from {self.port}")
        return 1


class TestDiscoverPort:
    def test_no_candidates_raises(self, monkeypatch):
        monkeypatch.setattr(
            "keysmith.discovery.list_candidates",
            lambda: [],
        )
        with pytest.raises(KeySmithError, match="No candidate"):
            discover_port()

    def test_first_candidate_succeeds(self, monkeypatch):
        fake = _FakeProto({})  # all default to "ok"
        monkeypatch.setattr("keysmith.discovery.Protocol", fake)
        result = discover_port(candidates=["/dev/a", "/dev/b"])
        assert result == "/dev/a"

    def test_first_fails_second_succeeds(self, monkeypatch):
        fake = _FakeProto({"/dev/a": "ping_fail"})
        monkeypatch.setattr("keysmith.discovery.Protocol", fake)
        result = discover_port(candidates=["/dev/a", "/dev/b"])
        assert result == "/dev/b"

    def test_open_failure_continues_to_next(self, monkeypatch):
        # OSError on open shouldn't crash the search — should move on.
        fake = _FakeProto({"/dev/a": "open_fail"})
        monkeypatch.setattr("keysmith.discovery.Protocol", fake)
        result = discover_port(candidates=["/dev/a", "/dev/b"])
        assert result == "/dev/b"

    def test_all_candidates_fail_raises(self, monkeypatch):
        fake = _FakeProto({
            "/dev/a": "ping_fail",
            "/dev/b": "open_fail",
        })
        monkeypatch.setattr("keysmith.discovery.Protocol", fake)
        with pytest.raises(KeySmithError) as exc_info:
            discover_port(candidates=["/dev/a", "/dev/b"])
        # Error message should mention the probed paths so the user knows
        # what was tried.
        msg = str(exc_info.value)
        assert "/dev/a" in msg
        assert "/dev/b" in msg

    def test_open_delay_passed_through(self, monkeypatch):
        # Verify the open_delay_s arg actually gets passed to Protocol —
        # this guards the P1.2 fix.
        captured: list = []

        class _Capturing:
            def __init__(self, port, **kwargs):
                captured.append(kwargs.get("open_delay_s"))
                self._port = port

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def ping(self):
                return 1

        monkeypatch.setattr("keysmith.discovery.Protocol", _Capturing)
        discover_port(candidates=["/dev/a"], open_delay_s=2.0)
        assert captured == [2.0]

    def test_baud_passed_through(self, monkeypatch):
        captured: list = []

        class _Capturing:
            def __init__(self, port, **kwargs):
                captured.append(kwargs.get("baud"))

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def ping(self):
                return 1

        monkeypatch.setattr("keysmith.discovery.Protocol", _Capturing)
        discover_port(candidates=["/dev/a"], baud=57600)
        assert captured == [57600]
