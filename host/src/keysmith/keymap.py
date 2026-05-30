"""HID keyboard usage code aliases.

Maps human-friendly names like 'international3' or 'cmd' to the raw HID
usage codes from USB HID Usage Table v1.22, Keyboard/Keypad Page (0x07).

Reference: https://usb.org/sites/default/files/hut1_22.pdf §10
Cross-checked against: NicoHood/HID-Project ImprovedKeylayouts.h

Names are stored lowercased with underscores; lookup is case-insensitive
and accepts hyphens or spaces as separators. Numeric values (`0x89`,
`137`, or `'0x89'`) are also accepted by `resolve_key()` for ad-hoc use.
"""

from __future__ import annotations

from typing import Dict


class UnknownKeyError(KeyError):
    """The given key name/code could not be resolved to a HID usage."""


# ---- Canonical keymap -------------------------------------------------
#
# Organised by HID Usage Table sections. Codes are inclusive ranges;
# only commonly useful aliases are surfaced here. Add more as needed.

KEYMAP: Dict[str, int] = {
    # --- Letters (0x04..0x1D) ---
    **{chr(c): 0x04 + (c - ord("a")) for c in range(ord("a"), ord("z") + 1)},
    # --- Digits row (0x1E..0x27) ---
    "1": 0x1E, "2": 0x1F, "3": 0x20, "4": 0x21, "5": 0x22,
    "6": 0x23, "7": 0x24, "8": 0x25, "9": 0x26, "0": 0x27,

    # --- Editing / whitespace ---
    "enter": 0x28, "return": 0x28,
    "escape": 0x29, "esc": 0x29,
    "backspace": 0x2A,
    "tab": 0x2B,
    "space": 0x2C,
    "minus": 0x2D, "hyphen": 0x2D,
    "equal": 0x2E, "equals": 0x2E,
    "left_bracket": 0x2F,
    "right_bracket": 0x30,
    "backslash": 0x31,
    "semicolon": 0x33,
    "apostrophe": 0x34, "quote": 0x34,
    "grave": 0x35, "backtick": 0x35,
    "comma": 0x36,
    "period": 0x37, "dot": 0x37,
    "slash": 0x38,
    "caps_lock": 0x39,

    # --- Function row ---
    "f1": 0x3A, "f2": 0x3B, "f3": 0x3C, "f4": 0x3D,
    "f5": 0x3E, "f6": 0x3F, "f7": 0x40, "f8": 0x41,
    "f9": 0x42, "f10": 0x43, "f11": 0x44, "f12": 0x45,
    "f13": 0x68, "f14": 0x69, "f15": 0x6A, "f16": 0x6B,
    "f17": 0x6C, "f18": 0x6D, "f19": 0x6E, "f20": 0x6F,
    "f21": 0x70, "f22": 0x71, "f23": 0x72, "f24": 0x73,

    # --- Navigation ---
    "print_screen": 0x46,
    "scroll_lock": 0x47,
    "pause": 0x48,
    "insert": 0x49,
    "home": 0x4A,
    "page_up": 0x4B, "pageup": 0x4B,
    "delete": 0x4C, "forward_delete": 0x4C,
    "end": 0x4D,
    "page_down": 0x4E, "pagedown": 0x4E,
    "right_arrow": 0x4F, "right": 0x4F,
    "left_arrow": 0x50, "left": 0x50,
    "down_arrow": 0x51, "down": 0x51,
    "up_arrow": 0x52, "up": 0x52,

    # --- Keypad (numeric pad) ---
    "num_lock": 0x53,
    "kp_divide": 0x54, "kp_slash": 0x54,
    "kp_multiply": 0x55, "kp_asterisk": 0x55,
    "kp_minus": 0x56,
    "kp_plus": 0x57,
    "kp_enter": 0x58,
    "kp_1": 0x59, "kp_2": 0x5A, "kp_3": 0x5B, "kp_4": 0x5C,
    "kp_5": 0x5D, "kp_6": 0x5E, "kp_7": 0x5F, "kp_8": 0x60,
    "kp_9": 0x61, "kp_0": 0x62,
    "kp_period": 0x63, "kp_dot": 0x63,
    "kp_equal": 0x67,

    # --- International (commonly used for Asian IMEs) ---
    "international1": 0x87, "intl1": 0x87,           # ろ / Brazilian /
    "international2": 0x88, "intl2": 0x88, "katakana_hiragana": 0x88,
    "international3": 0x89, "intl3": 0x89,           # ¥ on JP layout
    "international4": 0x8A, "intl4": 0x8A, "henkan": 0x8A,
    "international5": 0x8B, "intl5": 0x8B, "muhenkan": 0x8B,
    "international6": 0x8C, "intl6": 0x8C,
    "international7": 0x8D, "intl7": 0x8D,
    "international8": 0x8E, "intl8": 0x8E,
    "international9": 0x8F, "intl9": 0x8F,

    # --- Lang (KR/JP) ---
    "lang1": 0x90, "hangul": 0x90,
    "lang2": 0x91, "hanja": 0x91,
    "lang3": 0x92, "katakana": 0x92,
    "lang4": 0x93, "hiragana": 0x93,
    "lang5": 0x94, "zenkaku_hankaku": 0x94,

    # --- Modifiers ---
    "left_control":  0xE0, "left_ctrl":  0xE0, "lctrl": 0xE0,
    "left_shift":    0xE1, "lshift": 0xE1,
    "left_alt":      0xE2, "left_option": 0xE2, "lalt": 0xE2, "loption": 0xE2,
    "left_gui":      0xE3, "left_cmd": 0xE3, "left_meta": 0xE3,
    "lcmd": 0xE3, "lmeta": 0xE3, "lgui": 0xE3,
    "right_control": 0xE4, "right_ctrl": 0xE4, "rctrl": 0xE4,
    "right_shift":   0xE5, "rshift": 0xE5,
    "right_alt":     0xE6, "right_option": 0xE6, "ralt": 0xE6, "roption": 0xE6,
    "right_gui":     0xE7, "right_cmd": 0xE7, "right_meta": 0xE7,
    "rcmd": 0xE7, "rmeta": 0xE7, "rgui": 0xE7,

    # --- Convenience aliases (default to LEFT modifier) ---
    "ctrl": 0xE0, "control": 0xE0,
    "shift": 0xE1,
    "alt": 0xE2, "option": 0xE2, "opt": 0xE2,
    "cmd": 0xE3, "command": 0xE3, "meta": 0xE3, "gui": 0xE3, "win": 0xE3,
}


def _normalize(name: str) -> str:
    """Lowercase and normalize separators to underscore."""
    return name.strip().lower().replace("-", "_").replace(" ", "_")


def resolve_key(value: object) -> int:
    """Resolve a key spec to an HID usage code (0..255).

    Accepts:
        - int                       returned as-is (after range check)
        - str alias                 looked up in KEYMAP (case/sep-insensitive)
        - hex string '0x89'         parsed as int
        - decimal string '137'      parsed as int

    Raises:
        UnknownKeyError if the alias is unknown.
        ValueError if an int is out of byte range.
        TypeError on unsupported input types.
    """
    if isinstance(value, bool):
        raise TypeError(f"bool is not a valid HID code: {value!r}")
    if isinstance(value, int):
        if not (0 <= value <= 0xFF):
            raise ValueError(f"HID code out of byte range: 0x{value:X}")
        return value
    if isinstance(value, str):
        s = value.strip()
        # Alias lookup first — this matters because the digit row keys
        # ("1", "2", ...) are stored in KEYMAP with their character as
        # the alias. If we tried numeric parsing first, "1" would be
        # interpreted as raw HID code 1 (KEY_ERROR_ROLLOVER) rather
        # than as the digit-1 key (0x1E).
        norm = _normalize(s)
        if norm in KEYMAP:
            return KEYMAP[norm]
        # Hex string? (Always allowed — `0x1E` is unambiguous.)
        if s.lower().startswith("0x"):
            try:
                code = int(s, 16)
            except ValueError:
                raise UnknownKeyError(f"Invalid hex code: {value!r}") from None
            if not (0 <= code <= 0xFF):
                raise ValueError(f"HID code out of byte range: {value!r}")
            return code
        # Pure decimal? Only accept values that aren't already a digit
        # alias (i.e. require >= 10 to disambiguate from "1".."9"). For
        # digits 0-9 the user must use the hex form (e.g. `0x1E`) to
        # express a raw code, otherwise the alias wins. For 10..255
        # decimals we treat as raw HID code.
        if s.isdigit():
            code = int(s, 10)
            if 10 <= code <= 0xFF:
                return code
            # 0..9 already handled by alias lookup above; reaching here
            # means the alias didn't exist (shouldn't happen) or a
            # confusing single-digit was passed.
            raise UnknownKeyError(
                f"Ambiguous numeric key {value!r}: "
                f"use '0x{code:02X}' for raw HID code, "
                f"or one of {sorted(c for c in '0123456789')} for digit keys."
            )
        raise UnknownKeyError(f"Unknown key alias: {value!r}")
    raise TypeError(f"Cannot resolve key from {type(value).__name__}: {value!r}")
