from __future__ import annotations

from collections.abc import Callable

from sct.backup_manager import BackupManager
from sct.game.runtime import EldenRingRuntime
from sct.installer import ModInstaller
from sct.localization import TranslationService
from sct.mod_loaders import ModLoaderManager
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
        game_runtime: EldenRingRuntime,
        backup_manager: BackupManager,
        loader_manager: ModLoaderManager | None = None,
        installer_factory: Callable[[], ModInstaller] | None = None,
) -> tuple[PageSpec, ...]:
    loaders = loader_manager or ModLoaderManager()
    settings_page = SettingsPage(
        translator,
        settings_store,
        steam_service,
        loader_manager=loaders,
        installer_factory=installer_factory,
    )
    seamless_page = SeamlessPage(translator, settings_store)
    backups_page = BackupsPage(translator, backup_manager, settings_store)
    settings_page.game_directory_changed.connect(seamless_page.set_game_directory)
    settings_page.backup_settings_changed.connect(backups_page.reload_hotkeys)
    return (
        PageSpec(
            "nav.home",
            "home.png",
            HomePage(translator, settings_store, steam_service, loaders),
        ),
        PageSpec("nav.seamless", "seamless.png", seamless_page),
        PageSpec(
            "nav.current_game",
            "controller.png",
            CurrentGamePage(translator, game_runtime),
        ),
        PageSpec("nav.backups", "backup.png", backups_page),
        PageSpec(
            "nav.characters",
            "character.png",
            CharactersPage(translator, settings_store),
        ),
        PageSpec("nav.settings", "settings.png", settings_page),
    )
