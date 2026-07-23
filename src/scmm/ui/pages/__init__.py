from __future__ import annotations

from scmm.localization import TranslationService
from scmm.ui.page_spec import PageSpec
from scmm.ui.pages.backups import BackupsPage
from scmm.ui.pages.characters import CharactersPage
from scmm.ui.pages.current_game import CurrentGamePage
from scmm.ui.pages.home import HomePage
from scmm.ui.pages.seamless import SeamlessPage
from scmm.ui.pages.settings import SettingsPage


def build_page_specs(translator: TranslationService) -> tuple[PageSpec, ...]:
    return (
        PageSpec("nav.home", "home.png", HomePage(translator)),
        PageSpec("nav.seamless", "seamless.png", SeamlessPage(translator)),
        PageSpec("nav.current_game", "controller.png", CurrentGamePage(translator)),
        PageSpec("nav.backups", "backup.png", BackupsPage(translator)),
        PageSpec("nav.characters", "character.png", CharactersPage(translator)),
        PageSpec("nav.settings", "settings.png", SettingsPage(translator)),
    )
