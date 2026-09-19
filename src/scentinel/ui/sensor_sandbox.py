"""Simulation studio plus a virtual-sensor laboratory on the same project."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from scentinel.core.project import Project
from scentinel.core.virtual_sensor import SENSOR_FAMILIES, VirtualSensorConfig, step_response
from scentinel.ui.i18n import Translator
from scentinel.ui.main_window import MainWindow
from scentinel.ui.results_panel import SensorReading


class SensorSandbox(MainWindow):
    """The CFD editor plus per-sensor emulation driven by lab settings."""

    back_requested = Signal()

    def __init__(
        self,
        translator: Translator,
        project: Project | None = None,
        path=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(translator, project=project, path=path, parent=parent)
        self.setWindowTitle("Scentinel — Universal Sensor Sandbox")
        self._elapsed = 0.0
        self._sample = 0
        self._values: dict[str, float] = {}
        self._detected_at: dict[str, float] = {}
        self.home_requested.connect(self.back_requested.emit)
        self._build_sensor_lab()
        self._set_lab_widgets(self.project().sensor_lab)
        self.viewport().sensors_changed.connect(self._sync_sensors)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.advance)
        self._sync_sensors()
        self.set_lab_visible(False)

    def _build_sensor_lab(self) -> None:
        dock = QDockWidget("Virtual Sensor Lab", self)
        dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        tabs = QTabWidget()
        tabs.addTab(self._build_model_tab(), "Sensor models")
        tabs.addTab(self._build_telemetry_tab(), "Telemetry")
        tabs.addTab(self._build_evaluation_tab(), "Evaluation")
        dock.setWidget(tabs)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        dock.setMinimumHeight(280)
        toolbar = QToolBar("Sandbox tools", self)
        toolbar.setMovable(False)
        toolbar.addAction(dock.toggleViewAction())
        dock.toggleViewAction().setText("Sensor Lab")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        self._sandbox_toolbar = toolbar
        self._sensor_dock = dock
        self.resizeDocks([dock], [320], Qt.Orientation.Vertical)

    def set_lab_visible(self, visible: bool) -> None:
        self._lab_mode = visible
        self._sensor_dock.setVisible(visible)
        self._sandbox_toolbar.setVisible(visible)
        self.results_panel().set_sandbox_mode(visible)

    def lab_visible(self) -> bool:
        return getattr(self, "_lab_mode", False)

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
            self.family,
            self.range,
            self.lod,
            self.response,
            self.recovery,
            self.noise,
            self.drift,
            self.cross_factor,
            self.temperature,
            self.humidity,
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
        self._telemetry.setHorizontalHeaderLabels(
            [
                "Sensor",
                "Technology",
                "Source",
                "Ground truth",
                "Indicated",
                "Error",
                "State",
                "Detection time",
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

    def _store_lab(self, *_args: object) -> None:
        if self._loading:
            return
        self._project.sensor_lab = self.config()
        self._mark_dirty()

    def _set_lab_widgets(self, config: VirtualSensorConfig) -> None:
        widgets = (
            self.family,
            self.range,
            self.lod,
            self.response,
            self.recovery,
            self.noise,
            self.drift,
            self.cross_factor,
        )
        for widget in widgets:
            widget.blockSignals(True)
        try:
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
        finally:
            for widget in widgets:
                widget.blockSignals(False)

    def _apply_project(self, project: Project, path=None) -> None:
        super()._apply_project(project, path=path)
        if not hasattr(self, "humidity"):
            return
        self._set_lab_widgets(project.sensor_lab)
        self.humidity.setValue(project.scenario.moisture_fraction * 100.0)
        self._sync_sensors()

    def _exposure(self, sensor_id: str) -> tuple[float, float, str]:
        """Return (truth ppm, cross ppm, source label) for one sensor."""
        for reading in self.results_panel().readings():
            if reading.sensor_id != sensor_id:
                continue
            if "VOC" in reading.values:
                truth = reading.values["VOC"]
                source = "cfd-voc"
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
        sensors = self.viewport().sensors()
        live = {sensor.sensor_id for sensor in sensors}
        self._values = {key: value for key, value in self._values.items() if key in live}
        self._detected_at = {key: value for key, value in self._detected_at.items() if key in live}
        self._telemetry.setRowCount(len(sensors))
        for row, sensor in enumerate(sensors):
            truth, cross, source = self._exposure(sensor.sensor_id)
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
                if sensor.sensor_id in self._detected_at
                else "—",
            )
            for column, text in enumerate(cells):
                self._telemetry.setItem(row, column, QTableWidgetItem(text))
        self._publish_sensor_table()
        self._refresh_evaluation()

    def _publish_sensor_table(self) -> None:
        """Push the current replay into the results table, so the lab output is visible.

        The table is the same one a solve fills, so the numbers a reviewer reads
        are the numbers the device model produced. Until the first sample lands
        the ground truth is shown with the indicated value still pending, which
        is why the entries are only written once a value exists.
        """
        rows = []
        for sensor in self.viewport().sensors():
            indicated = self._values.get(sensor.sensor_id)
            if indicated is None:
                continue
            truth, cross, source = self._exposure(sensor.sensor_id)
            values = {"TVOC": indicated, "GROUND_TRUTH": truth}
            if cross:
                values["INTERFERENCE"] = cross
            rows.append(
                SensorReading(
                    sensor_id=sensor.sensor_id,
                    x=sensor.x,
                    y=sensor.y,
                    values=values,
                )
            )
        if rows:
            self.results_panel().set_results(rows)

    def toggle(self) -> None:
        if not self.viewport().sensors():
            self.results_panel().append_log("Place at least one sensor before replaying its response.")
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
        self.results_panel().set_results([])
        self._sync_sensors()

    def advance(self) -> None:
        step = self._timer.interval() / 1000.0
        self._elapsed += step
        config = self.config()
        truths: list[float] = []
        for row, sensor in enumerate(self.viewport().sensors()):
            truth, cross, source = self._exposure(sensor.sensor_id)
            truths.append(truth)
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
            state = "saturated" if reading.saturated else "below LOD" if reading.below_detection else "measuring"
            values = (
                sensor.sensor_id,
                config.family,
                source,
                f"{truth:.4f} ppm",
                f"{reading.indicated_ppm:.4f} ppm",
                f"{reading.indicated_ppm - truth:+.4f} ppm",
                state,
                f"{self._detected_at[sensor.sensor_id]:.2f} s"
                if sensor.sensor_id in self._detected_at
                else "—",
            )
            for column, text in enumerate(values):
                item = self._telemetry.item(row, column)
                if item is None:
                    self._telemetry.setItem(row, column, QTableWidgetItem(text))
                else:
                    item.setText(text)
        if self._values and truths:
            mean_error = sum(
                abs(self._values[sensor.sensor_id] - truth)
                for sensor, truth in zip(self.viewport().sensors(), truths)
            ) / len(truths)
            self.results_panel().set_virtual_sensor_summary(
                technology=config.family,
                indicated_ppm=sum(self._values.values()) / len(self._values),
                detection_limit_ppm=config.detection_limit_ppm,
                temperature_c=self.temperature.value(),
                humidity_rh=self.humidity.value(),
                mean_error_ppm=mean_error,
            )
        self._sample += 1
        self._publish_sensor_table()
        self._refresh_evaluation()

    def _refresh_evaluation(self) -> None:
        count = len(self.viewport().sensors())
        detected = len(self._detected_at)
        errors = []
        for sensor in self.viewport().sensors():
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
                "Run CFD or replay a controlled exposure to populate device-performance metrics.\n\n"
                "Coverage and blind-zone scores require a spatial concentration field; they are not inferred from probe-only data."
            )
