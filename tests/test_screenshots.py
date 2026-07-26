from __future__ import annotations

import threading
import time
import unittest

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QImage
from PySide6.QtMultimedia import QVideoFrame

from sct.screenshots import (
    GameWindowCapture,
    bgra_to_png,
    select_capture_window,
)
from tests.qt_helpers import get_qapplication


class FakeCapturableWindow:
    def __init__(self, description: str, *, valid: bool = True) -> None:
        self._description = description
        self._valid = valid

    def description(self) -> str:
        return self._description

    def isValid(self) -> bool:
        return self._valid


class FakeWindowCapture(QObject):
    errorOccurred = Signal(object, str)

    def __init__(self) -> None:
        super().__init__()
        self.selected_window = None
        self.started = False

    def setWindow(self, window) -> None:
        self.selected_window = window

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False


class FakeVideoSink(QObject):
    videoFrameChanged = Signal(object)


class FakeCaptureSession:
    def setWindowCapture(self, capture) -> None:
        self.capture = capture

    def setVideoSink(self, sink) -> None:
        self.sink = sink


class ScreenshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = get_qapplication()

    def test_exact_game_title_does_not_select_manager_or_browser(self) -> None:
        manager = FakeCapturableWindow("Elden Ring Seamless Co-op Mod Manager")
        browser = FakeCapturableWindow("Elden Ring guide - Brave")
        game = FakeCapturableWindow("ELDEN RING™")

        selected = select_capture_window(
            (manager, browser, game),
            "ELDEN RING™",
        )

        self.assertIs(selected, game)

    def test_invalid_exact_title_match_is_not_selected(self) -> None:
        invalid_game = FakeCapturableWindow("ELDEN RING™", valid=False)

        selected = select_capture_window((invalid_game,), "ELDEN RING™")

        self.assertIsNone(selected)

    def test_capture_request_returns_first_qt_video_frame_as_png(self) -> None:
        game = FakeCapturableWindow("ELDEN RING™")
        source = FakeWindowCapture()
        sink = FakeVideoSink()
        capture = GameWindowCapture(
            window_provider=lambda: (game,),
            game_title_provider=lambda: "ELDEN RING™",
            window_capture=source,
            capture_session=FakeCaptureSession(),
            video_sink=sink,
        )
        result: dict[str, bytes | None] = {}
        worker = threading.Thread(
            target=lambda: result.setdefault(
                "png",
                capture.capture(timeout_seconds=1.0),
            )
        )

        worker.start()
        deadline = time.monotonic() + 1.0
        while not source.started and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.005)
        self.assertTrue(source.started)
        self.assertIs(source.selected_window, game)

        image = QImage(2, 1, QImage.Format.Format_RGB32)
        image.fill(QColor(214, 65, 46))
        sink.videoFrameChanged.emit(QVideoFrame(image))
        while worker.is_alive() and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.005)
        worker.join(timeout=0.1)

        self.assertFalse(worker.is_alive())
        png = result["png"]
        self.assertIsNotNone(png)
        decoded = QImage.fromData(png, "PNG")
        self.assertEqual(decoded.pixelColor(0, 0), QColor(214, 65, 46))

    def test_bgra_pixels_are_encoded_as_a_valid_png_without_color_swapping(self) -> None:
        pixels = bytes(
            (
                0,
                0,
                255,
                0,
                0,
                255,
                0,
                0,
            )
        )

        png = bgra_to_png(pixels, width=2, height=1)
        image = QImage.fromData(png, "PNG")

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertFalse(image.isNull())
        self.assertEqual(image.pixelColor(0, 0), QColor(255, 0, 0))
        self.assertEqual(image.pixelColor(1, 0), QColor(0, 255, 0))


if __name__ == "__main__":
    unittest.main()
