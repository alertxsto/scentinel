"""Visual presentation of real OpenFOAM concentration fields.

The view is deliberately shrinkable. A large minimum height here propagates up
through the tab widget and pins the whole results panel, which then squeezes the
viewport to nothing when the window is made smaller. The image label therefore
has no minimum height of its own and rescales its pixmap on every resize.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from scentinel.core import post

#: Below this height the controls wrap instead of fighting for space.
COMPACT_HEIGHT_PX = 320


class FieldResultView(QWidget):
    """Gas selector, summary statistics, and the rendered concentration field."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._case_dir: Path | None = None
        self._sensors: list = []
        self._image_path: Path | None = None

        # The view must be able to shrink; the tab widget sizes itself from the
        # largest page, so a hard floor here starves the viewport above it.
        self.setMinimumHeight(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(6)
        self._gas_label = QLabel("Gas field")
        self._gas = QComboBox()
        self._gas.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._gas.currentTextChanged.connect(self._render_selected)
        header.addWidget(self._gas_label)
        header.addWidget(self._gas)
        header.addStretch(1)
        layout.addLayout(header)

        self._stats = QLabel("Run a simulation to render the real OpenFOAM field.")
        self._stats.setWordWrap(True)
        self._stats.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._stats)

        # The image sits in a scroll area so a wide or tall render stays
        # reachable instead of being cropped by the panel.
        self._image = QLabel()
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setMinimumSize(0, 0)
        self._image.setText("No field available")
        self._image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        self._image_scroll = QScrollArea()
        self._image_scroll.setWidgetResizable(True)
        self._image_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._image_scroll.setWidget(self._image)
        layout.addWidget(self._image_scroll, 1)

    # -- data ----------------------------------------------------------------

    def set_case(self, case_dir: Path, sensors: list) -> None:
        self._case_dir = Path(case_dir)
        self._sensors = list(sensors)
        fields = post.concentration_fields(self._case_dir)
        self._gas.blockSignals(True)
        self._gas.clear()
        self._gas.addItems(fields)
        self._gas.blockSignals(False)
        if fields:
            self._render_selected(fields[0])

    def _render_selected(self, gas: str) -> None:
        if not gas or self._case_dir is None:
            return
        image_path = self._case_dir.parent / f"field-{gas}.png"
        summary = post.render_concentration_field(
            self._case_dir, gas, image_path, sensors=self._sensors
        )
        self._image_path = image_path
        self._stats.setText(
            f"min {summary.minimum_ppmv:.4g} · mean {summary.mean_ppmv:.4g} · "
            f"max {summary.maximum_ppmv:.4g} ppmv · hotspot "
            f"({summary.hotspot_x_m:.2f}, {summary.hotspot_y_m:.2f}) m"
        )
        self._set_pixmap()

    # -- rendering -----------------------------------------------------------

    def _set_pixmap(self) -> None:
        if not (self._image_path and self._image_path.exists()):
            return
        target = self._image_scroll.viewport().size()
        if target.width() <= 0 or target.height() <= 0:
            return
        pixmap = QPixmap(str(self._image_path))
        if pixmap.isNull():
            return
        self._image.setPixmap(
            pixmap.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
        self._set_pixmap()
