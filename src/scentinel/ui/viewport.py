"""2D cross-section viewport: draws the bin + mound and places sensor points.

Scene units are metres; ``y`` is flipped so that model ``+y`` points up on
screen. Sensor markers carry a screen-constant label so the identifier stays
readable at any zoom level.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView, QWidget

from scentinel.core.geometry import BinGeometry, bin_polygon, mound_polygon, placement_problem
from scentinel.core.project import Sensor

GRID_STEP_M = 0.5
MARGIN_FRACTION = 0.08
DIMENSION_GUTTER_M = 0.45
SENSOR_RADIUS_M = 0.06
LABEL_OFFSET_M = 0.09

COLOR_BACKGROUND = "#fbfbfa"
COLOR_BIN_FILL = "#f2f4f3"
COLOR_BIN_LINE = "#3d3d3d"
COLOR_MOUND_FILL = "#c8a165"
COLOR_MOUND_LINE = "#7a5230"
COLOR_GRID = "#dcdcdc"
COLOR_SENSOR = "#d32f2f"
COLOR_SENSOR_TEXT = "#7f1d1d"
COLOR_LABEL = "#4b4b4b"


class ViewportWidget(QGraphicsView):
    """Interactive cross-section: click to place, right-click to remove."""

    sensor_added = Signal(object)
    sensor_removed = Signal(object)
    sensors_changed = Signal()
    cursor_moved = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setMouseTracking(True)
        self.setBackgroundBrush(QBrush(QColor(COLOR_BACKGROUND)))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        self._geom = BinGeometry()
        self._sensors: list[Sensor] = []
        self._markers: dict[str, QGraphicsSimpleTextItem] = {}
        self._label_font = QFont()
        self._label_font.setPointSizeF(8.0)

        self._rebuild()

    # -- model ---------------------------------------------------------------

    def geometry(self) -> BinGeometry:
        return self._geom

    def set_geometry(self, geom: BinGeometry) -> None:
        self._geom = geom
        dropped = [s for s in self._sensors if not self.is_placeable(s.x, s.y)]
        if dropped:
            self._sensors = [s for s in self._sensors if s not in dropped]
            for sensor in dropped:
                self.sensor_removed.emit(sensor)
        self._rebuild(refit=True)
        self.sensors_changed.emit()

    def sensors(self) -> list[Sensor]:
        return list(self._sensors)

    def set_sensors(self, sensors: list[Sensor]) -> None:
        self._sensors = [s for s in sensors if self.is_placeable(s.x, s.y)]
        self._rebuild()
        self.sensors_changed.emit()

    def clear_sensors(self) -> None:
        if not self._sensors:
            return
        for sensor in self._sensors:
            self.sensor_removed.emit(sensor)
        self._sensors.clear()
        self._rebuild()
        self.sensors_changed.emit()

    def is_placeable(self, x: float, y: float) -> bool:
        """True when (x, y) is inside the bin and clear of the waste mound."""
        return not placement_problem(self._geom, x, y)

    def add_sensor(self, x: float, y: float) -> Sensor | None:
        if not self.is_placeable(x, y):
            return None
        sensor = Sensor(sensor_id=self._next_id(), x=round(x, 3), y=round(y, 3))
        self._sensors.append(sensor)
        self._draw_sensor(sensor)
        self.sensor_added.emit(sensor)
        self.sensors_changed.emit()
        return sensor

    def remove_sensor(self, sensor_id: str) -> None:
        for sensor in list(self._sensors):
            if sensor.sensor_id == sensor_id:
                self._sensors.remove(sensor)
                self._rebuild()
                self.sensor_removed.emit(sensor)
                self.sensors_changed.emit()
                return

    def _next_id(self) -> str:
        used = {sensor.sensor_id for sensor in self._sensors}
        index = len(used) + 1
        while f"S{index}" in used:
            index += 1
        return f"S{index}"

    # -- rendering -----------------------------------------------------------

    def _rebuild(self, *, refit: bool = False) -> None:
        self._scene.clear()
        self._markers.clear()

        self._scene.addPolygon(
            self._to_scene(bin_polygon(self._geom)),
            QPen(QColor(COLOR_BIN_LINE), 0.0),
            QBrush(QColor(COLOR_BIN_FILL)),
        )
        self._draw_grid()
        self._scene.addPolygon(
            self._to_scene(mound_polygon(self._geom)),
            QPen(QColor(COLOR_MOUND_LINE), 0.0),
            QBrush(QColor(COLOR_MOUND_FILL)),
        )
        self._draw_dimensions()

        for sensor in self._sensors:
            self._draw_sensor(sensor)

        self._scene.setSceneRect(self._extent())
        if refit and self.viewport().width() > 0 and self.viewport().height() > 0:
            self.fit_to_window()

    def _draw_grid(self) -> None:
        pen = QPen(QColor(COLOR_GRID), 0.0)
        length, height = self._geom.length_m, self._geom.height_m
        steps_x = int(length / GRID_STEP_M)
        steps_y = int(height / GRID_STEP_M)
        for i in range(1, steps_x):
            x = i * GRID_STEP_M
            self._scene.addLine(x, 0.0, x, -height, pen)
        for j in range(1, steps_y):
            y = j * GRID_STEP_M
            self._scene.addLine(0.0, -y, length, -y, pen)

    def _draw_dimensions(self) -> None:
        geom = self._geom
        self._add_label(
            f"{geom.length_m:g} m",
            geom.length_m / 2.0,
            -geom.height_m - LABEL_OFFSET_M,
            COLOR_LABEL,
            align_center=True,
        )
        self._add_label(
            f"{geom.height_m:g} m",
            -DIMENSION_GUTTER_M + LABEL_OFFSET_M,
            -geom.height_m / 2.0,
            COLOR_LABEL,
        )

    def _draw_sensor(self, sensor: Sensor) -> None:
        radius = SENSOR_RADIUS_M
        self._scene.addEllipse(
            sensor.x - radius,
            -sensor.y - radius,
            radius * 2.0,
            radius * 2.0,
            QPen(QColor(COLOR_SENSOR), 0.0),
            QBrush(QColor(COLOR_SENSOR)),
        )
        marker = self._add_label(
            sensor.sensor_id,
            sensor.x + LABEL_OFFSET_M,
            -sensor.y - LABEL_OFFSET_M,
            COLOR_SENSOR_TEXT,
        )
        marker.setToolTip(f"{sensor.sensor_id}: x={sensor.x:.3f} m, y={sensor.y:.3f} m")
        self._markers[sensor.sensor_id] = marker

    def _add_label(
        self,
        text: str,
        x: float,
        y: float,
        color: str,
        *,
        align_center: bool = False,
    ) -> QGraphicsSimpleTextItem:
        item = QGraphicsSimpleTextItem(text)
        item.setBrush(QBrush(QColor(color)))
        item.setFont(self._label_font)
        item.setFlag(QGraphicsSimpleTextItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        item.setPos(x, y)
        if align_center:
            item.moveBy(-item.boundingRect().width() / 2.0, 0.0)
        self._scene.addItem(item)
        return item

    def _to_scene(self, points: list[tuple[float, float]]) -> QPolygonF:
        return QPolygonF([QPointF(x, -y) for x, y in points])

    def _extent(self) -> QRectF:
        """Scene rectangle covering the bin, in metres.

        Deliberately derived from the geometry rather than
        ``itemsBoundingRect()``: the sensor labels ignore view transforms, so
        their scene bounding box is expressed in pixels and would otherwise
        inflate the fitted area by the zoom factor.
        """
        margin = max(self._geom.length_m, self._geom.height_m) * MARGIN_FRACTION
        return QRectF(
            -margin - DIMENSION_GUTTER_M,
            -self._geom.height_m - margin,
            self._geom.length_m + 2.0 * margin + DIMENSION_GUTTER_M,
            self._geom.height_m + 2.0 * margin,
        )

    def fit_to_window(self) -> None:
        self._scene.setSceneRect(self._extent())
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def reset_view(self) -> None:
        self.resetTransform()
        self.fit_to_window()

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
        self.fit_to_window()

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001
        point = self.mapToScene(event.position().toPoint())
        self.cursor_moved.emit(point.x(), -point.y())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        point = self.mapToScene(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton:
            self.add_sensor(point.x(), -point.y())
        elif event.button() == Qt.MouseButton.RightButton:
            hit = self._sensor_at(point.x(), -point.y())
            if hit is not None:
                self.remove_sensor(hit.sensor_id)
        super().mousePressEvent(event)

    def _sensor_at(self, x: float, y: float) -> Sensor | None:
        threshold = SENSOR_RADIUS_M * 2.0
        best: tuple[float, Sensor] | None = None
        for sensor in self._sensors:
            distance = ((sensor.x - x) ** 2 + (sensor.y - y) ** 2) ** 0.5
            if distance <= threshold and (best is None or distance < best[0]):
                best = (distance, sensor)
        return None if best is None else best[1]
