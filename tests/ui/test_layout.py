"""Layout regressions: panes must stay resizable and no content may be clipped.

These guard the failure modes that are invisible to behavioural tests: a hard
minimum height on a nested widget propagates up through the tab widget, pins the
whole panel, and starves the pane above it — while every other test still passes.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QDockWidget,
    QGroupBox,
    QScrollArea,
    QSplitter,
    QTabWidget,
)

from scentinel.ui.i18n import Translator
from scentinel.ui.main_window import MainWindow
from scentinel.ui.sensor_sandbox import SensorSandbox

SMALL = (760, 520)
NORMAL = (1440, 900)


@pytest.fixture
def window(qapp, translator):
    widget = MainWindow(translator)
    yield widget
    widget.close()
    widget.deleteLater()


def _splitters(window: MainWindow) -> list[QSplitter]:
    return window.findChildren(QSplitter)


def test_splitters_allow_the_user_to_drag_panes(window):
    window.resize(*NORMAL)
    window.show()
    qapp = window.parent()
    splitters = _splitters(window)
    assert splitters, "expected the workspace to use splitters"
    for splitter in splitters:
        assert splitter.childrenCollapsible(), "panes must be collapsible"
        for index in range(splitter.count() - 1):
            assert splitter.handle(index).isEnabled(), "every divider must be draggable"


def test_panes_are_not_pinned_by_minimum_sizes(window):
    """Panels must accept any size a drag could produce.

    A drag calls ``setSizes`` internally, so this exercises the same path
    without depending on handle geometry, which the offscreen platform does not
    lay out. The bounds asserted here are the floors the window declares.
    """
    window.resize(*NORMAL)
    window.show()
    horizontal = next(s for s in _splitters(window) if s.orientation() == Qt.Orientation.Horizontal)
    horizontal.setSizes([620, 820])
    QApplication.processEvents()
    wide, narrow = horizontal.sizes()
    assert wide > 600, f"setup panel refused to grow: {horizontal.sizes()}"

    horizontal.setSizes([260, 1180])
    QApplication.processEvents()
    small, large = horizontal.sizes()
    assert small < wide, "setup panel refused to shrink"
    assert large > narrow, "workspace refused to grow"

    vertical = next(s for s in _splitters(window) if s.orientation() == Qt.Orientation.Vertical)
    vertical.setSizes([640, 220])
    QApplication.processEvents()
    assert vertical.sizes()[0] > 600, "viewport refused to grow"
    vertical.setSizes([200, 660])
    QApplication.processEvents()
    assert vertical.sizes()[0] < 400, "viewport refused to shrink"


def test_viewport_keeps_usable_height_in_a_small_window(window):
    """A tall results panel must not squeeze the viewport away."""
    window.resize(*SMALL)
    window.show()
    assert window.viewport().height() >= 160
    assert window.results_panel().height() >= 140


def test_viewport_grows_when_the_window_grows(window):
    window.resize(*SMALL)
    window.show()
    small = window.viewport().height()
    window.resize(*NORMAL)
    assert window.viewport().height() > small


def test_no_group_box_is_clipped_outside_a_scroll_area(window):
    """Every settings group must either fit or be reachable by scrolling."""
    for size in (NORMAL, SMALL):
        window.resize(*size)
        window.show()
        for group in window.findChildren(QGroupBox):
            layout = group.layout()
            if layout is None:
                continue
            needed = layout.sizeHint().height() + 24
            if needed <= group.height() + 4:
                continue
            ancestor = group.parent()
            reachable = False
            while ancestor is not None:
                if isinstance(ancestor, QAbstractScrollArea):
                    reachable = True
                    break
                ancestor = ancestor.parent()
            assert reachable, f"'{group.title()}' is clipped and not scrollable at {size}"


def test_results_tabs_stay_reachable_when_the_panel_is_short(window):
    window.resize(*SMALL)
    window.show()
    tabs = window.results_panel().findChild(QTabWidget)
    assert tabs is not None
    for index in range(tabs.count()):
        page = tabs.widget(index)
        inner = page.widget() if isinstance(page, QScrollArea) else page
        if inner is None:
            continue
        if inner.sizeHint().height() <= page.height() + 4:
            continue
        assert isinstance(page, QScrollArea) and page.verticalScrollBar().maximum() > 0, (
            f"tab '{tabs.tabText(index)}' is clipped and cannot be scrolled"
        )


def test_field_view_can_shrink(window):
    """The field tab must not impose a floor on the whole results panel."""
    assert window.results_panel()._field_view.minimumSizeHint().height() < 200


def test_window_has_a_minimum_size(window):
    assert window.minimumWidth() > 0
    assert window.minimumHeight() > 0


class TestSensorLab:
    """The sensor lab dock is the one that used to crop its own fields."""

    @pytest.fixture
    def sandbox(self, qapp, translator):
        widget = SensorSandbox(translator)
        widget.resize(*NORMAL)
        widget.show()
        widget.set_lab_visible(True)
        yield widget
        widget.close()
        widget.deleteLater()

    def test_every_lab_tab_is_scrollable(self, sandbox):
        dock = sandbox._sensor_dock
        tabs = dock.findChild(QTabWidget)
        assert isinstance(tabs, QTabWidget)
        for index in range(tabs.count()):
            assert isinstance(tabs.widget(index), QScrollArea), (
                f"lab tab '{tabs.tabText(index)}' must be scrollable"
            )

    def test_lab_content_is_reachable_when_the_dock_is_short(self, sandbox):
        dock = sandbox._sensor_dock
        sandbox.resizeDocks([dock], [150], Qt.Orientation.Vertical)
        QApplication.processEvents()
        tabs = dock.findChild(QTabWidget)
        page = tabs.widget(0)  # sensor models, the tallest page
        inner = page.widget()
        assert inner.sizeHint().height() > page.viewport().height(), (
            "test needs a page taller than the viewport to be meaningful"
        )
        assert page.verticalScrollBar().maximum() > 0
        page.verticalScrollBar().setValue(page.verticalScrollBar().maximum())
        assert page.verticalScrollBar().value() == page.verticalScrollBar().maximum()

    def test_lab_dock_can_be_shrunk_to_its_title_bar(self, sandbox):
        """The dock's floor must come from its content only when reachable.

        QMainWindowLayout re-applies a floor from minimumSizeHint on every
        resize, so the content is wrapped to stop advertising one.
        """
        dock = sandbox._sensor_dock
        sandbox.resizeDocks([dock], [90], Qt.Orientation.Vertical)
        QApplication.processEvents()
        assert dock.height() <= 120, f"dock stayed at {dock.height()}px"
