"""Spatial virtual-sensor studio built around the same placement workflow as CFD."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from scentinel.core.geometry import BinGeometry
from scentinel.core.virtual_sensor import SENSOR_FAMILIES, VirtualSensorConfig, step_response
from scentinel.ui.viewport import ViewportWidget


class SensorSandbox(QWidget):
    """Place multiple virtual sensors spatially and replay a controlled gas exposure."""

    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._elapsed = 0.0
        self._sample = 0
        self._values: dict[str, float] = {}
        self.setStyleSheet(
            "SensorSandbox{background:#f4f7f5;color:#1f2937}"
            "SensorSandbox QGroupBox{background:white;border:1px solid #d9e1dd;border-radius:8px;margin-top:14px;padding-top:10px;font-weight:700}"
            "SensorSandbox QLabel{color:#334155}"
            "SensorSandbox QPlainTextEdit{background:#111827;color:#d1fae5;border-radius:6px}"
            "SensorSandbox QPushButton{padding:7px 12px}"
        )
        root = QVBoxLayout(self)
        header = QHBoxLayout()
        back = QPushButton("← Home"); back.clicked.connect(self.back_requested.emit)
        title = QLabel("Universal Sensor Sandbox — Spatial Studio")
        title.setStyleSheet("font-size:22px;font-weight:800;color:#153f30")
        badge = QLabel("CONTROLLED EXPOSURE · bukan CFD")
        badge.setStyleSheet("background:#fef3c7;color:#92400e;border-radius:8px;padding:5px 10px;font-weight:700")
        header.addWidget(back); header.addWidget(title); header.addStretch(1); header.addWidget(badge)
        root.addLayout(header)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self._build_controls())
        self.viewport = ViewportWidget(); self.viewport.set_geometry(BinGeometry())
        self.viewport.sensors_changed.connect(self._sync_sensors)
        split.addWidget(self.viewport)
        split.addWidget(self._build_outputs())
        split.setStretchFactor(0, 0); split.setStretchFactor(1, 1); split.setStretchFactor(2, 1)
        split.setSizes([330, 650, 460])
        root.addWidget(split, 1)
        self.timer = QTimer(self); self.timer.setInterval(250); self.timer.timeout.connect(self.advance)

    def _build_controls(self) -> QWidget:
        body = QWidget(); layout = QVBoxLayout(body)
        intro = QLabel("Klik pada ruang udara di viewport untuk menempatkan sensor. Semua sensor menerima exposure chamber yang sama; posisi disimpan untuk workflow placement, tetapi belum mengubah konsentrasi tanpa field CFD.")
        intro.setWordWrap(True); intro.setStyleSheet("background:#eff6ff;color:#1e3a8a;padding:10px;border-radius:6px")
        layout.addWidget(intro)
        exposure = QGroupBox("Exposure chamber")
        eform = QFormLayout(exposure)
        self.truth = self._spin(0, 1_000_000, 25, " ppm")
        self.cross = self._spin(0, 1_000_000, 0, " ppm")
        self.temperature = self._spin(-20, 80, 25, " °C")
        self.humidity = self._spin(0, 100, 50, " %RH")
        eform.addRow("Ground truth TVOC", self.truth); eform.addRow("Gas pengganggu", self.cross)
        eform.addRow("Temperatur", self.temperature); eform.addRow("Kelembapan", self.humidity)
        layout.addWidget(exposure)
        device = QGroupBox("Virtual device model"); form = QFormLayout(device)
        self.family = QComboBox(); self.family.addItems(SENSOR_FAMILIES)
        self.range = self._spin(0.1, 1_000_000, 1000, " ppm")
        self.lod = self._spin(0, 1000, 0.01, " ppm", 3)
        self.response = self._spin(0.1, 600, 2, " s")
        self.recovery = self._spin(0.1, 1200, 5, " s")
        self.noise = self._spin(0, 1000, 0.01, " ppm", 3)
        self.drift = self._spin(-100, 100, 0, " ppm/h", 3)
        self.cross_factor = self._spin(-10, 10, 0, " ×", 3)
        for label, widget in (("Teknologi",self.family),("Range",self.range),("LOD",self.lod),("Response time",self.response),("Recovery time",self.recovery),("Noise",self.noise),("Drift",self.drift),("Cross-sensitivity",self.cross_factor)):
            form.addRow(label, widget)
        layout.addWidget(device); layout.addStretch(1)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(body); return scroll

    def _build_outputs(self) -> QWidget:
        panel = QWidget(); layout = QVBoxLayout(panel)
        title = QLabel("Virtual sensor telemetry"); title.setStyleSheet("font-size:17px;font-weight:700;color:#153f30")
        layout.addWidget(title)
        self.table = QTableWidget(0, 5); self.table.setHorizontalHeaderLabels(["Sensor","x [m]","y [m]","TVOC [ppm]","State"])
        layout.addWidget(self.table, 1)
        controls = QHBoxLayout(); self.run_button = QPushButton("Jalankan exposure"); self.run_button.clicked.connect(self.toggle)
        reset = QPushButton("Reset"); reset.clicked.connect(self.reset)
        clear = QPushButton("Hapus sensor"); clear.clicked.connect(self.viewport.clear_sensors)
        controls.addWidget(self.run_button); controls.addWidget(reset); controls.addWidget(clear); controls.addStretch(1)
        layout.addLayout(controls)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(170); layout.addWidget(self.log)
        return panel

    @staticmethod
    def _spin(low: float, high: float, value: float, suffix: str, decimals: int = 2) -> QDoubleSpinBox:
        spin=QDoubleSpinBox(); spin.setRange(low,high); spin.setDecimals(decimals); spin.setValue(value); spin.setSuffix(suffix); spin.setKeyboardTracking(False); return spin

    def config(self) -> VirtualSensorConfig:
        return VirtualSensorConfig(family=self.family.currentText(),range_ppm=self.range.value(),detection_limit_ppm=self.lod.value(),response_time_s=self.response.value(),recovery_time_s=self.recovery.value(),cross_sensitivity=self.cross_factor.value(),noise_ppm=self.noise.value(),drift_ppm_h=self.drift.value())

    def _sync_sensors(self) -> None:
        sensors=self.viewport.sensors(); self.table.setRowCount(len(sensors))
        live={sensor.sensor_id for sensor in sensors}; self._values={key:value for key,value in self._values.items() if key in live}
        for row,sensor in enumerate(sensors):
            values=(sensor.sensor_id,f"{sensor.x:.3f}",f"{sensor.y:.3f}",f"{self._values.get(sensor.sensor_id,0):.4f}","ready")
            for col,text in enumerate(values): self.table.setItem(row,col,QTableWidgetItem(text))

    def toggle(self) -> None:
        if not self.viewport.sensors(): self.log.appendPlainText("Place at least one sensor in the viewport."); return
        if self.timer.isActive(): self.timer.stop(); self.run_button.setText("Lanjutkan exposure")
        else: self.timer.start(); self.run_button.setText("Jeda exposure")

    def reset(self) -> None:
        self.timer.stop(); self._elapsed=0; self._sample=0; self._values={}; self.log.clear(); self.run_button.setText("Jalankan exposure"); self._sync_sensors()

    def advance(self) -> None:
        step=self.timer.interval()/1000; self._elapsed+=step; config=self.config()
        for row,sensor in enumerate(self.viewport.sensors()):
            reading=step_response(config,ground_truth_ppm=self.truth.value(),previous_ppm=self._values.get(sensor.sensor_id,0),elapsed_s=self._elapsed,step_s=step,temperature_c=self.temperature.value(),humidity_rh=self.humidity.value(),cross_gas_ppm=self.cross.value(),sample_index=self._sample+row)
            self._values[sensor.sensor_id]=reading.indicated_ppm
            self.table.item(row,3).setText(f"{reading.indicated_ppm:.4f}")
            state="SATURATED" if reading.saturated else "<LOD" if reading.below_detection else "measuring"
            self.table.item(row,4).setText(state)
        self._sample+=1
        self.log.appendPlainText(f"t={self._elapsed:.2f}s · truth={self.truth.value():.4f} ppm · {len(self._values)} virtual sensor(s)")
