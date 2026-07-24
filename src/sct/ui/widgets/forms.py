from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from sct.ui.pages.base import LocalizedPage


def section(page: LocalizedPage, title_key: str) -> QGroupBox:
    group = QGroupBox()
    page.bind(group.setTitle, title_key)
    return group


def add_form_row(
    page: LocalizedPage,
    layout: QFormLayout,
    label_key: str,
    field: QWidget,
) -> QLabel:
    label = QLabel()
    page.bind(label.setText, label_key)
    layout.addRow(label, field)
    return label


def action_button(page: LocalizedPage, key: str, object_name: str) -> QPushButton:
    button = QPushButton()
    button.setObjectName(object_name)
    page.bind(button.setText, key)
    return button


def translated_table(
    page: LocalizedPage,
    header_keys: Sequence[str],
    object_name: str,
) -> QTableWidget:
    table = QTableWidget(0, len(header_keys))
    table.setObjectName(object_name)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    for column, key in enumerate(header_keys):
        item = QTableWidgetItem()
        table.setHorizontalHeaderItem(column, item)
        page.bind(item.setText, key)
    return table
