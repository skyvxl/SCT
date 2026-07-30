from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import QSize
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from sct.component_versions import detect_ersc_version
from sct.localization import TranslationService
from sct.resource_loader import load_optional_icon
from sct.settings import SettingsStore
from sct.ui.dialogs.about import AboutDialog
from sct.ui.dialogs.auto_setup import AutoSetupDialog, InstallerFactory
from sct.ui.page_spec import PageSpec
from sct.ui.update_controller import (
    UpdateController,
    UpdateServiceFactory,
)
from sct.ui.widgets.popups import SquarePopupMenu
from sct.version import DISPLAY_VERSION

AboutFactory = Callable[[TranslationService, QWidget | None], QDialog]
AutoSetupFactory = Callable[
    [TranslationService, SettingsStore, InstallerFactory, QWidget | None],
    QDialog,
]
UpdateControllerFactory = Callable[
    [TranslationService, SettingsStore, UpdateServiceFactory, QWidget | None],
    UpdateController,
]


class MainWindow(QMainWindow):
    def __init__(
            self,
            translator: TranslationService,
            pages: Sequence[PageSpec],
            settings_store: SettingsStore,
            installer_factory: InstallerFactory,
            update_service_factory: UpdateServiceFactory,
            *,
            about_factory: AboutFactory = AboutDialog,
            auto_setup_factory: AutoSetupFactory = AutoSetupDialog,
            update_controller_factory: UpdateControllerFactory = UpdateController,
    ) -> None:
        super().__init__()
        if len(pages) != 6:
            raise ValueError("MainWindow requires exactly six pages")
        self.translator = translator
        self._pages = tuple(pages)
        self._settings_store = settings_store
        self._installer_factory = installer_factory
        self._update_controller = update_controller_factory(
            translator,
            settings_store,
            update_service_factory,
            self,
        )
        self._about_factory = about_factory
        self._auto_setup_factory = auto_setup_factory
        self._ersc_version: str | None = None
        self.navigation_buttons: list[QPushButton] = []
        self.help_actions: list[QAction] = []

        self.setObjectName("mainWindow")
        self.resize(1600, 900)
        self.setMinimumSize(1040, 720)
        application_icon = load_optional_icon("icons", "icon.ico")
        if application_icon is not None:
            self.setWindowIcon(application_icon)

        self.help_menu = SquarePopupMenu(self.menuBar())
        self.help_menu.setObjectName("helpMenu")
        self.menuBar().addMenu(self.help_menu)
        action_callbacks = (
            ("menu.auto_setup", self.show_auto_setup),
            (
                "menu.check_manager_updates",
                lambda: self._update_controller.check_toolkit(self),
            ),
            (
                "menu.check_mod_updates",
                lambda: self._update_controller.check_ersc(self),
            ),
            ("menu.about", self.show_about),
        )
        for key, callback in action_callbacks:
            action = QAction(self)
            action.setProperty("translationKey", key)
            action.triggered.connect(
                lambda _checked=False, handler=callback: handler()
            )
            self.help_menu.addAction(action)
            self.help_actions.append(action)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 6, 8, 4)
        root.setSpacing(4)
        body = QHBoxLayout()
        body.setSpacing(12)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(232)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(8)
        self.navigation_group = QButtonGroup(self)
        self.navigation_group.setExclusive(True)

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("pageStack")
        for index, page in enumerate(self._pages):
            button = QPushButton()
            button.setObjectName("navigationButton")
            button.setCheckable(True)
            button.setMinimumHeight(40)
            button.setIconSize(QSize(24, 24))
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            icon = load_optional_icon("icons", page.icon_name)
            if icon is not None:
                button.setIcon(icon)
            button.clicked.connect(lambda _checked=False, value=index: self.select_page(value))
            self.navigation_group.addButton(button, index)
            self.navigation_buttons.append(button)
            sidebar_layout.addWidget(button)
            self.page_stack.addWidget(page.widget)
        sidebar_layout.addStretch(1)
        body.addWidget(sidebar)
        body.addWidget(self.page_stack, 1)
        root.addLayout(body, 1)

        footer = QHBoxLayout()
        self.mod_version_label = QLabel()
        self.manager_version_label = QLabel()
        footer.addWidget(self.mod_version_label)
        footer.addStretch(1)
        footer.addWidget(self.manager_version_label)
        root.addLayout(footer)
        self.setCentralWidget(central)

        self.translator.language_changed.connect(lambda _locale: self.retranslate_ui())
        self._update_controller.ersc_updated.connect(self.refresh_ersc_version)
        self._update_controller.auto_setup_requested.connect(self.show_auto_setup)
        self.select_page(0)
        self.refresh_ersc_version()
        self.retranslate_ui()

    def select_page(self, index: int) -> None:
        self.page_stack.setCurrentIndex(index)
        self.navigation_buttons[index].setChecked(True)

    def show_about(self) -> None:
        dialog = self._about_factory(self.translator, self)
        dialog.exec()

    def show_auto_setup(self) -> None:
        dialog = self._auto_setup_factory(
            self.translator,
            self._settings_store,
            self._installer_factory,
            self,
        )
        settings_page = self._pages[-1].widget
        if hasattr(dialog, "installation_completed") and hasattr(
                settings_page,
                "handle_installation_completed",
        ):
            dialog.installation_completed.connect(
                settings_page.handle_installation_completed
            )
        if hasattr(dialog, "installation_completed"):
            dialog.installation_completed.connect(self.refresh_ersc_version)
        dialog.exec()

    def refresh_ersc_version(self, _result: object | None = None) -> None:
        game_directory = self._settings_store.load().mod_path
        self._ersc_version = detect_ersc_version(game_directory)
        if not hasattr(self, "mod_version_label"):
            return
        if self._ersc_version is None:
            text = self.translator.translate("footer.mod_not_detected")
        else:
            text = self.translator.translate(
                "footer.mod_version",
                version=self._ersc_version,
            )
        self.mod_version_label.setText(text)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.translator.translate("app.title"))
        self.help_menu.setTitle(self.translator.translate("menu.help"))
        for action in self.help_actions:
            action.setText(self.translator.translate(action.property("translationKey")))
        for button, page in zip(self.navigation_buttons, self._pages, strict=True):
            button.setText(self.translator.translate(page.label_key))
        self.refresh_ersc_version()
        self.manager_version_label.setText(
            self.translator.translate("footer.manager_version", version=DISPLAY_VERSION)
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        self._update_controller.shutdown()
        for page in self._pages:
            shutdown = getattr(page.widget, "shutdown", None)
            if callable(shutdown):
                shutdown()
        super().closeEvent(event)
