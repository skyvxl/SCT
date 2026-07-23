from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout

from scmm.localization import TranslationService
from scmm.ui.pages.base import LocalizedPage
from scmm.ui.widgets.forms import action_button, translated_table


class CharactersPage(LocalizedPage):
    def __init__(self, translator: TranslationService) -> None:
        super().__init__(translator)
        layout = QVBoxLayout(self)
        instructions_title = QLabel()
        instructions_title.setProperty("role", "accent")
        instructions_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bind(instructions_title.setText, "characters.instructions_title")
        layout.addWidget(instructions_title)
        instructions = QLabel()
        instructions.setWordWrap(True)
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bind(instructions.setText, "characters.instructions")
        layout.addWidget(instructions)

        archive_title = QLabel()
        self.bind(archive_title.setText, "characters.archive")
        layout.addWidget(archive_title)
        self.archive_table = translated_table(
            self,
            ("characters.name", "characters.level", "characters.playtime"),
            "archivedCharactersTable",
        )
        layout.addWidget(self.archive_table, 1)
        archive_buttons = QGridLayout()
        archive_buttons.addWidget(
            action_button(self, "characters.load_archive", "loadArchiveButton"), 0, 0
        )
        archive_buttons.addWidget(action_button(self, "common.delete", "deleteArchiveButton"), 0, 1)
        layout.addLayout(archive_buttons)

        game_title = QLabel()
        self.bind(game_title.setText, "characters.game_save")
        layout.addWidget(game_title)
        self.game_table = translated_table(
            self,
            ("characters.name", "characters.level", "characters.playtime"),
            "gameCharactersTable",
        )
        layout.addWidget(self.game_table, 1)
        game_buttons = QGridLayout()
        game_buttons.addWidget(
            action_button(self, "characters.load_game", "loadGameSaveButton"), 0, 0
        )
        game_buttons.addWidget(
            action_button(self, "common.delete", "deleteGameCharacterButton"), 0, 1
        )
        layout.addLayout(game_buttons)
