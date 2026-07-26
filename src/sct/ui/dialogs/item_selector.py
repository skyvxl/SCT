from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from sct.game.builds import EquipmentItem
from sct.items import ItemCatalog, ItemCategory, ItemRecord
from sct.localization import TranslationService

QUANTITY_CATEGORIES = {ItemCategory.QUICK_ITEMS, ItemCategory.AMMUNITION}
INVALID_MODEL_INDEX = QModelIndex()


class ItemTableModel(QAbstractTableModel):
    def __init__(
            self,
            catalog: ItemCatalog,
            category: ItemCategory,
            translator: TranslationService,
            parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.catalog = catalog
        self.category = category
        self.translator = translator
        self._items = catalog.items(category)
        self._pixmaps: dict[int, QPixmap | None] = {}

    def rowCount(self, parent: QModelIndex = INVALID_MODEL_INDEX) -> int:
        return 0 if parent.isValid() else len(self._items)

    def columnCount(self, parent: QModelIndex = INVALID_MODEL_INDEX) -> int:
        return 0 if parent.isValid() else 3

    def data(
            self,
            index: QModelIndex,
            role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                return item.name
            if index.column() == 1:
                return str(item.id)
            return ""
        if role == Qt.ItemDataRole.DecorationRole and index.column() == 2:
            return self._pixmap(item)
        if role == Qt.ItemDataRole.ToolTipRole:
            return item.name
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() == 1:
            return Qt.AlignmentFlag.AlignCenter
        return None

    def headerData(
            self,
            section: int,
            orientation: Qt.Orientation,
            role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if orientation != Qt.Orientation.Horizontal or role != Qt.ItemDataRole.DisplayRole:
            return None
        keys = (
            "player_details.selector.name",
            "player_details.selector.id",
            "player_details.selector.image",
        )
        return self.translator.translate(keys[section]) if 0 <= section < 3 else None

    def item_at(self, row: int) -> ItemRecord:
        return self._items[row]

    def set_query(self, query: str) -> None:
        self.beginResetModel()
        self._items = self.catalog.search(self.category, query)
        self.endResetModel()

    def _pixmap(self, item: ItemRecord) -> QPixmap | None:
        if item.icon_id is None:
            return None
        if item.icon_id in self._pixmaps:
            return self._pixmaps[item.icon_id]
        payload = self.catalog.icon_bytes(item)
        pixmap: QPixmap | None = None
        if payload:
            candidate = QPixmap()
            if candidate.loadFromData(payload):
                pixmap = candidate.scaled(
                    96,
                    96,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
        self._pixmaps[item.icon_id] = pixmap
        return pixmap


class ItemSelectorDialog(QDialog):
    def __init__(
            self,
            translator: TranslationService,
            catalog: ItemCatalog,
            category: ItemCategory,
            parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.translator = translator
        self.catalog = catalog
        self.category = ItemCategory(category)
        self._selected_record: ItemRecord | None = None
        self._selected_ash: ItemRecord | None = None
        self.setObjectName("itemSelectorDialog")

        root = QVBoxLayout(self)
        search_row = QHBoxLayout()
        search_label = QLabel(self.translator.translate("player_details.selector.search"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            self.translator.translate("player_details.selector.search_hint")
        )
        search_row.addWidget(search_label)
        search_row.addWidget(self.search_edit, 1)
        root.addLayout(search_row)

        self.model = ItemTableModel(catalog, self.category, translator, self)
        self.table = QTableView()
        self.table.setObjectName("itemSelectorTable")
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(110)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.Fixed,
        )
        self.table.setColumnWidth(2, 120)
        root.addWidget(self.table, 1)

        self.quantity_row = QWidget()
        quantity_layout = QHBoxLayout(self.quantity_row)
        quantity_layout.setContentsMargins(0, 0, 0, 0)
        quantity_layout.addWidget(
            QLabel(self.translator.translate("player_details.selector.quantity"))
        )
        self.quantity_spin = QSpinBox()
        self.quantity_spin.setRange(1, 999)
        self.quantity_spin.setValue(99)
        quantity_layout.addWidget(self.quantity_spin, 1)
        self.quantity_row.setVisible(self.category in QUANTITY_CATEGORIES)
        root.addWidget(self.quantity_row)

        self.weapon_controls = QWidget()
        weapon_layout = QVBoxLayout(self.weapon_controls)
        weapon_layout.setContentsMargins(0, 0, 0, 0)
        level_row = QHBoxLayout()
        level_row.addWidget(
            QLabel(self.translator.translate("player_details.selector.weapon_level"))
        )
        self.upgrade_spin = QSpinBox()
        self.upgrade_spin.setRange(0, 0)
        level_row.addWidget(self.upgrade_spin, 1)
        weapon_layout.addLayout(level_row)
        ash_row = QHBoxLayout()
        self.ash_button = QPushButton(
            self.translator.translate("player_details.selector.choose_ash")
        )
        self.ash_button.setEnabled(False)
        self.ash_label = QLabel(
            self.translator.translate("player_details.selector.no_ash")
        )
        ash_row.addWidget(self.ash_button)
        ash_row.addWidget(self.ash_label, 1)
        weapon_layout.addLayout(ash_row)
        self.weapon_controls.setVisible(self.category is ItemCategory.WEAPONS)
        root.addWidget(self.weapon_controls)

        button_row = QHBoxLayout()
        self.accept_button = QPushButton(
            self.translator.translate("common.accept")
        )
        self.accept_button.setEnabled(False)
        cancel_button = QPushButton(self.translator.translate("common.cancel"))
        button_row.addWidget(self.accept_button)
        button_row.addWidget(cancel_button)
        root.addLayout(button_row)

        self.search_edit.textChanged.connect(self._filter)
        self.table.selectionModel().currentRowChanged.connect(
            lambda current, _previous: self.select_row(current.row())
        )
        self.table.doubleClicked.connect(lambda _index: self._accept_if_ready())
        self.accept_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        self.ash_button.clicked.connect(self._choose_ash)

        title_key = (
            "player_details.selector.weapon_title"
            if self.category is ItemCategory.WEAPONS
            else "player_details.selector.title"
        )
        self.setWindowTitle(self.translator.translate(title_key))
        self.setFixedSize(600, 820)

    def select_row(self, row: int) -> None:
        if not 0 <= row < self.model.rowCount():
            self._selected_record = None
            self.accept_button.setEnabled(False)
            self.ash_button.setEnabled(False)
            return
        self._selected_record = self.model.item_at(row)
        self.accept_button.setEnabled(True)
        if self.category is ItemCategory.WEAPONS:
            maximum = self._selected_record.max_upgrade
            self.upgrade_spin.setRange(0, maximum)
            self.upgrade_spin.setValue(min(self.upgrade_spin.value(), maximum))
            self.ash_button.setEnabled(True)
        model_index = self.model.index(row, 0)
        if self.table.currentIndex().row() != row:
            self.table.setCurrentIndex(model_index)
            self.table.selectRow(row)

    def selected_item(self) -> EquipmentItem | None:
        record = self._selected_record
        if record is None:
            return None
        return EquipmentItem(
            item_id=record.id,
            quantity=(
                self.quantity_spin.value()
                if self.category in QUANTITY_CATEGORIES
                else 1
            ),
            upgrade_level=(
                self.upgrade_spin.value()
                if self.category is ItemCategory.WEAPONS
                else 0
            ),
            ash_of_war=(
                self._selected_ash.id
                if self.category is ItemCategory.WEAPONS
                   and self._selected_ash is not None
                else None
            ),
        )

    def _filter(self, query: str) -> None:
        self.model.set_query(query)
        self.table.clearSelection()
        self.select_row(-1)

    def _choose_ash(self) -> None:
        if self._selected_record is None:
            return
        dialog = ItemSelectorDialog(
            self.translator,
            self.catalog,
            ItemCategory.ASHES_OF_WAR,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        item = dialog.selected_item()
        if item is None:
            return
        self._selected_ash = self.catalog.get(
            ItemCategory.ASHES_OF_WAR,
            item.item_id,
        )
        if self._selected_ash is not None:
            self.ash_label.setText(self._selected_ash.name)

    def _accept_if_ready(self) -> None:
        if self._selected_record is not None:
            self.accept()
