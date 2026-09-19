"""Full Simulation Studio with an additional virtual-sensor laboratory."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDockWidget, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QToolBar,
    QVBoxLayout, QWidget,
)

from scentinel.core.project import Project
from scentinel.core.virtual_sensor import SENSOR_FAMILIES, VirtualSensorConfig, step_response
from scentinel.ui.i18n import Translator
from scentinel.ui.main_window import MainWindow


class SensorSandbox(MainWindow):
    """The complete CFD studio plus per-sensor emulation and evaluation."""

    back_requested = Signal()

    def __init__(
        self,
        translator: Translator,
        project: Project | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(translator, project=project, parent=parent)
        self.setWindowTitle("Scentinel — Universal Sensor Sandbox")
        self._elapsed = 0.0
        self._sample = 0
        self._values: dict[str, float] = {}
        self._detected_at: dict[str, float] = {}
        self.home_requested.connect(self.back_requested.emit)
        self.results_panel().set_sandbox_mode(True)
        self._build_sensor_lab()
        self.viewport().sensors_changed.connect(self._sync_sensors)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.advance)
        self._sync_sensors()

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
        dock.hide()
        self.resizeDocks([dock], [320], Qt.Orientation.Vertical)
        self._sensor_dock = dock

    def _build_model_tab(self) -> QWidget:
        tab = QWidget(); layout = QVBoxLayout(tab)
        note = QLabel(
            "Sandbox memakai seluruh geometri, sumber gas, numerics, placement, dan hasil CFD "
            "Simulation Studio. Parameter di bawah menambahkan measurement-chain tiap sensor."
        )
        note.setWordWrap(True)
        note.setStyleSheet("background:#eff6ff;color:#1e3a8a;padding:9px;border-radius:6px")
        layout.addWidget(note)
        exposure = QGroupBox("Replay input")
        eform = QFormLayout(exposure)
        self.truth = self._spin(0, 1_000_000, 25, " ppm")
        self.cross = self._spin(0, 1_000_000, 0, " ppm")
        self.temperature = self._spin(-20, 80, 25, " °C")
        self.humidity = self._spin(0, 100, 50, " %RH")
        eform.addRow("Ground truth fallback", self.truth)
        eform.addRow("Interfering gas", self.cross)
        eform.addRow("Temperature", self.temperature)
        eform.addRow("Humidity", self.humidity)
        layout.addWidget(exposure)
        model = QGroupBox("Selected sensor model")
        form = QFormLayout(model)
        self.family = QComboBox(); self.family.addItems(SENSOR_FAMILIES)
        self.range = self._spin(0.1, 1_000_000, 1000, " ppm")
        self.lod = self._spin(0, 1000, 0.01, " ppm", 3)
        self.response = self._spin(0.1, 600, 2, " s")
        self.recovery = self._spin(0.1, 1200, 5, " s")
        self.noise = self._spin(0, 1000, 0.01, " ppm", 3)
        self.drift = self._spin(-100, 100, 0, " ppm/h", 3)
        self.cross_factor = self._spin(-10, 10, 0, " ×", 3)
        for label, widget in (
            ("Technology", self.family), ("Range", self.range), ("LOD", self.lod),
            ("Response time", self.response), ("Recovery time", self.recovery),
            ("Noise", self.noise), ("Drift", self.drift),
            ("Cross-sensitivity", self.cross_factor),
        ):
            form.addRow(label, widget)
        layout.addWidget(model)
        controls = QHBoxLayout()
        self._replay_button = QPushButton("Start sensor replay")
        self._replay_button.clicked.connect(self.toggle)
        reset = QPushButton("Reset sensor state"); reset.clicked.connect(self.reset_sensor_state)
        controls.addWidget(self._replay_button); controls.addWidget(reset)
        layout.addLayout(controls); layout.addStretch(1)
        return tab

    def _build_telemetry_tab(self) -> QWidget:
        tab = QWidget(); layout = QVBoxLayout(tab)
        self._telemetry = QTableWidget(0, 7)
        self._telemetry.setHorizontalHeaderLabels(
            ["Sensor", "Technology", "Ground truth", "Indicated", "Error", "State", "Detection time"]
        )
        layout.addWidget(self._telemetry)
        return tab

    def _build_evaluation_tab(self) -> QWidget:
        tab = QWidget(); layout = QVBoxLayout(tab)
        title = QLabel("Placement and device evaluation")
        title.setStyleSheet("font-size:16px;font-weight:700;color:#174c36")
        self._evaluation = QLabel()
        self._evaluation.setWordWrap(True)
        layout.addWidget(title); layout.addWidget(self._evaluation); layout.addStretch(1)
        self._refresh_evaluation()
        return tab

    @staticmethod
    def _spin(low: float, high: float, value: float, suffix: str, decimals: int = 2) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(); spin.setRange(low, high); spin.setDecimals(decimals)
        spin.setValue(value); spin.setSuffix(suffix); spin.setKeyboardTracking(False)
        return spin

    def config(self) -> VirtualSensorConfig:
        return VirtualSensorConfig(
            family=self.family.currentText(), range_ppm=self.range.value(),
            detection_limit_ppm=self.lod.value(), response_time_s=self.response.value(),
            recovery_time_s=self.recovery.value(), cross_sensitivity=self.cross_factor.value(),
            noise_ppm=self.noise.value(), drift_ppm_h=self.drift.value(),
        )

    def _sync_sensors(self) -> None:
        sensors = self.viewport().sensors()
        live = {sensor.sensor_id for sensor in sensors}
        self._values = {key: value for key, value in self._values.items() if key in live}
        self._detected_at = {key: value for key, value in self._detected_at.items() if key in live}
        self._telemetry.setRowCount(len(sensors))
        for row, sensor in enumerate(sensors):
            cells = (sensor.sensor_id, self.family.currentText(), "—", "—", "—", "ready", "—")
            for column, text in enumerate(cells):
                self._telemetry.setItem(row, column, QTableWidgetItem(text))
        self._refresh_evaluation()

    def toggle(self) -> None:
        if not self.viewport().sensors():
            self.results_panel().append_log("Place at least one sensor before replaying its response.")
            return
        if self._timer.isActive():
            self._timer.stop(); self._replay_button.setText("Continue sensor replay")
        else:
            self._timer.start(); self._replay_button.setText("Pause sensor replay")

    def reset_sensor_state(self) -> None:
        self._timer.stop(); self._elapsed = 0; self._sample = 0
        self._values.clear(); self._detected_at.clear(); self._replay_button.setText("Start sensor replay")
        self._sync_sensors()

    def advance(self) -> None:
        step = self._timer.interval() / 1000.0
        self._elapsed += step
        config = self.config()
        truth = self.truth.value()
        for row, sensor in enumerate(self.viewport().sensors()):
            reading = step_response(
                config, ground_truth_ppm=truth,
                previous_ppm=self._values.get(sensor.sensor_id, 0.0),
                elapsed_s=self._elapsed, step_s=step,
                temperature_c=self.temperature.value(), humidity_rh=self.humidity.value(),
                cross_gas_ppm=self.cross.value(), sample_index=self._sample + row,
            )
            self._values[sensor.sensor_id] = reading.indicated_ppm
            if reading.indicated_ppm >= config.detection_limit_ppm and sensor.sensor_id not in self._detected_at:
                self._detected_at[sensor.sensor_id] = self._elapsed
            state = "saturated" if reading.saturated else "below LOD" if reading.below_detection else "measuring"
            values = (
                sensor.sensor_id, config.family, f"{truth:.4f} ppm",
                f"{reading.indicated_ppm:.4f} ppm",
                f"{reading.indicated_ppm - truth:+.4f} ppm", state,
                f"{self._detected_at[sensor.sensor_id]:.2f} s" if sensor.sensor_id in self._detected_at else "—",
            )
            for column, text in enumerate(values): self._telemetry.item(row, column).setText(text)
        if self._values:
            mean_error = sum(abs(value - truth) for value in self._values.values()) / len(
                self._values
            )
            self.results_panel().set_virtual_sensor_summary(
                technology=config.family,
                indicated_ppm=sum(self._values.values()) / len(self._values),
                detection_limit_ppm=config.detection_limit_ppm,
                temperature_c=self.temperature.value(),
                humidity_rh=self.humidity.value(),
                mean_error_ppm=mean_error,
            )
        self._sample += 1
        self._refresh_evaluation()

    def _refresh_evaluation(self) -> None:
        count = len(self.viewport().sensors())
        detected = len(self._detected_at)
        errors = [abs(value - self.truth.value()) for value in self._values.values()]
        mean_error = sum(errors) / len(errors) if errors else None
        self._evaluation.setText(
            f"Placed sensors: {count}\nDetected exposure: {detected}/{count}\n"
            f"Mean absolute indication error: {mean_error:.4f} ppm\n" if mean_error is not None
            else f"Placed sensors: {count}\nDetected exposure: {detected}/{count}\n"
            "Run CFD or replay a controlled exposure to populate device-performance metrics.\n\n"
            "Coverage and blind-zone scores require a spatial concentration field; they are not inferred from probe-only data."
        )
