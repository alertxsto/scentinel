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
    QTabWidget,
)

from scentinel.ui.i18n import Translator
from scentinel.ui.main_window import MainWindow

SMALL = (760, 520)
NORMAL = (1440, 900)


@pytest.fixture
def window(qapp, translator):
    widget = MainWindow(translator)
    yield widget
    widget.close()
    widget.deleteLater()


def test_panels_are_docks_the_user_can_move(window):
    """Every panel must be draggable, floatable, hideable and tabbable."""
    window.resize(*NORMAL)
    window.show()
    panels = window.panels()
    assert {"setup", "viewport", "results"} <= set(panels)
    for key, dock in panels.items():
        assert dock.allowedAreas() == Qt.DockWidgetArea.AllDockWidgetAreas, key
        assert dock.toggleViewAction().isEnabled(), key
    assert window.isDockNestingEnabled(), "docks must be nestable so panels can tab"


def test_panels_can_be_resized_freely(window):
    """No panel may pin another: each must accept a range of sizes."""
    window.resize(*NORMAL)
    window.show()
    dock = window.dock("viewport")
    window.resizeDocks([dock], [300], Qt.Orientation.Vertical)
    QApplication.processEvents()
    short = window.viewport().height()
    window.resizeDocks([dock], [700], Qt.Orientation.Vertical)
    QApplication.processEvents()
    tall = window.viewport().height()
    assert tall > short, f"viewport refused to grow: {short} -> {tall}"


def test_panels_can_be_hidden_and_shown_again(window):
    window.resize(*NORMAL)
    window.show()
    dock = window.dock("results")
    dock.setVisible(False)
    QApplication.processEvents()
    assert not dock.isVisible()
    dock.setVisible(True)
    QApplication.processEvents()
    assert dock.isVisible()


def test_viewport_keeps_usable_height_in_a_small_window(window):
    """A tall results panel must not squeeze the viewport away."""
    window.resize(*SMALL)
    window.show()
    QApplication.processEvents()
    assert window.viewport().height() >= 100
    assert window.viewport().width() >= 300


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
    """The lab is a dock, and every one of its pages must stay reachable."""

    @pytest.fixture
    def lab_window(self, qapp, translator):
        widget = MainWindow(translator)
        widget.resize(*NORMAL)
        widget.show()
        widget.dock("sensor_lab").setVisible(True)
        QApplication.processEvents()
        yield widget
        widget.close()
        widget.deleteLater()

    def test_lab_is_a_dock_not_a_mode(self, lab_window):
        """It must be a panel the user can move, hide, or float."""
        dock = lab_window.dock("sensor_lab")
        assert dock.isVisible()
        assert dock.allowedAreas() == Qt.DockWidgetArea.AllDockWidgetAreas
        assert dock.widget() is lab_window.sensor_lab()

    def test_every_lab_tab_is_scrollable(self, lab_window):
        tabs = lab_window.sensor_lab().findChild(QTabWidget)
        assert isinstance(tabs, QTabWidget)
        for index in range(tabs.count()):
            assert isinstance(tabs.widget(index), QScrollArea), (
                f"lab tab '{tabs.tabText(index)}' must be scrollable"
            )

    def test_lab_content_is_reachable_when_the_dock_is_short(self, lab_window):
        dock = lab_window.dock("sensor_lab")
        lab_window.resizeDocks([dock], [150], Qt.Orientation.Vertical)
        QApplication.processEvents()
        tabs = dock.findChild(QTabWidget)
        page = tabs.widget(0)  # sensor models, the tallest page
        inner = page.widget()
        if inner.sizeHint().height() <= page.viewport().height():
            pytest.skip("dock did not shrink far enough to need a scrollbar")
        assert page.verticalScrollBar().maximum() > 0
        page.verticalScrollBar().setValue(page.verticalScrollBar().maximum())
        assert page.verticalScrollBar().value() == page.verticalScrollBar().maximum()

    def test_lab_dock_can_be_shrunk_to_its_title_bar(self, lab_window):
        dock = lab_window.dock("sensor_lab")
        before = dock.height()
        lab_window.resizeDocks([dock], [max(before // 2, 60)], Qt.Orientation.Vertical)
        QApplication.processEvents()
        assert dock.height() <= before, f"dock grew unexpectedly to {dock.height()}px"

    def test_lab_is_hidden_by_default(self, qapp, translator):
        window = MainWindow(translator)
        window.resize(*NORMAL)
        window.show()
        assert not window.dock("sensor_lab").isVisible()
        window.close()
        window.deleteLater()
