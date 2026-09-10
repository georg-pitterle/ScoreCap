"""System-wide hotkey via Win32 RegisterHotKey, delivered through Qt."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
HOTKEY_ID = 0xA17C

_MODIFIERS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "strg": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "umschalt": MOD_SHIFT,
    "win": MOD_WIN,
    "meta": MOD_WIN,
}

_NAMED_KEYS = {
    "space": 0x20,
    "print": 0x2C,
    "insert": 0x2D,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    **{f"f{n}": 0x6F + n for n in range(1, 13)},
}


def _virtual_key(name: str) -> int:
    if len(name) == 1 and (name.isalpha() or name.isdigit()):
        return ord(name.upper())
    if name in _NAMED_KEYS:
        return _NAMED_KEYS[name]
    raise ValueError(f"Unbekannte Taste: {name}")


def parse_hotkey(spec: str) -> tuple[int, int]:
    parts = [part.strip().lower() for part in spec.split("+") if part.strip()]
    if len(parts) < 2:
        raise ValueError("Hotkey braucht mindestens einen Modifier und eine Taste")
    *modifier_names, key = parts
    modifiers = MOD_NOREPEAT
    for name in modifier_names:
        if name not in _MODIFIERS:
            raise ValueError(f"Unbekannter Modifier: {name}")
        modifiers |= _MODIFIERS[name]
    return modifiers, _virtual_key(key)


class HotkeyFilter(QAbstractNativeEventFilter):
    """Registers one global hotkey and calls back when it fires."""

    def __init__(self, on_pressed: Callable[[], None]) -> None:
        super().__init__()
        self._on_pressed = on_pressed
        self._registered = False

    def register(self, spec: str) -> bool:
        self.unregister()
        modifiers, virtual_key = parse_hotkey(spec)
        ok = bool(
            ctypes.windll.user32.RegisterHotKey(
                None, HOTKEY_ID, wintypes.UINT(modifiers), wintypes.UINT(virtual_key)
            )
        )
        self._registered = ok
        return ok

    def unregister(self) -> None:
        if self._registered:
            ctypes.windll.user32.UnregisterHotKey(None, HOTKEY_ID)
            self._registered = False

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (Qt naming)
        if event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self._on_pressed()
        return False, 0
