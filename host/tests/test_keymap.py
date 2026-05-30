"""Tests for keysmith.keymap."""

import pytest

from keysmith.keymap import KEYMAP, UnknownKeyError, resolve_key


class TestResolveKey:
    def test_lowercase_alias(self) -> None:
        assert resolve_key("international3") == 0x89

    def test_short_alias(self) -> None:
        assert resolve_key("intl3") == 0x89

    def test_case_insensitive(self) -> None:
        assert resolve_key("CMD") == 0xE3
        assert resolve_key("Cmd") == 0xE3

    def test_separator_normalisation_hyphen(self) -> None:
        assert resolve_key("right-shift") == 0xE5

    def test_separator_normalisation_space(self) -> None:
        assert resolve_key("right shift") == 0xE5

    def test_int_passthrough(self) -> None:
        assert resolve_key(0x89) == 0x89
        assert resolve_key(0) == 0
        assert resolve_key(255) == 255

    def test_int_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            resolve_key(256)
        with pytest.raises(ValueError):
            resolve_key(-1)

    def test_hex_string(self) -> None:
        assert resolve_key("0x89") == 0x89
        assert resolve_key("0X89") == 0x89

    def test_decimal_string(self) -> None:
        # 137 = 0x89 (International3). Decimals >= 10 are accepted as
        # raw HID codes since they can't be confused with digit aliases.
        assert resolve_key("137") == 0x89

    def test_single_digit_string_resolves_to_alias(self) -> None:
        # "1" must mean the digit-1 key (0x1E), not raw HID code 1
        # (KEY_ERROR_ROLLOVER). Use "0x01" if you really want raw code 1.
        assert resolve_key("1") == 0x1E
        assert resolve_key("9") == 0x26
        assert resolve_key("0") == 0x27

    def test_unknown_alias_raises(self) -> None:
        with pytest.raises(UnknownKeyError):
            resolve_key("not_a_real_key")

    def test_bool_rejected(self) -> None:
        # bool is a subclass of int in Python; we explicitly reject it
        # to catch typos like `tap: true`.
        with pytest.raises(TypeError):
            resolve_key(True)

    def test_none_rejected(self) -> None:
        with pytest.raises(TypeError):
            resolve_key(None)

    def test_modifier_default_is_left(self) -> None:
        assert resolve_key("cmd") == 0xE3   # Left GUI
        assert resolve_key("shift") == 0xE1  # Left Shift
        assert resolve_key("ctrl") == 0xE0   # Left Control
        assert resolve_key("alt") == 0xE2    # Left Alt

    def test_letter_keys(self) -> None:
        assert resolve_key("a") == 0x04
        assert resolve_key("z") == 0x1D

    def test_digit_keys(self) -> None:
        # NB: HID puts '1' at 0x1E and '0' at 0x27 (not in numeric order).
        assert resolve_key("1") == 0x1E
        assert resolve_key("0") == 0x27

    def test_function_keys(self) -> None:
        assert resolve_key("f1") == 0x3A
        assert resolve_key("f12") == 0x45
        assert resolve_key("f19") == 0x6E
        assert resolve_key("f24") == 0x73


class TestKeymapIntegrity:
    def test_no_duplicate_codes_for_canonical_names(self) -> None:
        """Aliases sharing a code is fine (cmd == left_cmd), but different
        canonical keys must have unique codes."""
        # We only enforce uniqueness on the 'primary' name for each HID
        # code. This is a sanity check: catch typos like accidentally
        # mapping two different keys to the same code.
        canonicals = {
            "international3": 0x89,
            "international1": 0x87,
            "international2": 0x88,
            "right_shift": 0xE5,
            "left_shift": 0xE1,
            "f19": 0x6E,
            "up_arrow": 0x52,
            "space": 0x2C,
            "enter": 0x28,
        }
        for name, code in canonicals.items():
            assert KEYMAP[name] == code, f"{name} should be 0x{code:02X}"

    def test_all_codes_in_byte_range(self) -> None:
        for name, code in KEYMAP.items():
            assert 0 <= code <= 0xFF, f"{name}=0x{code:X} out of range"

    def test_all_keys_lowercase(self) -> None:
        for name in KEYMAP:
            assert name == name.lower(), f"{name!r} is not lowercase"
