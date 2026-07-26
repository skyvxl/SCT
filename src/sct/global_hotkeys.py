from __future__ import annotations

import ctypes
import os
from collections.abc import Callable, Mapping
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

from sct.errors import LocalizedError

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
HOTKEY_ID_BASE = 0x5C70


def _enum_value(value: object) -> int:
    raw = getattr(value, "value", value)
    return int(raw)  # type: ignore[arg-type]


_SPECIAL_KEYS = {
    _enum_value(Qt.Key.Key_Escape): 0x1B,
    _enum_value(Qt.Key.Key_Tab): 0x09,
    _enum_value(Qt.Key.Key_Backtab): 0x09,
    _enum_value(Qt.Key.Key_Backspace): 0x08,
    _enum_value(Qt.Key.Key_Return): 0x0D,
    _enum_value(Qt.Key.Key_Enter): 0x0D,
    _enum_value(Qt.Key.Key_Insert): 0x2D,
    _enum_value(Qt.Key.Key_Delete): 0x2E,
    _enum_value(Qt.Key.Key_Pause): 0x13,
    _enum_value(Qt.Key.Key_Print): 0x2C,
    _enum_value(Qt.Key.Key_Clear): 0x0C,
    _enum_value(Qt.Key.Key_Home): 0x24,
    _enum_value(Qt.Key.Key_End): 0x23,
    _enum_value(Qt.Key.Key_Left): 0x25,
    _enum_value(Qt.Key.Key_Up): 0x26,
    _enum_value(Qt.Key.Key_Right): 0x27,
    _enum_value(Qt.Key.Key_Down): 0x28,
    _enum_value(Qt.Key.Key_PageUp): 0x21,
    _enum_value(Qt.Key.Key_PageDown): 0x22,
    _enum_value(Qt.Key.Key_Space): 0x20,
}


def key_sequence_to_windows_hotkey(sequence: QKeySequence) -> tuple[int, int]:
    if sequence.count() != 1:
        raise ValueError("A global shortcut must contain exactly one key chord")
    combination = sequence[0]
    modifiers = combination.keyboardModifiers()
    windows_modifiers = 0
    if modifiers & Qt.KeyboardModifier.AltModifier:
        windows_modifiers |= MOD_ALT
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        windows_modifiers |= MOD_CONTROL
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        windows_modifiers |= MOD_SHIFT
    if modifiers & Qt.KeyboardModifier.MetaModifier:
        windows_modifiers |= MOD_WIN

    key = _enum_value(combination.key())
    first_function_key = _enum_value(Qt.Key.Key_F1)
    last_function_key = _enum_value(Qt.Key.Key_F24)
    if first_function_key <= key <= last_function_key:
        virtual_key = 0x70 + key - first_function_key
    elif ord("A") <= key <= ord("Z") or ord("0") <= key <= ord("9"):
        virtual_key = key
    else:
        virtual_key = _SPECIAL_KEYS.get(key, 0)
    if not virtual_key:
        raise ValueError(f"Unsupported global shortcut key: {key:#x}")
    return windows_modifiers, virtual_key


class _NativeHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback: Callable[[int], None]) -> None:
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        event_name = (
            event_type
            if isinstance(event_type, str)
            else bytes(event_type).decode("ascii", errors="ignore")
        )
        if event_name in {"windows_generic_MSG", "windows_dispatcher_MSG"}:
            native_message = wintypes.MSG.from_address(int(message))
            if native_message.message == WM_HOTKEY:
                self._callback(int(native_message.wParam))
                return True, 0
        return False, 0


class GlobalHotkeyManager(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._registered_ids: set[int] = set()
        self._filter = _NativeHotkeyFilter(self._dispatch)
        application = QApplication.instance()
        if os.name == "nt" and application is not None:
            application.installNativeEventFilter(self._filter)

    def register(
            self,
            bindings: Mapping[str, tuple[QKeySequence, Callable[[], None]]],
    ) -> None:
        self.unregister_all()
        if os.name != "nt":
            return
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        register_hotkey = user32.RegisterHotKey
        register_hotkey.argtypes = (
            wintypes.HWND,
            ctypes.c_int,
            wintypes.UINT,
            wintypes.UINT,
        )
        register_hotkey.restype = wintypes.BOOL

        for index, (name, (sequence, callback)) in enumerate(bindings.items()):
            if sequence.isEmpty():
                continue
            try:
                modifiers, virtual_key = key_sequence_to_windows_hotkey(sequence)
            except ValueError as error:
                self.unregister_all()
                raise LocalizedError(
                    "shortcut_invalid",
                    f"Invalid global shortcut for {name}: {error}",
                    params={"name": name},
                ) from error
            hotkey_id = HOTKEY_ID_BASE + index
            if not register_hotkey(
                    None,
                    hotkey_id,
                    modifiers | MOD_NOREPEAT,
                    virtual_key,
            ):
                self.unregister_all()
                raise LocalizedError(
                    "shortcut_registration_failed",
                    f"Unable to register global shortcut for {name}",
                    params={"name": name},
                )
            self._registered_ids.add(hotkey_id)
            self._callbacks[hotkey_id] = callback

    def unregister_all(self) -> None:
        if os.name == "nt" and self._registered_ids:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            unregister_hotkey = user32.UnregisterHotKey
            unregister_hotkey.argtypes = (wintypes.HWND, ctypes.c_int)
            unregister_hotkey.restype = wintypes.BOOL
            for hotkey_id in self._registered_ids:
                unregister_hotkey(None, hotkey_id)
        self._registered_ids.clear()
        self._callbacks.clear()

    def shutdown(self) -> None:
        self.unregister_all()
        application = QApplication.instance()
        if os.name == "nt" and application is not None:
            application.removeNativeEventFilter(self._filter)

    def _dispatch(self, hotkey_id: int) -> None:
        callback = self._callbacks.get(hotkey_id)
        if callback is not None:
            callback()
