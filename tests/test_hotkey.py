import pytest

from scorecap.hotkey import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    MOD_WIN,
    parse_hotkey,
)


def test_parses_ctrl_shift_letter():
    mods, vk = parse_hotkey("Ctrl+Shift+S")
    assert mods == MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT
    assert vk == ord("S")


def test_parses_alt_and_win_and_digits():
    mods, vk = parse_hotkey("alt+win+4")
    assert mods == MOD_ALT | MOD_WIN | MOD_NOREPEAT
    assert vk == ord("4")


def test_parses_function_keys():
    _, vk = parse_hotkey("Ctrl+F9")
    assert vk == 0x78


def test_is_case_and_space_insensitive():
    assert parse_hotkey(" CTRL + shift + s ") == parse_hotkey("ctrl+shift+S")


@pytest.mark.parametrize("spec", ["", "Ctrl+", "Hyper+S", "Ctrl+Shift+NotAKey"])
def test_invalid_specs_raise(spec):
    with pytest.raises(ValueError):
        parse_hotkey(spec)


def test_key_without_modifier_is_rejected():
    with pytest.raises(ValueError):
        parse_hotkey("S")
