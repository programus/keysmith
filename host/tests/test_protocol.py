"""Tests for keysmith.protocol — fully mocked, no real board needed.

We swap out `serial.Serial` with a fake that records every write and
serves canned read replies. This lets us assert exact bytes-on-the-wire
without depending on hardware.
"""

from __future__ import annotations

from typing import List
from unittest.mock import patch

import pytest

from keysmith.protocol import (
    KeySmithError,
    MAGIC,
    OP_PING,
    OP_PRESS,
    OP_RELEASE,
    OP_RELEASE_ALL,
    PingFailedError,
    Protocol,
    REPLY_MAGIC,
    _validate_hid,
)


class FakeSerial:
    """In-memory pyserial.Serial stand-in for protocol tests."""

    def __init__(self, port: str, baud: int = 115200, timeout: float = 1.0) -> None:
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.writes: List[bytes] = []
        self.read_queue: List[bytes] = []
        self.input_buffer_resets: int = 0
        self.flush_count: int = 0
        self.closed: bool = False

    # -- pyserial API surface we use --
    def write(self, data: bytes) -> int:
        if self.closed:
            raise OSError("FakeSerial: writing to closed port")
        self.writes.append(bytes(data))
        return len(data)

    def flush(self) -> None:
        self.flush_count += 1

    def read(self, size: int) -> bytes:
        # Pull canned replies in FIFO order. If the next reply is shorter
        # than `size`, return what we have (mimics pyserial timeout
        # behaviour). If the queue is empty, simulate a timeout (b"").
        if not self.read_queue:
            return b""
        chunk = self.read_queue.pop(0)
        return chunk[:size]

    def reset_input_buffer(self) -> None:
        self.input_buffer_resets += 1

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_serial_factory(monkeypatch):
    """Patch serial.Serial in the protocol module to return our fake.

    Returns a list — the most recently created FakeSerial is appended,
    so tests can grab it as `factory[-1]` after constructing a Protocol.
    """
    instances: List[FakeSerial] = []

    def _factory(*args, **kwargs):
        # pyserial accepts positional (port, baud) or keyword args; we
        # cover both.
        port = args[0] if args else kwargs["port"]
        baud = args[1] if len(args) > 1 else kwargs.get("baudrate", kwargs.get("baud", 115200))
        timeout = kwargs.get("timeout", 1.0)
        fake = FakeSerial(port=port, baud=baud, timeout=timeout)
        instances.append(fake)
        return fake

    monkeypatch.setattr("keysmith.protocol.serial.Serial", _factory)
    return instances


# ---- HID validation ---------------------------------------------------


class TestValidateHid:
    def test_valid_codes(self):
        for code in (0, 1, 0x89, 0xE5, 0xFF):
            _validate_hid(code)

    def test_out_of_range_high(self):
        with pytest.raises(ValueError):
            _validate_hid(0x100)

    def test_out_of_range_negative(self):
        with pytest.raises(ValueError):
            _validate_hid(-1)

    def test_wrong_type(self):
        with pytest.raises(TypeError):
            _validate_hid("a")  # type: ignore[arg-type]


# ---- Open / close lifecycle -------------------------------------------


class TestLifecycle:
    def test_open_uses_configured_baud_and_timeout(self, fake_serial_factory):
        p = Protocol("/dev/fake", baud=57600, open_delay_s=0.0, timeout_s=2.5)
        with p:
            fake = fake_serial_factory[-1]
            assert fake.port == "/dev/fake"
            assert fake.baud == 57600
            assert fake.timeout == 2.5

    def test_open_drains_input_buffer(self, fake_serial_factory):
        with Protocol("/dev/fake", open_delay_s=0.0):
            fake = fake_serial_factory[-1]
            # open() should drain stale bytes once.
            assert fake.input_buffer_resets >= 1

    def test_open_delay_respected(self, fake_serial_factory, monkeypatch):
        # Verify open_delay_s actually drives time.sleep.
        sleeps: List[float] = []
        monkeypatch.setattr("keysmith.protocol.time.sleep", lambda s: sleeps.append(s))
        with Protocol("/dev/fake", open_delay_s=0.123):
            pass
        assert 0.123 in sleeps

    def test_double_open_is_idempotent(self, fake_serial_factory):
        p = Protocol("/dev/fake", open_delay_s=0.0)
        p.open()
        p.open()
        try:
            # Only one underlying Serial should be created.
            assert len(fake_serial_factory) == 1
        finally:
            p.close()

    def test_close_idempotent(self, fake_serial_factory):
        p = Protocol("/dev/fake", open_delay_s=0.0)
        p.open()
        p.close()
        p.close()  # second close is a no-op, must not raise

    def test_context_manager_closes(self, fake_serial_factory):
        with Protocol("/dev/fake", open_delay_s=0.0):
            fake = fake_serial_factory[-1]
        assert fake.closed is True

    def test_write_before_open_raises(self):
        p = Protocol("/dev/fake")
        with pytest.raises(KeySmithError, match="not open"):
            p.press(0x04)

    def test_ping_before_open_raises(self):
        p = Protocol("/dev/fake")
        with pytest.raises(KeySmithError, match="not open"):
            p.ping()


# ---- Wire-format ------------------------------------------------------


class TestWireFormat:
    def test_press_writes_magic_op_code(self, fake_serial_factory):
        with Protocol("/dev/fake", open_delay_s=0.0) as p:
            p.press(0x89)
            fake = fake_serial_factory[-1]
            assert fake.writes == [bytes([MAGIC, OP_PRESS, 0x89])]

    def test_release_writes_magic_op_code(self, fake_serial_factory):
        with Protocol("/dev/fake", open_delay_s=0.0) as p:
            p.release(0xE5)
            fake = fake_serial_factory[-1]
            assert fake.writes == [bytes([MAGIC, OP_RELEASE, 0xE5])]

    def test_release_all_writes_two_bytes(self, fake_serial_factory):
        with Protocol("/dev/fake", open_delay_s=0.0) as p:
            p.release_all()
            fake = fake_serial_factory[-1]
            # No HID code on release_all — just MAGIC + OP.
            assert fake.writes == [bytes([MAGIC, OP_RELEASE_ALL])]

    def test_tap_writes_press_then_release(self, fake_serial_factory, monkeypatch):
        # Skip the hold delay to keep the test instant.
        monkeypatch.setattr("keysmith.protocol.time.sleep", lambda _s: None)
        with Protocol("/dev/fake", open_delay_s=0.0) as p:
            p.tap(0x89)
            fake = fake_serial_factory[-1]
            assert fake.writes == [
                bytes([MAGIC, OP_PRESS, 0x89]),
                bytes([MAGIC, OP_RELEASE, 0x89]),
            ]

    def test_each_write_flushed(self, fake_serial_factory):
        with Protocol("/dev/fake", open_delay_s=0.0) as p:
            p.press(0x04)
            p.release(0x04)
            p.release_all()
            fake = fake_serial_factory[-1]
            assert fake.flush_count == 3

    def test_press_rejects_invalid_hid(self, fake_serial_factory):
        with Protocol("/dev/fake", open_delay_s=0.0) as p:
            with pytest.raises(ValueError):
                p.press(0x100)
            fake = fake_serial_factory[-1]
            # Nothing should have been written if validation rejected.
            assert fake.writes == []


# ---- Ping path --------------------------------------------------------


class TestPing:
    def test_ping_success_returns_version(self, fake_serial_factory):
        with Protocol("/dev/fake", open_delay_s=0.0) as p:
            fake = fake_serial_factory[-1]
            fake.read_queue.append(bytes([REPLY_MAGIC, 0x01]))
            assert p.ping() == 0x01
            assert fake.writes[-1] == bytes([MAGIC, OP_PING])

    def test_ping_returns_arbitrary_version(self, fake_serial_factory):
        with Protocol("/dev/fake", open_delay_s=0.0) as p:
            fake = fake_serial_factory[-1]
            fake.read_queue.append(bytes([REPLY_MAGIC, 0x07]))
            assert p.ping() == 7

    def test_ping_short_reply_raises(self, fake_serial_factory):
        with Protocol("/dev/fake", open_delay_s=0.0) as p:
            fake = fake_serial_factory[-1]
            fake.read_queue.append(bytes([REPLY_MAGIC]))  # only 1 byte
            with pytest.raises(PingFailedError, match="expected 2"):
                p.ping()

    def test_ping_no_reply_raises(self, fake_serial_factory):
        with Protocol("/dev/fake", open_delay_s=0.0) as p:
            # No queued reply — read returns b""
            with pytest.raises(PingFailedError, match="expected 2"):
                p.ping()

    def test_ping_wrong_magic_raises(self, fake_serial_factory):
        with Protocol("/dev/fake", open_delay_s=0.0) as p:
            fake = fake_serial_factory[-1]
            fake.read_queue.append(bytes([0xFF, 0x01]))
            with pytest.raises(PingFailedError, match="magic mismatch"):
                p.ping()

    def test_ping_drains_input_before_request(self, fake_serial_factory):
        with Protocol("/dev/fake", open_delay_s=0.0) as p:
            fake = fake_serial_factory[-1]
            resets_after_open = fake.input_buffer_resets
            fake.read_queue.append(bytes([REPLY_MAGIC, 0x01]))
            p.ping()
            # ping() must reset the buffer once before sending its request.
            assert fake.input_buffer_resets == resets_after_open + 1
