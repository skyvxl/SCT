from __future__ import annotations

from sct.localization import TranslationService
from sct.settings import SettingsStore
from sct.steam import SteamService
from sct.ui.page_spec import PageSpec
from sct.ui.pages.backups import BackupsPage
from sct.ui.pages.characters import CharactersPage
from sct.ui.pages.current_game import CurrentGamePage
from sct.ui.pages.home import HomePage
from sct.ui.pages.seamless import SeamlessPage
from sct.ui.pages.settings import SettingsPage


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
