from __future__ import annotations

import os
from pathlib import Path


def configure_qt_environment() -> None:
    if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        return
    font_directory = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    if font_directory.is_dir():
        os.environ.setdefault("QT_QPA_FONTDIR", str(font_directory))
