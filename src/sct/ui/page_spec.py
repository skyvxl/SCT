from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget


@dataclass(frozen=True, slots=True)
class PageSpec:
    label_key: str
    icon_name: str
    widget: QWidget
