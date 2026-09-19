"""Application shell: one workspace window, plus a start screen.

There is no mode switch. The editor is a single dock-based workspace whose
panels the user arranges; the only separate page is the start screen, which
exists to open a project and is left as soon as one is open. Opening, creating,
or dropping a project raises the workspace, and the View menu carries the
workspace arrangements and the panel toggles.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from scentinel.core.project import FILE_FILTER, Project, load_project
from scentinel.ui.i18n import LANGUAGES, Translator
from scentinel.ui.main_window import MainWindow
from scentinel.ui.workspace import WORKSPACES

_RECENT_KEY = "recentProjects"
_RECENT_LIMIT = 8


class HomeWindow(QMainWindow):
    """Owns the workspace and the start screen; never switches editor modes."""

    def __init__(
        self,
        translator: Translator,
        project: Project | None = None,
        path: Path | None = None,
        settings: QSettings | None = None,
    ) -> None:
        super().__init__()
        self._t = translator
        self._settings = settings or QSettings("Scentinel", "Scentinel")
        self.setWindowTitle("Scentinel")
        self.resize(1520, 940)

        # A path without a loaded project still opens that project: the caller
        # should not have to know that the editor needs the object as well.
        if project is None and path is not None:
            try:
                project = load_project(path)
            except (OSError, ValueError, KeyError):
                project = None
                path = None

        self._editor = MainWindow(translator, project=project, path=path)
        self._editor.setWindowFlags(Qt.WindowType.Widget)
        self._editor.home_requested.connect(self.show_start)
        self._editor.project_path_changed.connect(self._remember_project)

        self._stack = QStackedWidget()
        self._start = self._build_start()
        self._stack.addWidget(self._start)
        self._stack.addWidget(self._editor)
        self.setCentralWidget(self._stack)

        self._build_toolbar()
        self._build_menus()
        self._refresh_recents()
        if path is not None:
            self._remember_project(path)
            QTimer.singleShot(0, self.show_workspace)
        else:
            QTimer.singleShot(0, self.show_start)

    # -- start screen --------------------------------------------------------

    def _build_start(self) -> QWidget:
        page = QWidget()
        page.setObjectName("homePage")
        root = QVBoxLayout(page)
        root.setContentsMargins(38, 32, 38, 32)
        root.setSpacing(16)

        self._home_title = QLabel()
        self._home_title.setObjectName("dashboardTitle")
        self._home_subtitle = QLabel()
        self._home_subtitle.setWordWrap(True)
        self._home_subtitle.setObjectName("secondaryText")
        root.addWidget(self._home_title)
        root.addWidget(self._home_subtitle)

        actions = QHBoxLayout()
        self._new_button = QPushButton()
        self._new_button.setObjectName("primaryAction")
        self._new_button.clicked.connect(self._new_project)
        self._open_button = QPushButton()
        self._open_button.clicked.connect(self._open_project)
        actions.addWidget(self._new_button)
        actions.addWidget(self._open_button)
        actions.addStretch(1)
        root.addLayout(actions)

        self._recent_caption = QLabel()
        self._recent_caption.setObjectName("cardHeading")
        root.addWidget(self._recent_caption)
        self._recents = QListWidget()
        self._recents.setObjectName("recentList")
        self._recents.itemActivated.connect(self._open_recent_item)
        self._recents.itemClicked.connect(self._open_recent_item)
        root.addWidget(self._recents, 1)

        self._empty_recents = QLabel()
        self._empty_recents.setObjectName("secondaryText")
        root.addWidget(self._empty_recents)

        self._t.changed.connect(self._retranslate_start)
        self._retranslate_start()
        return page

    def _retranslate_start(self) -> None:
        t = self._t.t
        self._home_title.setText(t("home.title"))
        self._home_subtitle.setText(t("home.subtitle"))
        self._new_button.setText(t("home.new"))
        self._open_button.setText(t("home.open"))
        self._recent_caption.setText(t("home.recent"))
        self._empty_recents.setText(t("home.recent.empty"))

    # -- toolbar and menus ---------------------------------------------------

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        self._act_start = QAction(self)
        self._act_start.setShortcut("Alt+Left")
        self._act_start.triggered.connect(self.show_start)
        toolbar.addAction(self._act_start)
        toolbar.addSeparator()

        self._project_label = QLabel()
        self._project_label.setObjectName("toolbarProject")
        toolbar.addWidget(self._project_label)
        self._retranslate_toolbar()
        self._t.changed.connect(self._retranslate_toolbar)

    def _retranslate_toolbar(self) -> None:
        self._act_start.setText(self._t.t("nav.start"))
        self._refresh_project_label()

    def _refresh_project_label(self) -> None:
        path = self._editor.project_path()
        text = path.name if path is not None else self._t.t("home.untitled")
        if self._editor.is_dirty():
            text += " •"
        self._project_label.setText(text)

    def _build_menus(self) -> None:
        """Extend the editor's View menu with workspaces, panels, and language.

        The editor already owns a View menu holding the fit and reset actions;
        this adds to that menu rather than appending a second one, so there is a
        single place where the arrangement is controlled.
        """
        view = self._editor.view_menu()
        self._view_menu = view

        view.addSeparator()
        self._workspace_menu = view.addMenu("")
        group = QActionGroup(self)
        group.setExclusive(True)
        self._workspace_actions: dict[str, QAction] = {}
        for name in WORKSPACES:
            action = QAction(name, self, checkable=True)
            action.setChecked(name == self._editor.workspace())
            action.triggered.connect(lambda _checked, value=name: self._set_workspace(value))
            group.addAction(action)
            self._workspace_menu.addAction(action)
            self._workspace_actions[name] = action
        view.addSeparator()

        self._panels_menu = view.addMenu("")
        self._panel_actions: dict[str, QAction] = {}
        for key, dock in self._editor.panels().items():
            action = dock.toggleViewAction()
            self._panels_menu.addAction(action)
            self._panel_actions[key] = action
        view.addSeparator()

        self._save_layout_action = QAction(self)
        self._save_layout_action.triggered.connect(self._editor.save_workspace)
        view.addAction(self._save_layout_action)
        self._reset_layout_action = QAction(self)
        self._reset_layout_action.triggered.connect(self._editor.reset_workspace)
        view.addAction(self._reset_layout_action)
        view.addSeparator()

        self._language_menu = view.addMenu("")
        language_group = QActionGroup(self)
        language_group.setExclusive(True)
        self._language_actions: dict[str, QAction] = {}
        for code, label in LANGUAGES.items():
            action = QAction(label, self, checkable=True)
            action.setChecked(code == self._t.locale)
            action.triggered.connect(lambda _checked, value=code: self._set_locale(value))
            language_group.addAction(action)
            self._language_menu.addAction(action)
            self._language_actions[code] = action

        self._t.changed.connect(self._retranslate_view)
        self._retranslate_view()

    def _retranslate_view(self) -> None:
        t = self._t.t
        self._view_menu.setTitle(t("menu.view"))
        self._workspace_menu.setTitle(t("menu.view.workspace"))
        self._panels_menu.setTitle(t("menu.view.panels"))
        self._save_layout_action.setText(t("menu.view.save_layout"))
        self._reset_layout_action.setText(t("menu.view.reset_layout"))
        self._language_menu.setTitle(t("menu.view.language"))
        for code, action in self._language_actions.items():
            action.setChecked(code == self._t.locale)

    def _set_workspace(self, name: str) -> None:
        self._editor.set_workspace(name)
        for key, action in self._workspace_actions.items():
            action.setChecked(key == name)

    def _set_locale(self, locale: str) -> None:
        self._t.set_locale(locale)
        for code, action in self._language_actions.items():
            action.setChecked(code == self._t.locale)

    # -- page switching ------------------------------------------------------

    def show_start(self) -> None:
        self._refresh_recents()
        self._stack.setCurrentWidget(self._start)

    def show_workspace(self) -> None:
        self._stack.setCurrentWidget(self._editor)
        self._refresh_project_label()

    # -- recents -------------------------------------------------------------

    def _recent_paths(self) -> list[Path]:
        raw = self._settings.value(_RECENT_KEY, [])
        if isinstance(raw, str):
            raw = [raw]
        paths: list[Path] = []
        seen: set[str] = set()
        for item in raw or []:
            path = Path(str(item))
            key = str(path)
            if key in seen or not path.is_file():
                continue
            seen.add(key)
            paths.append(path)
        return paths[:_RECENT_LIMIT]

    def _save_recents(self, paths: list[Path]) -> None:
        self._settings.setValue(_RECENT_KEY, [str(path) for path in paths[:_RECENT_LIMIT]])

    def _remember_project(self, path: object) -> None:
        if not isinstance(path, Path):
            self._refresh_project_label()
            return
        recents = [path, *[item for item in self._recent_paths() if item != path]]
        self._save_recents(recents)
        self._refresh_recents()
        self._refresh_project_label()

    def _refresh_recents(self) -> None:
        self._recents.clear()
        paths = self._recent_paths()
        self._empty_recents.setVisible(not paths)
        self._recents.setVisible(bool(paths))
        for path in paths:
            item = QListWidgetItem(f"{path.stem}  —  {path}")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self._recents.addItem(item)

    def _open_recent_item(self, item: QListWidgetItem) -> None:
        self._editor.open_project(Path(str(item.data(Qt.ItemDataRole.UserRole))))
        self.show_workspace()

    def _new_project(self) -> None:
        self._editor.new_project()
        self.show_workspace()

    def _open_project(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, self._t.t("menu.file.open"), str(Path.cwd()), FILE_FILTER
        )
        if not chosen:
            return
        self._editor.open_project(Path(chosen))
        self.show_workspace()
