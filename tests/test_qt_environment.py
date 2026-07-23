from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QFontMetrics

from scmm.qt_environment import configure_qt_environment
from tests.qt_helpers import get_qapplication


class QtEnvironmentTests(unittest.TestCase):
    def test_offscreen_platform_uses_installed_windows_fonts(self) -> None:
        with patch.dict(
            os.environ,
            {"QT_QPA_PLATFORM": "offscreen", "WINDIR": r"C:\Windows"},
        ):
            os.environ.pop("QT_QPA_FONTDIR", None)
            configure_qt_environment()

            self.assertEqual(os.environ["QT_QPA_FONTDIR"], str(Path(r"C:\Windows") / "Fonts"))

    def test_offscreen_application_font_supports_cyrillic(self) -> None:
        application = get_qapplication()
        self.assertTrue(QFontMetrics(application.font()).inFontUcs4(ord("Ж")))


if __name__ == "__main__":
    unittest.main()
