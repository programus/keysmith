# KeySmith host CLI

Python command-line tool that drives the KeySmith Pro Micro firmware
over USB serial.

## Install (development)

This package uses [uv](https://docs.astral.sh/uv/) for dependency
management.

```bash
cd host
uv sync                # creates .venv, installs deps + dev deps
```

Run the CLI from the venv:

```bash
uv run keysmith --help
```

Or install it as a system-wide tool:

```bash
uv tool install .       # exposes `keysmith` on $PATH
keysmith --help
```

## Usage

```bash
# Probe the connected board (auto-discovers /dev/cu.usbmodem*)
keysmith ping

# List actions defined in your config
keysmith list

# Run a named action sequence
keysmith run unlock

# Ad-hoc: tap a single key without needing config
keysmith tap international3
keysmith tap 0x89          # by raw HID code
keysmith tap right_shift

# Emergency: release any held keys
keysmith release-all
```

## Configuration

Lookup precedence (highest first):

1. `--config <path>` CLI flag
2. `$KEYSMITH_CONFIG_FILE` environment variable
3. `~/.config/keysmith/config.yaml`
4. `~/.keysmith.yaml`

See [`../examples/config.yaml`](../examples/config.yaml) for a full example.

YAML keys use **kebab-case** throughout. KeySmith rejects unknown keys
with a helpful error rather than silently ignoring typos — so writing
`open_delay_s` (snake_case) instead of `open-delay-s` will produce a
clear message rather than mysterious "the setting has no effect".

### Schema

```yaml
device:
  port: /dev/cu.usbmodem8401   # optional — auto-discovered if omitted
  baud: 115200                 # optional — default 115200
  open-delay-s: 0.05           # optional — default 0.05; see below

actions:
  <action-name>:
    - press: <key>             # press without release
    - release: <key>           # release a previously pressed key
    - tap: <key>               # press + brief hold + release
    - delay-ms: <int>          # sleep N milliseconds
    - release-all: true        # safety reset
```

### `device.open-delay-s`

Seconds to wait after opening the serial port before talking to the
board. The default of `0.05` works for typical third-party Pro Micro
clones, which don't reset on DTR toggle.

If you have a **stock SparkFun Pro Micro** or **Arduino Leonardo** whose
Caterina bootloader resets on DTR toggle, you may see `PING` failures
with the default. Bump it up:

```yaml
device:
  open-delay-s: 2.0
```

## Key reference

`<key>` accepts any of:

- **Friendly alias** (case-insensitive; `_`, `-`, and space all interchangeable)
- **Hex string** like `0x89`
- **Decimal** `>= 10` like `137` (single digits `0`-`9` always mean the digit-row keys, not raw HID codes — use `0x01`-`0x09` for those)

The complete alias table:

### Letters

| HID code | Aliases |
|----------|---------|
| `0x04` | `a` |
| `0x05` | `b` |
| `0x06` | `c` |
| `0x07` | `d` |
| `0x08` | `e` |
| `0x09` | `f` |
| `0x0A` | `g` |
| `0x0B` | `h` |
| `0x0C` | `i` |
| `0x0D` | `j` |
| `0x0E` | `k` |
| `0x0F` | `l` |
| `0x10` | `m` |
| `0x11` | `n` |
| `0x12` | `o` |
| `0x13` | `p` |
| `0x14` | `q` |
| `0x15` | `r` |
| `0x16` | `s` |
| `0x17` | `t` |
| `0x18` | `u` |
| `0x19` | `v` |
| `0x1A` | `w` |
| `0x1B` | `x` |
| `0x1C` | `y` |
| `0x1D` | `z` |

### Digits (top row)

| HID code | Aliases |
|----------|---------|
| `0x1E` | `1` |
| `0x1F` | `2` |
| `0x20` | `3` |
| `0x21` | `4` |
| `0x22` | `5` |
| `0x23` | `6` |
| `0x24` | `7` |
| `0x25` | `8` |
| `0x26` | `9` |
| `0x27` | `0` |

### Editing & whitespace

| HID code | Aliases |
|----------|---------|
| `0x28` | `enter`, `return` |
| `0x29` | `esc`, `escape` |
| `0x2A` | `backspace` |
| `0x2B` | `tab` |
| `0x2C` | `space` |
| `0x39` | `caps_lock` |

### Punctuation

| HID code | Aliases |
|----------|---------|
| `0x2D` | `minus`, `hyphen` |
| `0x2E` | `equal`, `equals` |
| `0x2F` | `left_bracket` |
| `0x30` | `right_bracket` |
| `0x31` | `backslash` |
| `0x33` | `semicolon` |
| `0x34` | `quote`, `apostrophe` |
| `0x35` | `grave`, `backtick` |
| `0x36` | `comma` |
| `0x37` | `dot`, `period` |
| `0x38` | `slash` |

### Function keys F1–F24

| HID code | Aliases |
|----------|---------|
| `0x3A` | `f1` |
| `0x3B` | `f2` |
| `0x3C` | `f3` |
| `0x3D` | `f4` |
| `0x3E` | `f5` |
| `0x3F` | `f6` |
| `0x40` | `f7` |
| `0x41` | `f8` |
| `0x42` | `f9` |
| `0x43` | `f10` |
| `0x44` | `f11` |
| `0x45` | `f12` |
| `0x68` | `f13` |
| `0x69` | `f14` |
| `0x6A` | `f15` |
| `0x6B` | `f16` |
| `0x6C` | `f17` |
| `0x6D` | `f18` |
| `0x6E` | `f19` |
| `0x6F` | `f20` |
| `0x70` | `f21` |
| `0x71` | `f22` |
| `0x72` | `f23` |
| `0x73` | `f24` |

### Navigation

| HID code | Aliases |
|----------|---------|
| `0x46` | `print_screen` |
| `0x47` | `scroll_lock` |
| `0x48` | `pause` |
| `0x49` | `insert` |
| `0x4A` | `home` |
| `0x4B` | `pageup`, `page_up` |
| `0x4C` | `delete`, `forward_delete` |
| `0x4D` | `end` |
| `0x4E` | `pagedown`, `page_down` |
| `0x4F` | `right`, `right_arrow` |
| `0x50` | `left`, `left_arrow` |
| `0x51` | `down`, `down_arrow` |
| `0x52` | `up`, `up_arrow` |

### Keypad (numeric pad)

| HID code | Aliases |
|----------|---------|
| `0x53` | `num_lock` |
| `0x54` | `kp_slash`, `kp_divide` |
| `0x55` | `kp_asterisk`, `kp_multiply` |
| `0x56` | `kp_minus` |
| `0x57` | `kp_plus` |
| `0x58` | `kp_enter` |
| `0x59` | `kp_1` |
| `0x5A` | `kp_2` |
| `0x5B` | `kp_3` |
| `0x5C` | `kp_4` |
| `0x5D` | `kp_5` |
| `0x5E` | `kp_6` |
| `0x5F` | `kp_7` |
| `0x60` | `kp_8` |
| `0x61` | `kp_9` |
| `0x62` | `kp_0` |
| `0x63` | `kp_dot`, `kp_period` |
| `0x67` | `kp_equal` |

### International (CJK IMEs)

| HID code | Aliases |
|----------|---------|
| `0x87` | `intl1`, `international1` |
| `0x88` | `intl2`, `international2`, `katakana_hiragana` |
| `0x89` | `intl3`, `international3` |
| `0x8A` | `intl4`, `henkan`, `international4` |
| `0x8B` | `intl5`, `muhenkan`, `international5` |
| `0x8C` | `intl6`, `international6` |
| `0x8D` | `intl7`, `international7` |
| `0x8E` | `intl8`, `international8` |
| `0x8F` | `intl9`, `international9` |

### Lang (KR/JP IMEs)

| HID code | Aliases |
|----------|---------|
| `0x90` | `lang1`, `hangul` |
| `0x91` | `hanja`, `lang2` |
| `0x92` | `lang3`, `katakana` |
| `0x93` | `lang4`, `hiragana` |
| `0x94` | `lang5`, `zenkaku_hankaku` |

### Modifiers

| HID code | Aliases |
|----------|---------|
| `0xE0` | `ctrl`, `control`, `lctrl`, `left_ctrl`, `left_control` |
| `0xE1` | `shift`, `lshift`, `left_shift` |
| `0xE2` | `alt`, `opt`, `option`, `lalt`, `loption`, `left_alt`, `left_option` |
| `0xE3` | `cmd`, `command`, `meta`, `gui`, `win`, `lcmd`, `lmeta`, `lgui`, `left_cmd`, `left_meta`, `left_gui` |
| `0xE4` | `rctrl`, `right_ctrl`, `right_control` |
| `0xE5` | `rshift`, `right_shift` |
| `0xE6` | `ralt`, `roption`, `right_alt`, `right_option` |
| `0xE7` | `rcmd`, `rmeta`, `rgui`, `right_cmd`, `right_meta`, `right_gui` |

> The unmodified `cmd`/`shift`/`ctrl`/`alt` aliases default to the
> **left** modifier — matching how applications usually treat them.

The canonical source is [`src/keysmith/keymap.py`](src/keysmith/keymap.py)
— if you find a key missing, it's a one-line addition there plus a
test, please open a PR.

## Tests

```bash
uv run pytest             # offline tests (no board needed)
```

The tests cover the keymap and config layers. Protocol/discovery
end-to-end tests require a connected board and aren't run automatically.

## Architecture

```
cli.py            ┐
                  ├─→  config.py    (YAML schema, layered lookup, kebab-case)
                  ├─→  keymap.py    (alias → HID code)
                  ├─→  discovery.py (PING-based port autodiscovery)
                  └─→  protocol.py  (binary wire protocol over pyserial)
```

The CLI is the only layer that touches I/O policy (where to look for
config, exit codes, error formatting). Everything below is pure logic
that can be reused by other Python callers (e.g. a Hermes plugin).
