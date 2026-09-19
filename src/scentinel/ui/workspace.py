"""Dock-based workspace shell, modelled on how Blender arranges its editors.

There is one workspace, not three modes. Every surface is a ``QDockWidget``, so
the user can drag any of them to another edge, tab two together, float one onto
a second monitor, or hide the ones they are not using. Qt's own dock system
supplies the drop indicators, the tab bars, and the float windows; the
application only has to name the areas and remember the result.

Layouts are persisted per named workspace under ``QSettings``, so a user can
keep a "setup" arrangement while placing sensors and a "review" arrangement for
reading results, and switch between them from the View menu.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSettings, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QTabWidget,
    QWidget,
)

from scentinel.ui.i18n import Translator

#: Named arrangements, in menu order. The first is the fallback.
WORKSPACES = ("Simulation", "Sensor lab", "Review")

_SETTINGS_GROUP = "workspaces"
_STATE_VERSION = 1


class DockedWorkspace(QMainWindow):
    """A single window whose panels dock, tab, float, and remember their places."""

    def __init__(
        self,
        translator: Translator,
        *,
        settings: QSettings | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._t = translator
        self._settings = settings or QSettings("Scentinel", "Scentinel")
        self._docks: dict[str, QDockWidget] = {}
        self._workspace = WORKSPACES[0]
        self._applying_layout = False
        self._needs_layout_pass = True

        self.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.GroupedDragging
        )
        self.setDockNestingEnabled(True)
        self.setTabPosition(
            Qt.DockWidgetArea.AllDockWidgetAreas, QTabWidget.TabPosition.North
        )

    # -- dock registration ---------------------------------------------------

    def add_panel(
        self,
        key: str,
        title: str,
        widget: QWidget,
        area: Qt.DockWidgetArea,
        *,
        min_size: tuple[int, int] | None = None,
    ) -> QDockWidget:
        """Register a dock under ``key`` so layouts can restore it by name."""
        dock = QDockWidget(title, self)
        dock.setObjectName(f"dock.{key}")
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setWidget(_flexible(widget))
        if min_size is not None:
            dock.setMinimumSize(*min_size)
        self.addDockWidget(area, dock)
        self._docks[key] = dock
        return dock

    def dock(self, key: str) -> QDockWidget:
        return self._docks[key]

    def panels(self) -> dict[str, QDockWidget]:
        return dict(self._docks)

    # -- workspaces ----------------------------------------------------------

    def workspace(self) -> str:
        return self._workspace

    def set_workspace(self, name: str) -> None:
        """Apply a named layout, falling back to the built-in default."""
        if name not in WORKSPACES:
            raise ValueError(f"unknown workspace {name!r}")
        self._workspace = name
        if self.isVisible():
            if not self._apply_saved_layout(name):
                self.apply_default_layout(name)
        else:
            self._needs_layout_pass = True

    def save_workspace(self, name: str | None = None) -> None:
        """Persist the current arrangement under the active workspace name."""
        name = name or self._workspace
        self._settings.beginGroup(_SETTINGS_GROUP)
        self._settings.setValue(f"{name}.version", _STATE_VERSION)
        self._settings.setValue(f"{name}.geometry", self.saveGeometry())
        self._settings.setValue(f"{name}.state", self.saveState(_STATE_VERSION))
        self._settings.endGroup()

    def reset_workspace(self, name: str | None = None) -> None:
        """Forget a saved layout and reapply the built-in default."""
        name = name or self._workspace
        self._settings.beginGroup(_SETTINGS_GROUP)
        self._settings.remove(name)
        self._settings.endGroup()
        self.apply_default_layout(name)

    def _apply_saved_layout(self, name: str) -> bool:
        self._settings.beginGroup(_SETTINGS_GROUP)
        version = self._settings.value(f"{name}.version")
        state = self._settings.value(f"{name}.state")
        geometry = self._settings.value(f"{name}.geometry")
        self._settings.endGroup()
        if version is None or state is None:
            return False
        try:
            if int(version) != _STATE_VERSION:
                return False
        except (TypeError, ValueError):
            return False

        self._applying_layout = True
        try:
            # A layout saved before a panel existed would hide the new panel
            # forever, so every dock is shown before the state is restored.
            for dock in self._docks.values():
                dock.setVisible(True)
            if not self.restoreState(_as_bytes(state), _STATE_VERSION):
                return False
            if geometry is not None:
                self.restoreGeometry(_as_bytes(geometry))
        finally:
            self._applying_layout = False
        return True

    def apply_default_layout(self, name: str | None = None) -> None:
        """The built-in arrangement for a workspace, used on first run.

        Each panel is re-added to its home area before being shown: a dock that
        was dragged elsewhere in a previous session would otherwise keep that
        place, because ``addDockWidget`` is what decides the area a dock belongs
        to when the state is not being restored.
        """
        name = name or self._workspace
        self._applying_layout = True
        try:
            for key, area in self._default_areas(name).items():
                dock = self._docks.get(key)
                if dock is None:
                    continue
                dock.setFloating(False)
                dock.setVisible(True)
                self.addDockWidget(area, dock)
            for key, dock in self._docks.items():
                dock.setVisible(key in self._layout_for(name))
            self._apply_default_sizes(name)
        finally:
            self._applying_layout = False

    def _apply_default_sizes(self, name: str) -> None:
        """Give the panels a sane split; without it Qt picks arbitrary ratios."""
        width = max(self.width(), 1200)
        height = max(self.height(), 800)
        for dock in self._docks.values():
            dock.setMinimumSize(0, 0)
        self.resizeDocks(
            [self._docks["setup"], self._docks["viewport"]],
            [380, width - 380],
            Qt.Orientation.Horizontal,
        )
        if "results" in self._docks and self._docks["results"].isVisible():
            self.resizeDocks(
                [self._docks["viewport"], self._docks["results"]],
                [height - 340, 340],
                Qt.Orientation.Vertical,
            )
        self.resizeDocks(
            [self._docks["setup"], self._docks["viewport"]],
            [380, width - 380],
            Qt.Orientation.Horizontal,
        )

    def showEvent(self, event) -> None:  # noqa: ANN001
        """Apply the workspace layout once the window has a real size.

        ``resizeDocks`` only takes effect after the dock layout has been
        computed, which happens when the window is first shown. Calling it
        during construction leaves every panel at its minimum.
        """
        super().showEvent(event)
        if self._needs_layout_pass:
            self._needs_layout_pass = False
            if not self._apply_saved_layout(self._workspace):
                self.apply_default_layout(self._workspace)

    def _default_areas(self, name: str) -> dict[str, Qt.DockWidgetArea]:
        """Home area for each panel; the arrangement is the ordering."""
        return {
            "setup": Qt.DockWidgetArea.LeftDockWidgetArea,
            "viewport": Qt.DockWidgetArea.RightDockWidgetArea,
            "results": Qt.DockWidgetArea.BottomDockWidgetArea,
            "sensor_lab": Qt.DockWidgetArea.BottomDockWidgetArea,
        }

    def _layout_for(self, name: str) -> tuple[str, ...]:
        """Which panels are shown by default in each workspace."""
        if name == "Sensor lab":
            return ("setup", "viewport", "sensor_lab", "results")
        if name == "Review":
            return ("viewport", "results", "sensor_lab")
        return ("setup", "viewport", "results")


def _flexible(widget: QWidget) -> QWidget:
    """Let a docked widget shrink so the dock can be dragged small.

    A dock takes its floor from its content's minimum size hint, and
    ``QMainWindowLayout`` re-applies that floor on every resize. Panels that
    contain their own scroll areas do not need to advertise a minimum.
    """
    widget.setMinimumSize(0, 0)
    return widget


def _as_bytes(value: object) -> QByteArray:
    """QSettings returns a QByteArray or a str depending on the backend."""
    return value if isinstance(value, QByteArray) else QByteArray(bytes(value))  # type: ignore[arg-type]
