from __future__ import annotations

import ctypes
import logging
import os
from collections.abc import Iterable
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, Lock
from typing import Any, Protocol

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QIODevice,
    QObject,
    Qt,
    QThread,
    Signal,
    Slot,
)
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import (
    QMediaCaptureSession,
    QVideoFrame,
    QVideoSink,
    QWindowCapture,
)

LOGGER = logging.getLogger("sct.screenshots")

MAX_SCREENSHOT_WIDTH = 1920
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MAX_EXECUTABLE_PATH = 32768


class _CapturableWindowProtocol(Protocol):
    def description(self) -> str: ...

    def isValid(self) -> bool: ...


def select_capture_window(
        windows: Iterable[_CapturableWindowProtocol],
        expected_title: str,
) -> _CapturableWindowProtocol | None:
    title = expected_title.strip().casefold()
    if not title:
        return None
    for window in windows:
        if (
                window.isValid()
                and window.description().strip().casefold() == title
        ):
            return window
    return None


@dataclass(slots=True)
class _CaptureRequest:
    completed: Event = field(default_factory=Event)
    result: bytes | None = None


class GameWindowCapture(QObject):
    _capture_requested = Signal(object)
    _cancel_requested = Signal(object)

    def __init__(
            self,
            parent: QObject | None = None,
            *,
            window_provider=QWindowCapture.capturableWindows,
            game_title_provider=None,
            window_capture: Any | None = None,
            capture_session: Any | None = None,
            video_sink: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self._window_provider = window_provider
        self._game_title_provider = (
                game_title_provider or _find_elden_ring_window_title
        )
        self._window_capture = window_capture or QWindowCapture(self)
        self._capture_session = capture_session or QMediaCaptureSession(self)
        self._video_sink = video_sink or QVideoSink(self)
        self._request_lock = Lock()
        self._active_request: _CaptureRequest | None = None

        self._capture_session.setWindowCapture(self._window_capture)
        self._capture_session.setVideoSink(self._video_sink)
        self._capture_requested.connect(
            self._begin_capture,
            Qt.ConnectionType.QueuedConnection,
        )
        self._cancel_requested.connect(
            self._cancel_capture,
            Qt.ConnectionType.QueuedConnection,
        )
        self._video_sink.videoFrameChanged.connect(self._frame_received)
        self._window_capture.errorOccurred.connect(self._capture_failed)

    def capture(self, *, timeout_seconds: float = 3.0) -> bytes | None:
        if QThread.currentThread() is self.thread():
            LOGGER.debug("Window capture cannot block the Qt application thread")
            return None
        request = _CaptureRequest()
        with self._request_lock:
            self._capture_requested.emit(request)
            if not request.completed.wait(max(0.1, timeout_seconds)):
                self._cancel_requested.emit(request)
                return None
            return request.result

    @Slot(object)
    def _begin_capture(self, request: object) -> None:
        active = request
        if not isinstance(active, _CaptureRequest):
            return
        if self._active_request is not None:
            self._finish_capture(None)
        self._active_request = active
        try:
            expected_title = self._game_title_provider()
            window = select_capture_window(
                self._window_provider(),
                expected_title or "",
            )
            if window is None:
                self._finish_capture(None)
                return
            self._window_capture.setWindow(window)
            self._window_capture.start()
        except Exception as error:
            LOGGER.debug("Unable to start Elden Ring window capture: %s", error)
            self._finish_capture(None)

    @Slot(object)
    def _cancel_capture(self, request: object) -> None:
        if request is self._active_request:
            self._finish_capture(None)

    @Slot(object)
    def _frame_received(self, frame: object) -> None:
        if self._active_request is None or not isinstance(frame, QVideoFrame):
            return
        if not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        try:
            payload = image_to_png(image)
        except Exception as error:
            LOGGER.debug("Unable to encode Elden Ring capture: %s", error)
            self._finish_capture(None)
            return
        self._finish_capture(payload)

    @Slot(object, str)
    def _capture_failed(self, _error: object, message: str) -> None:
        if self._active_request is None:
            return
        LOGGER.debug("Elden Ring window capture failed: %s", message)
        self._finish_capture(None)

    def _finish_capture(self, result: bytes | None) -> None:
        request = self._active_request
        if request is None:
            return
        self._active_request = None
        try:
            self._window_capture.stop()
        except Exception:
            LOGGER.debug("Unable to stop Elden Ring window capture", exc_info=True)
        request.result = result
        request.completed.set()


def bgra_to_png(data: bytes, *, width: int, height: int) -> bytes:
    if width <= 0 or height <= 0:
        raise ValueError("Screenshot dimensions must be positive")
    stride = width * 4
    if len(data) != stride * height:
        raise ValueError("BGRA buffer size does not match screenshot dimensions")
    image = QImage(
        data,
        width,
        height,
        stride,
        QImage.Format.Format_RGB32,
    ).copy()
    if image.isNull():
        raise ValueError("Unable to construct screenshot image")
    return image_to_png(image)


def image_to_png(image: QImage) -> bytes:
    image = image.copy()
    if image.isNull():
        raise ValueError("Unable to encode an empty screenshot")
    if image.width() > MAX_SCREENSHOT_WIDTH:
        image = image.scaledToWidth(
            MAX_SCREENSHOT_WIDTH,
            Qt.TransformationMode.SmoothTransformation,
        )
    payload = QByteArray()
    output = QBuffer(payload)
    if not output.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("Unable to open screenshot PNG buffer")
    try:
        if not image.save(output, "PNG"):
            raise RuntimeError("Unable to encode screenshot as PNG")
    finally:
        output.close()
    return bytes(payload)


def _find_elden_ring_window_title() -> str | None:
    if os.name != "nt":
        return None
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    enum_windows = user32.EnumWindows
    is_visible = user32.IsWindowVisible
    is_iconic = user32.IsIconic
    get_length = user32.GetWindowTextLengthW
    get_text = user32.GetWindowTextW
    get_process_id = user32.GetWindowThreadProcessId
    open_process = kernel32.OpenProcess
    query_image = kernel32.QueryFullProcessImageNameW
    close_handle = kernel32.CloseHandle

    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HWND,
        wintypes.LPARAM,
    )
    enum_windows.argtypes = (callback_type, wintypes.LPARAM)
    enum_windows.restype = wintypes.BOOL
    is_visible.argtypes = (wintypes.HWND,)
    is_visible.restype = wintypes.BOOL
    is_iconic.argtypes = (wintypes.HWND,)
    is_iconic.restype = wintypes.BOOL
    get_length.argtypes = (wintypes.HWND,)
    get_length.restype = ctypes.c_int
    get_text.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    get_text.restype = ctypes.c_int
    get_process_id.argtypes = (
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    )
    get_process_id.restype = wintypes.DWORD
    open_process.argtypes = (
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    )
    open_process.restype = wintypes.HANDLE
    query_image.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    query_image.restype = wintypes.BOOL
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    found: str | None = None

    def visit(window: int, _parameter: int) -> bool:
        nonlocal found
        if not is_visible(window) or is_iconic(window):
            return True
        length = get_length(window)
        if length <= 0:
            return True
        process_id = wintypes.DWORD()
        get_process_id(window, ctypes.byref(process_id))
        process = open_process(
            PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            process_id.value,
        )
        if not process:
            return True
        try:
            path = ctypes.create_unicode_buffer(MAX_EXECUTABLE_PATH)
            size = wintypes.DWORD(len(path))
            if not query_image(process, 0, path, ctypes.byref(size)):
                return True
            if Path(path.value).name.casefold() != "eldenring.exe":
                return True
        finally:
            close_handle(process)
        title = ctypes.create_unicode_buffer(length + 1)
        if get_text(window, title, length + 1):
            found = title.value
            return False
        return True

    callback = callback_type(visit)
    enum_windows(callback, 0)
    return found
