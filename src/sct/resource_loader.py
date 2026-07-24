from __future__ import annotations

import logging
from importlib.resources import files
from pathlib import Path

from PySide6.QtGui import QIcon

LOGGER = logging.getLogger("sct.resources")
RESOURCE_PACKAGE = "sct.resources"


def resource_root() -> Path:
    return Path(str(files(RESOURCE_PACKAGE)))


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def optional_resource_path(*parts: str) -> Path | None:
    path = resource_path(*parts)
    if path.is_file():
        return path
    LOGGER.warning("Optional resource is missing: %s", path)
    return None


def load_optional_icon(*parts: str) -> QIcon | None:
    path = optional_resource_path(*parts)
    if path is None:
        return None
    icon = QIcon(str(path))
    if icon.isNull():
        LOGGER.warning("Optional icon is invalid: %s", path)
        return None
    return icon


def load_stylesheet() -> str:
    path = resource_path("styles", "theme.qss")
    try:
        stylesheet = path.read_text(encoding="utf-8")
    except OSError:
        LOGGER.warning("Unable to load stylesheet: %s", path, exc_info=True)
        return ""
    return stylesheet.replace("assets/icons", resource_path("icons").as_posix())
