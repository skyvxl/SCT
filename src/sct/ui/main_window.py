from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import QSize
from PySide6.QtGui import QAction
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

from sct.localization import TranslationService
from sct.resource_loader import load_optional_icon
from sct.settings import SettingsStore
from sct.ui.dialogs.about import AboutDialog
from sct.ui.dialogs.auto_setup import AutoSetupDialog, InstallerFactory
from sct.ui.page_spec import PageSpec
from sct.ui.widgets.popups import SquarePopupMenu
from sct.version import DISPLAY_VERSION

AboutFactory = Callable[[TranslationService, QWidget | None], QDialog]
AutoSetupFactory = Callable[
    [TranslationService, SettingsStore, InstallerFactory, QWidget | None],
    QDialog,
]


class MainWindow(QMainWindow):
    def __init__(
        self,
        translator: TranslationService,
        pages: Sequence[PageSpec],
        settings_store: SettingsStore,
        installer_factory: InstallerFactory,
        *,
        about_factory: AboutFactory = AboutDialog,
        auto_setup_factory: AutoSetupFactory = AutoSetupDialog,
    ) -> None:
        super().__init__()
        if len(pages) != 6:
            raise ValueError("MainWindow requires exactly six pages")
        self.translator = translator
        self._pages = tuple(pages)
        self._settings_store = settings_store
        self._installer_factory = installer_factory
        self._about_factory = about_factory
        self._auto_setup_factory = auto_setup_factory
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
        for key in (
            "menu.auto_setup",
            "menu.check_manager_updates",
            "menu.check_mod_updates",
            "menu.about",
        ):
            action = QAction(self)
            action.setProperty("translationKey", key)
            callback = self.show_auto_setup if key == "menu.auto_setup" else self.show_about
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
        self.select_page(0)
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
        dialog.exec()

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.translator.translate("app.title"))
        self.help_menu.setTitle(self.translator.translate("menu.help"))
        for action in self.help_actions:
            action.setText(self.translator.translate(action.property("translationKey")))
        for button, page in zip(self.navigation_buttons, self._pages, strict=True):
            button.setText(self.translator.translate(page.label_key))
        self.mod_version_label.setText(self.translator.translate("footer.mod_not_detected"))
        self.manager_version_label.setText(
            self.translator.translate("footer.manager_version", version=DISPLAY_VERSION)
        )
