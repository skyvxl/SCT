from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from sct.game.builds import EquipmentValue
from sct.items import ItemCatalog, ItemCategory
from sct.localization import TranslationService


class ItemSlotWidget(QFrame):
    browse_requested = Signal(str)
    value_changed = Signal(str, object)

    def __init__(
            self,
            translator: TranslationService,
            slot_name: str,
            label_key: str,
            category: ItemCategory,
            value: EquipmentValue,
            *,
            catalog: ItemCatalog | None,
            editable: bool,
            parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.translator = translator
        self.slot_name = slot_name
        self.category = category
        self.catalog = catalog
        self.editable = editable
        self._value = value
        self.setObjectName("itemSlot")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        self.slot_label = QLabel(translator.translate(label_key))
        self.slot_label.setObjectName("itemSlotLabel")
        self.slot_label.setMinimumWidth(0)
        self.slot_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        layout.addWidget(self.slot_label, 1)
        self.image_label = QLabel()
        self.image_label.setObjectName("itemSlotImage")
        self.image_label.setFixedSize(64, 64)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image_label)

        self.browse_button: QPushButton | None = None
        self.remove_button: QPushButton | None = None
        if editable:
            self.browse_button = QPushButton(translator.translate("common.browse"))
            self.browse_button.clicked.connect(
                lambda: self.browse_requested.emit(self.slot_name)
            )
            self.remove_button = QPushButton(
                translator.translate("player_details.remove")
            )
            self.remove_button.clicked.connect(self.clear)
            layout.addWidget(self.browse_button)
            layout.addWidget(self.remove_button)
        self._render()

    @property
    def value(self) -> EquipmentValue:
        return self._value

    def set_value(self, value: EquipmentValue) -> None:
        self._value = value
        self._render()
        self.value_changed.emit(self.slot_name, value)

    def clear(self) -> None:
        if self.editable:
            self.set_value(None)

    def _render(self) -> None:
        value = self._value
        if value is None:
            self.image_label.clear()
            self.image_label.setToolTip("")
            return
        record = self.catalog.get(self.category, value.item_id) if self.catalog else None
        name = record.name if record is not None else str(value.item_id)
        if value.upgrade_level:
            name = f"{name} +{value.upgrade_level}"
        self.image_label.setToolTip(name)
        self.slot_label.setToolTip(name)
        self.image_label.clear()
        payload = self.catalog.icon_bytes(record) if self.catalog and record else None
        if not payload:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(payload):
            self.image_label.setPixmap(
                pixmap.scaled(
                    self.image_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
