"""Application shell: dashboard, one project editor, studio and sandbox modes."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtGui import QAction, QActionGroup
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
from scentinel.ui.i18n import Translator
from scentinel.ui.sensor_sandbox import SensorSandbox

_RECENT_KEY = "recentProjects"
_RECENT_LIMIT = 8


class HomeWindow(QMainWindow):
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

        self._editor = SensorSandbox(translator, project=project, path=path)
        self._prepare_embedded(self._editor)
        self._editor.home_requested.connect(self.show_home)
        self._editor.back_requested.connect(self.show_home)
        self._editor.project_path_changed.connect(self._remember_project)

        self._stack = QStackedWidget()
        self._home = self._build_home()
        self._stack.addWidget(self._home)
        self._stack.addWidget(self._editor)
        self.setCentralWidget(self._stack)

        self._build_toolbar()
        self._refresh_recents()
        if path is not None:
            self._remember_project(path)
            QTimer.singleShot(0, self.show_studio)
        else:
            QTimer.singleShot(0, self.show_home)

    def _prepare_embedded(self, window: QMainWindow) -> None:
        window.setWindowFlags(Qt.WindowType.Widget)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        group = QActionGroup(self)
        group.setExclusive(True)
        self._act_home = QAction(self)
        self._act_studio = QAction(self)
        self._act_sandbox = QAction(self)
        for action, slot in (
            (self._act_home, self.show_home),
            (self._act_studio, self.show_studio),
            (self._act_sandbox, self.show_sandbox),
        ):
            action.setCheckable(True)
            action.triggered.connect(slot)
            group.addAction(action)
            toolbar.addAction(action)
        toolbar.addSeparator()
        self._project_label = QLabel()
        self._project_label.setObjectName("toolbarProject")
        toolbar.addWidget(self._project_label)
        self._retranslate_toolbar()
        self._t.changed.connect(self._retranslate_toolbar)

    def _retranslate_toolbar(self) -> None:
        t = self._t.t
        self._act_home.setText(t("nav.home"))
        self._act_studio.setText(t("nav.studio"))
        self._act_sandbox.setText(t("nav.sandbox"))
        self._refresh_project_label()

    def _refresh_project_label(self) -> None:
        path = self._editor.project_path()
        if path is not None:
            text = path.name
        else:
            text = self._t.t("home.untitled")
        if self._editor.is_dirty():
            text += " •"
        self._project_label.setText(text)

    def _build_home(self) -> QWidget:
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

        self._t.changed.connect(self._retranslate_home)
        self._retranslate_home()
        return page

    def _retranslate_home(self) -> None:
        t = self._t.t
        self._home_title.setText(t("home.title"))
        self._home_subtitle.setText(t("home.subtitle"))
        self._new_button.setText(t("home.new"))
        self._open_button.setText(t("home.open"))
        self._recent_caption.setText(t("home.recent"))
        self._empty_recents.setText(t("home.recent.empty"))

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
        path = Path(str(item.data(Qt.ItemDataRole.UserRole)))
        self._editor.open_project(path)
        self.show_studio()

    def _new_project(self) -> None:
        self._editor.new_project()
        self.show_studio()
        self._refresh_project_label()

    def _open_project(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, self._t.t("menu.file.open"), str(Path.cwd()), FILE_FILTER
        )
        if not chosen:
            return
        self._editor.open_project(Path(chosen))
        self.show_studio()

    def _select(self, page: QWidget, active: QAction) -> None:
        self._stack.setCurrentWidget(page)
        for action in (self._act_home, self._act_studio, self._act_sandbox):
            action.setChecked(action is active)
        self._refresh_project_label()

    def show_home(self) -> None:
        self._refresh_recents()
        self._select(self._home, self._act_home)

    def show_studio(self) -> None:
        self._editor.set_lab_visible(False)
        self._select(self._editor, self._act_studio)

    def show_sandbox(self) -> None:
        self._editor.set_lab_visible(True)
        self._select(self._editor, self._act_sandbox)
