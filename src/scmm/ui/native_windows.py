from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

from PySide6.QtWidgets import QWidget

LOGGER = logging.getLogger("scmm.ui.native_windows")
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_DONOTROUND = 1


def _apply_dwm_square_corners(window_id: int) -> bool:
    dwmapi = ctypes.WinDLL("dwmapi")
    set_window_attribute = dwmapi.DwmSetWindowAttribute
    set_window_attribute.argtypes = (
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    set_window_attribute.restype = ctypes.c_long
    preference = ctypes.c_int(DWMWCP_DONOTROUND)
    result = set_window_attribute(
        wintypes.HWND(window_id),
        wintypes.DWORD(DWMWA_WINDOW_CORNER_PREFERENCE),
        ctypes.byref(preference),
        wintypes.DWORD(ctypes.sizeof(preference)),
    )
    return int(result) == 0


def request_square_corners(widget: QWidget) -> bool:
    if sys.platform != "win32":
        return False
    try:
        return _apply_dwm_square_corners(int(widget.winId()))
    except Exception:
        LOGGER.debug("Unable to request square native corners", exc_info=True)
        return False
