from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout

from scmm.localization import TranslationService
from scmm.ui.pages.base import LocalizedPage
from scmm.ui.widgets.forms import action_button, translated_table


class CurrentGamePage(LocalizedPage):
    def __init__(self, translator: TranslationService) -> None:
        super().__init__(translator)
        layout = QVBoxLayout(self)

        current_title = QLabel()
        self.bind(current_title.setText, "current_game.current_players")
        layout.addWidget(current_title)
        self.current_table = translated_table(
            self,
            ("current_game.username", "current_game.level", "current_game.health"),
            "currentPlayersTable",
        )
        layout.addWidget(self.current_table, 1)
        layout.addWidget(action_button(self, "current_game.loading_fix", "loadingFixButton"))

        recent_title = QLabel()
        self.bind(recent_title.setText, "current_game.recent_players")
        layout.addWidget(recent_title)
        self.recent_table = translated_table(
            self,
            ("current_game.username", "current_game.level", "current_game.date"),
            "recentPlayersTable",
        )
        layout.addWidget(self.recent_table, 1)
