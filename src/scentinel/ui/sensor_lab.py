"""Virtual-sensor laboratory: a dockable panel, not a separate mode.

The lab used to be a whole window that the toolbar swapped in place of the
editor, which forced a mode switch to compare a device model against the CFD
result. It is now an ordinary panel: dock it beside the viewport, tab it with
the results, float it, or hide it, and the project stays the same object.

The panel reads the project's sensor list and its latest run readings, so it
never holds a second copy of the geometry or the results.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from scentinel.core.project import Project
from scentinel.core.virtual_sensor import SENSOR_FAMILIES, VirtualSensorConfig, step_response
from scentinel.ui.i18n import Translator
from scentinel.ui.results_panel import SensorReading


def _scrollable(page: QWidget) -> QScrollArea:
    """Wrap a tab page so its content stays reachable at any panel height."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    area.setWidget(page)
    return area


class SensorLabPanel(QWidget):
    """Per-sensor emulation driven by lab settings, fed by the project's results.

    The panel does not own the project. The host window pushes state in through
    :meth:`set_context` and listens to :attr:`config_changed`, so the lab can be
    docked, floated, or hidden without holding a reference to the editor.
    """

    config_changed = Signal(object)  # VirtualSensorConfig

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._t = translator
        self._elapsed = 0.0
        self._sample = 0
        self._values: dict[str, float] = {}
        self._detected_at: dict[str, float] = {}
        self._sensors: list = []
        self._readings: list[SensorReading] = []
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget()
        tabs.setMinimumHeight(0)
        tabs.addTab(_scrollable(self._build_model_tab()), "Sensor models")
        tabs.addTab(_scrollable(self._build_telemetry_tab()), "Telemetry")
        tabs.addTab(_scrollable(self._build_evaluation_tab()), "Evaluation")
        layout.addWidget(tabs)
        self._tabs = tabs

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.advance)

    # -- host interface ------------------------------------------------------

    def set_context(self, sensors: list, readings: list[SensorReading]) -> None:
        """Push the current sensor list and run readings into the lab."""
        self._sensors = list(sensors)
        self._readings = list(readings)
        self._sync_sensors()

    def set_config(self, config: VirtualSensorConfig) -> None:
        """Load a saved device model without emitting :attr:`config_changed`."""
        self._loading = True
        try:
            widgets = (
                self.family, self.range, self.lod, self.response,
                self.recovery, self.noise, self.drift, self.cross_factor,
            )
            for widget in widgets:
                widget.blockSignals(True)
            index = self.family.findText(config.family)
            if index >= 0:
                self.family.setCurrentIndex(index)
            self.range.setValue(config.range_ppm)
            self.lod.setValue(config.detection_limit_ppm)
            self.response.setValue(config.response_time_s)
            self.recovery.setValue(config.recovery_time_s)
            self.noise.setValue(config.noise_ppm)
            self.drift.setValue(config.drift_ppm_h)
            self.cross_factor.setValue(config.cross_sensitivity)
            for widget in widgets:
                widget.blockSignals(False)
        finally:
            self._loading = False

    def config(self) -> VirtualSensorConfig:
        return VirtualSensorConfig(
            family=self.family.currentText(),
            range_ppm=self.range.value(),
            detection_limit_ppm=self.lod.value(),
            response_time_s=self.response.value(),
            recovery_time_s=self.recovery.value(),
            cross_sensitivity=self.cross_factor.value(),
            noise_ppm=self.noise.value(),
            drift_ppm_h=self.drift.value(),
        )

    def is_replaying(self) -> bool:
        return self._timer.isActive()

    def stop(self) -> None:
        self._timer.stop()
        self._replay_button.setText("Start sensor replay")

    # -- construction --------------------------------------------------------

    def _build_model_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        note = QLabel(
            "Replay uses each placed sensor's CFD VOC (or the selected gas) as TVOC "
            "ground truth, then applies the lab model below. Fallback ppm is used "
            "only when that sensor has no run result yet."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        exposure = QGroupBox("Replay input")
        eform = QFormLayout(exposure)
        self.truth = self._spin(0, 1_000_000, 25, " ppm")
        self.cross = self._spin(0, 1_000_000, 0, " ppm")
        self.temperature = self._spin(-20, 80, 25, " °C")
        self.humidity = self._spin(0, 100, 50, " %RH")
        eform.addRow("Ground truth fallback", self.truth)
        eform.addRow("Interfering gas fallback", self.cross)
        eform.addRow("Temperature", self.temperature)
        eform.addRow("Humidity", self.humidity)
        layout.addWidget(exposure)
        model = QGroupBox("Selected sensor model")
        form = QFormLayout(model)
        self.family = QComboBox()
        self.family.addItems(SENSOR_FAMILIES)
        self.range = self._spin(0.1, 1_000_000, 1000, " ppm")
        self.lod = self._spin(0, 1000, 0.01, " ppm", 3)
        self.response = self._spin(0.1, 600, 2, " s")
        self.recovery = self._spin(0.1, 1200, 5, " s")
        self.noise = self._spin(0, 1000, 0.01, " ppm", 3)
        self.drift = self._spin(-100, 100, 0, " ppm/h", 3)
        self.cross_factor = self._spin(-10, 10, 0, " ×", 3)
        for label, widget in (
            ("Technology", self.family),
            ("Range", self.range),
            ("LOD", self.lod),
            ("Response time", self.response),
            ("Recovery time", self.recovery),
            ("Noise", self.noise),
            ("Drift", self.drift),
            ("Cross-sensitivity", self.cross_factor),
        ):
            form.addRow(label, widget)
        layout.addWidget(model)
        controls = QHBoxLayout()
        self._replay_button = QPushButton("Start sensor replay")
        self._replay_button.clicked.connect(self.toggle)
        reset = QPushButton("Reset sensor state")
        reset.clicked.connect(self.reset_sensor_state)
        controls.addWidget(self._replay_button)
        controls.addWidget(reset)
        layout.addLayout(controls)
        layout.addStretch(1)
        for widget in (
            self.family, self.range, self.lod, self.response, self.recovery,
            self.noise, self.drift, self.cross_factor, self.temperature, self.humidity,
        ):
            if widget is self.family:
                widget.currentIndexChanged.connect(self._store_lab)
            else:
                widget.valueChanged.connect(self._store_lab)
        return tab

    def _build_telemetry_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._telemetry = QTableWidget(0, 8)
        self._telemetry.setMinimumHeight(0)
        self._telemetry.setHorizontalHeaderLabels(
            [
                "Sensor", "Technology", "Source", "Ground truth",
                "Indicated", "Error", "State", "Detection time",
            ]
        )
        layout.addWidget(self._telemetry)
        return tab

    def _build_evaluation_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        title = QLabel("Placement and device evaluation")
        self._evaluation = QLabel()
        self._evaluation.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(self._evaluation)
        layout.addStretch(1)
        self._refresh_evaluation()
        return tab

    @staticmethod
    def _spin(low: float, high: float, value: float, suffix: str, decimals: int = 2) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setDecimals(decimals)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.setKeyboardTracking(False)
        return spin

    # -- state ---------------------------------------------------------------

    def _store_lab(self, *_args: object) -> None:
        if self._loading:
            return
        self.config_changed.emit(self.config())

    def _exposure(self, sensor_id: str) -> tuple[float, float, str]:
        """Return (truth ppm, cross ppm, source label) for one sensor."""
        for reading in self._readings:
            if reading.sensor_id != sensor_id:
                continue
            if "VOC" in reading.values:
                truth, source = reading.values["VOC"], "cfd-voc"
            elif reading.values:
                gas, truth = next(iter(reading.values.items()))
                source = f"cfd-{gas.lower()}"
            else:
                break
            cross = 0.0
            for gas in ("CH4", "H2S", "CO"):
                if gas in reading.values:
                    cross += reading.values[gas]
            return truth, cross if cross else self.cross.value(), source
        return self.truth.value(), self.cross.value(), "lab-fallback"

    def _sync_sensors(self) -> None:
        live = {sensor.sensor_id for sensor in self._sensors}
        self._values = {k: v for k, v in self._values.items() if k in live}
        self._detected_at = {k: v for k, v in self._detected_at.items() if k in live}
        self._telemetry.setRowCount(len(self._sensors))
        for row, sensor in enumerate(self._sensors):
            truth, _cross, source = self._exposure(sensor.sensor_id)
            indicated = self._values.get(sensor.sensor_id)
            cells = (
                sensor.sensor_id,
                self.family.currentText(),
                source,
                f"{truth:.4f} ppm",
                f"{indicated:.4f} ppm" if indicated is not None else "—",
                f"{indicated - truth:+.4f} ppm" if indicated is not None else "—",
                "ready" if indicated is None else "measuring",
                f"{self._detected_at[sensor.sensor_id]:.2f} s"
                if sensor.sensor_id in self._detected_at else "—",
            )
            for column, text in enumerate(cells):
                self._telemetry.setItem(row, column, QTableWidgetItem(text))
        self._refresh_evaluation()

    # -- replay --------------------------------------------------------------

    def toggle(self) -> None:
        if not self._sensors:
            return
        if self._timer.isActive():
            self._timer.stop()
            self._replay_button.setText("Continue sensor replay")
        else:
            self._timer.start()
            self._replay_button.setText("Pause sensor replay")

    def reset_sensor_state(self) -> None:
        self._timer.stop()
        self._elapsed = 0
        self._sample = 0
        self._values.clear()
        self._detected_at.clear()
        self._replay_button.setText("Start sensor replay")
        self._sync_sensors()

    def advance(self) -> None:
        step = self._timer.interval() / 1000.0
        self._elapsed += step
        config = self.config()
        for row, sensor in enumerate(self._sensors):
            truth, cross, source = self._exposure(sensor.sensor_id)
            reading = step_response(
                config,
                ground_truth_ppm=truth,
                previous_ppm=self._values.get(sensor.sensor_id, 0.0),
                elapsed_s=self._elapsed,
                step_s=step,
                temperature_c=self.temperature.value(),
                humidity_rh=self.humidity.value(),
                cross_gas_ppm=cross,
                sample_index=self._sample + row,
            )
            self._values[sensor.sensor_id] = reading.indicated_ppm
            if (
                reading.indicated_ppm >= config.detection_limit_ppm
                and sensor.sensor_id not in self._detected_at
            ):
                self._detected_at[sensor.sensor_id] = self._elapsed
            state = (
                "saturated" if reading.saturated
                else "below LOD" if reading.below_detection
                else "measuring"
            )
            values = (
                sensor.sensor_id,
                config.family,
                source,
                f"{truth:.4f} ppm",
                f"{reading.indicated_ppm:.4f} ppm",
                f"{reading.indicated_ppm - truth:+.4f} ppm",
                state,
                f"{self._detected_at[sensor.sensor_id]:.2f} s"
                if sensor.sensor_id in self._detected_at else "—",
            )
            for column, text in enumerate(values):
                item = self._telemetry.item(row, column)
                if item is None:
                    self._telemetry.setItem(row, column, QTableWidgetItem(text))
                else:
                    item.setText(text)
        self._sample += 1
        self._refresh_evaluation()

    def _refresh_evaluation(self) -> None:
        count = len(self._sensors)
        detected = len(self._detected_at)
        errors = []
        for sensor in self._sensors:
            if sensor.sensor_id not in self._values:
                continue
            truth, _, _ = self._exposure(sensor.sensor_id)
            errors.append(abs(self._values[sensor.sensor_id] - truth))
        mean_error = sum(errors) / len(errors) if errors else None
        if mean_error is not None:
            self._evaluation.setText(
                f"Placed sensors: {count}\nDetected exposure: {detected}/{count}\n"
                f"Mean absolute indication error: {mean_error:.4f} ppm\n"
                "Ground truth is CFD VOC at each sensor when a run result exists; "
                "otherwise the lab fallback."
            )
        else:
            self._evaluation.setText(
                f"Placed sensors: {count}\nDetected exposure: {detected}/{count}\n"
                "Run CFD or replay a controlled exposure to populate "
                "device-performance metrics.\n\n"
                "Coverage and blind-zone scores require a spatial concentration "
                "field; they are not inferred from probe-only data."
            )
