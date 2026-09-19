"""Regression tests: no control may be clipped without a way to reach it.

The failure these guard against is quiet. A row built as a form row puts its
checkbox in the label column, so the label plus the value field plus the "auto"
box can demand more width than the panel has; the controls stay functional and
every behavioural test passes, but the user has to drag the panel wider to see
them.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QCheckBox,
    QComboBox,
    QPushButton,
    QSplitter,
)

from scentinel.core.gas_data import DEFAULT_SOURCE_GASES, short_label
from scentinel.ui.main_window import MainWindow

NORMAL = (1440, 900)


@pytest.fixture
def window(qapp, translator):
    widget = MainWindow(translator)
    widget.resize(*NORMAL)
    widget.show()
    yield widget
    widget.close()
    widget.deleteLater()


def _panel(window: MainWindow):
    return window.setup_panel()


def test_setup_panel_fits_without_horizontal_scrolling(window):
    """The default layout must show every control, not require a sideways drag."""
    panel = _panel(window)
    overflow = panel.horizontalScrollBar().maximum()
    assert overflow == 0, (
        f"setup panel needs {overflow}px of horizontal scrolling at {NORMAL[0]}px"
    )


@pytest.mark.parametrize("gas", DEFAULT_SOURCE_GASES)
def test_each_gas_row_is_fully_visible(window, gas):
    """Checkbox, value field and auto box must all be on screen."""
    panel = _panel(window)
    viewport = panel.viewport().width()
    for widget in (panel._gas_boxes[gas], panel._gas_spins[gas], panel._gas_auto[gas]):
        right = widget.mapTo(panel.viewport(), widget.rect().topRight()).x()
        assert right <= viewport, (
            f"{gas}: control reaches {right}px in a {viewport}px viewport"
        )


@pytest.mark.parametrize("gas", DEFAULT_SOURCE_GASES)
def test_gas_label_is_short_enough_for_the_panel(gas):
    """A label wider than the panel clips its own row."""
    assert short_label(gas)
    assert len(short_label(gas)) <= 20, f"'{short_label(gas)}' is too long for a dense row"


def test_controls_are_reachable_when_the_panel_is_narrow(window):
    """A squeezed panel may scroll, but nothing may be permanently hidden."""
    panel = _panel(window)
    splitter = next(
        s for s in window.findChildren(QSplitter) if s.orientation().name == "Horizontal"
    )
    splitter.setSizes([240, 1200])
    QApplication.processEvents()

    controls = []
    for cls in (QCheckBox, QPushButton, QComboBox):
        controls.extend(panel.findChildren(cls))
    viewport = panel.viewport().width()
    clipped = [
        c for c in controls if c.mapTo(panel.viewport(), c.rect().topRight()).x() > viewport
    ]
    if not clipped:
        return
    assert panel.horizontalScrollBar().maximum() > 0, (
        f"{len(clipped)} controls are clipped and the panel cannot scroll to them"
    )
    panel.horizontalScrollBar().setValue(panel.horizontalScrollBar().maximum())
    QApplication.processEvents()
    hidden = [
        c
        for c in controls
        if c.mapTo(panel.viewport(), c.rect().topRight()).x() > panel.viewport().width()
    ]
    assert not hidden, "controls remain clipped even after scrolling right"


def test_no_scroll_area_needs_horizontal_scrolling_at_normal_size(window):
    for area in window.findChildren(QAbstractScrollArea):
        overflow = area.horizontalScrollBar().maximum()
        assert overflow == 0, (
            f"{type(area).__name__} needs {overflow}px of horizontal scrolling"
        )
