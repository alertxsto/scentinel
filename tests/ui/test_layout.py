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


def test_dragging_the_horizontal_divider_changes_pane_widths(window):
    """The divider must actually move panes, not just be enabled."""
    window.resize(*NORMAL)
    window.show()
    horizontal = next(s for s in _splitters(window) if s.orientation() == Qt.Orientation.Horizontal)
    before = horizontal.sizes()
    handle = horizontal.handle(0)
    # moveSplitter takes a position along the splitter, so aim past the handle.
    horizontal.moveSplitter(handle.x() + handle.width() + 120, 0)
    after = horizontal.sizes()
    assert after != before, "dragging the divider must resize the panes"
    assert after[0] > before[0], "the setup panel should have grown"


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
        dock = next(d for d in sandbox.findChildren(QDockWidget) if d.isVisible())
        tabs = dock.widget()
        assert isinstance(tabs, QTabWidget)
        for index in range(tabs.count()):
            assert isinstance(tabs.widget(index), QScrollArea), (
                f"lab tab '{tabs.tabText(index)}' must be scrollable"
            )

    def test_lab_content_is_reachable_when_the_dock_is_short(self, sandbox):
        dock = sandbox._sensor_dock
        sandbox.resizeDocks([dock], [150], Qt.Orientation.Vertical)
        tabs = dock.widget()
        page = tabs.widget(0)  # sensor models, the tallest page
        inner = page.widget()
        assert inner.sizeHint().height() > page.viewport().height(), (
            "test needs a page taller than the viewport to be meaningful"
        )
        assert page.verticalScrollBar().maximum() > 0
        page.verticalScrollBar().setValue(page.verticalScrollBar().maximum())
        assert page.verticalScrollBar().value() == page.verticalScrollBar().maximum()

    def test_lab_dock_has_no_hard_minimum(self, sandbox):
        assert sandbox._sensor_dock.minimumHeight() == 0
