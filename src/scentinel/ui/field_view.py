"""Visual presentation of real OpenFOAM concentration fields."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from scentinel.core import post


class FieldResultView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._case_dir: Path | None = None
        self._sensors: list = []
        self._image_path: Path | None = None
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel("Gas field"))
        self._gas = QComboBox(); self._gas.currentTextChanged.connect(self._render_selected)
        header.addWidget(self._gas); header.addStretch(1)
        self._stats = QLabel("Run a simulation to render the real OpenFOAM field.")
        header.addWidget(self._stats)
        layout.addLayout(header)
        self._image = QLabel(); self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setMinimumHeight(260); self._image.setText("No field available")
        layout.addWidget(self._image, 1)

    def set_case(self, case_dir: Path, sensors: list) -> None:
        self._case_dir = Path(case_dir); self._sensors = list(sensors)
        fields = post.concentration_fields(self._case_dir)
        self._gas.blockSignals(True); self._gas.clear(); self._gas.addItems(fields); self._gas.blockSignals(False)
        if fields: self._render_selected(fields[0])

    def _render_selected(self, gas: str) -> None:
        if not gas or self._case_dir is None: return
        image_path = self._case_dir.parent / f"field-{gas}.png"
        summary = post.render_concentration_field(self._case_dir, gas, image_path, sensors=self._sensors)
        self._image_path = image_path
        self._stats.setText(
            f"min {summary.minimum_ppmv:.4g} · mean {summary.mean_ppmv:.4g} · "
            f"max {summary.maximum_ppmv:.4g} ppmv · hotspot "
            f"({summary.hotspot_x_m:.2f}, {summary.hotspot_y_m:.2f}) m"
        )
        self._set_pixmap()

    def _set_pixmap(self) -> None:
        if self._image_path and self._image_path.exists():
            pixmap = QPixmap(str(self._image_path))
            self._image.setPixmap(pixmap.scaled(self._image.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event); self._set_pixmap()
