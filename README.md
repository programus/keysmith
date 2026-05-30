# KeySmith

A USB HID keyboard relay: a Pro Micro firmware plus a host CLI that turns
YAML-defined key sequences into real keystrokes — driven over serial.

## Why

Software-injected keystrokes (CGEventPost, AppleScript `key code`, etc.) on
macOS bypass the IOKit HID layer that tools like Karabiner-Elements hook
into. KeySmith solves this by routing keystrokes through real USB HID
hardware — so they look identical to a physical keyboard to the OS.

## Architecture

```
┌──────────────┐   serial   ┌──────────────┐   USB HID  ┌──────────┐
│  host CLI    │ ─────────> │  Pro Micro   │ ─────────> │  macOS   │
│  (Python)    │            │  firmware    │            │          │
│  reads YAML  │            │  (C++/AVR)   │            │          │
└──────────────┘            └──────────────┘            └──────────┘
```

- `firmware/` — PlatformIO project for SparkFun Pro Micro / Arduino Leonardo
  (ATmega32U4). Burned once; speaks a tiny binary protocol over USB serial.
- `host/` — Python CLI that reads YAML action definitions and drives the
  firmware. Designed to be invoked from scripts, AI agents, or the shell.
- `examples/` — Example YAML configs.

## Status

🚧 Early development. Firmware protocol design in progress.

## License

MIT — see [LICENSE](LICENSE).
