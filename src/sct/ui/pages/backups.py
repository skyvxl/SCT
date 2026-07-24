from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout

from sct.localization import TranslationService
from sct.ui.pages.base import LocalizedPage
from sct.ui.widgets.forms import action_button, translated_table


class BackupsPage(LocalizedPage):
    def __init__(self, translator: TranslationService) -> None:
        super().__init__(translator)
        layout = QVBoxLayout(self)
        layout.addStretch(2)
        self.status_label = QLabel()
        self.status_label.setObjectName("backupStatusLabel")
        self.status_label.setProperty("role", "danger")
        self.bind(self.status_label.setText, "backups.status_stopped")
        layout.addWidget(self.status_label)

        pinned_title = QLabel()
        self.bind(pinned_title.setText, "backups.pinned")
        layout.addWidget(pinned_title)
        self.pinned_table = translated_table(
            self, ("backups.name", "backups.date"), "pinnedBackupsTable"
        )
        layout.addWidget(self.pinned_table, 1)

        regular_title = QLabel()
        self.bind(regular_title.setText, "backups.regular")
        layout.addWidget(regular_title)
        self.regular_table = translated_table(
            self, ("backups.name", "backups.date"), "regularBackupsTable"
        )
        layout.addWidget(self.regular_table, 1)

        buttons = QGridLayout()
        self.save_button = action_button(self, "backups.save", "saveBackupButton")
        self.load_button = action_button(self, "backups.load", "loadBackupButton")
        self.refresh_button = action_button(self, "common.refresh", "refreshBackupsButton")
        self.delete_button = action_button(self, "common.delete", "deleteBackupButton")
        self.start_button = action_button(self, "backups.start", "startAutoBackupButton")
        self.stop_button = action_button(self, "backups.stop", "stopAutoBackupButton")
        self.load_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        for column, button in enumerate(
            (self.save_button, self.load_button, self.refresh_button, self.delete_button)
        ):
            buttons.addWidget(button, 0, column)
        buttons.addWidget(self.start_button, 1, 0, 1, 2)
        buttons.addWidget(self.stop_button, 1, 2, 1, 2)
        layout.addLayout(buttons)
