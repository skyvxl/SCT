from __future__ import annotations

from scmm.localization import TranslationService
from scmm.settings import SettingsStore
from scmm.steam import SteamService
from scmm.ui.page_spec import PageSpec
from scmm.ui.pages.backups import BackupsPage
from scmm.ui.pages.characters import CharactersPage
from scmm.ui.pages.current_game import CurrentGamePage
from scmm.ui.pages.home import HomePage
from scmm.ui.pages.seamless import SeamlessPage
from scmm.ui.pages.settings import SettingsPage


def build_page_specs(
    translator: TranslationService,
    settings_store: SettingsStore,
    steam_service: SteamService,
) -> tuple[PageSpec, ...]:
    settings_page = SettingsPage(translator, settings_store, steam_service)
    seamless_page = SeamlessPage(translator, settings_store)
    settings_page.game_directory_changed.connect(seamless_page.set_game_directory)
    return (
        PageSpec(
            "nav.home",
            "home.png",
            HomePage(translator, settings_store, steam_service),
        ),
        PageSpec("nav.seamless", "seamless.png", seamless_page),
        PageSpec("nav.current_game", "controller.png", CurrentGamePage(translator)),
        PageSpec("nav.backups", "backup.png", BackupsPage(translator)),
        PageSpec("nav.characters", "character.png", CharactersPage(translator)),
        PageSpec("nav.settings", "settings.png", settings_page),
    )
