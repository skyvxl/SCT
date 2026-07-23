from __future__ import annotations

import logging
import os
from pathlib import Path

LOGGER_NAME = "scmm"


def log_file_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "SeamlessCoopModManager" / "logs" / "scmm.log"


def configure_logging() -> Path | None:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    path = log_file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.FileHandler(path, encoding="utf-8")
        result: Path | None = path
    except OSError:
        handler = logging.StreamHandler()
        result = None
    handler.setFormatter(formatter)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False
    return result
