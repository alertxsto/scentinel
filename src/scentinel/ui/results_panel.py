"""Right-hand panel: the per-sensor probe table and the solver log view.

Both views are deliberately dumb — :meth:`ResultsPanel.set_results` and
:meth:`ResultsPanel.append_log` are the only entry points, so the panel can be
driven from a future solver worker without any panel-side threading.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from scentinel.core import assessment as assessment_mod
from scentinel.ui.field_view import FieldResultView
from scentinel.ui.i18n import Translator

if TYPE_CHECKING:
    from scentinel.core.history import RunRecord


def _scrollable(page: QWidget) -> QScrollArea:
    """Wrap a tab page so its content stays reachable at any panel height."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setWidget(page)
    return area


@dataclass(frozen=True)
class SensorReading:
    """One row of the results table: a sensor and its per-gas concentration."""

    sensor_id: str
    x: float
    y: float
    values: dict[str, float]


class ResultsPanel(QWidget):
    """Probe table plus a streaming log pane, with CSV export and cancel."""

    export_requested = Signal()
    cancel_requested = Signal()
    run_requested = Signal()
    clear_requested = Signal()

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._t = translator
        self._readings: list[SensorReading] = []
        self._record: RunRecord | None = None
        self._sandbox_mode = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self._title = QLabel()
        self._title.setObjectName("resultsTitle")
        self._status = QLabel()
        self._status.setObjectName("runStatus")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self._title)
        header.addStretch(1)
        header.addWidget(self._status)
        layout.addLayout(header)

        self._tabs = QTabWidget()
        self._summary_tab = self._build_summary_tab()

        self._stack = QStackedWidget()
        self._placeholder = QLabel()
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._table = QTableWidget(0, 0)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._stack.addWidget(self._placeholder)
        self._stack.addWidget(self._table)

        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        log_layout.setContentsMargins(8, 8, 8, 8)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(5000)
        self._log.setFont(QFont("monospace"))
        self._log.setMinimumHeight(0)
        log_layout.addWidget(self._log)

        # The Sensors and Log pages get scroll areas too, so no page can pin the
        # panel: the tab widget sizes itself from its tallest page, and a tall
        # page would otherwise starve the viewport above it.
        self._tabs.setMinimumHeight(0)
        self._tabs.addTab(self._summary_tab, "")
        self._tabs.addTab(_scrollable(self._stack), "")
        self._tabs.addTab(_scrollable(log_tab), "")
        self._field_view = FieldResultView()
        self._tabs.addTab(self._field_view, "")
        layout.addWidget(self._tabs, 1)

        buttons = QHBoxLayout()
        self._run_button = QPushButton()
        self._run_button.setObjectName("primaryAction")
        self._run_button.clicked.connect(self.run_requested.emit)
        self._export_button = QPushButton()
        self._export_button.clicked.connect(self.export_requested.emit)
        self._export_button.setEnabled(False)
        self._cancel_button = QPushButton()
        self._cancel_button.clicked.connect(self.cancel_requested.emit)
        self._cancel_button.setVisible(False)
        buttons.addWidget(self._run_button)
        buttons.addWidget(self._export_button)
        buttons.addStretch(1)
        buttons.addWidget(self._cancel_button)
        layout.addLayout(buttons)

        self._t.changed.connect(self.retranslate)
        self.retranslate()

    def set_sandbox_mode(self, enabled: bool) -> None:
        """Switch TVOC outputs from hardware requirements to virtual telemetry."""
        self._sandbox_mode = enabled

    def set_virtual_sensor_summary(
        self,
        *,
        technology: str,
        indicated_ppm: float,
        detection_limit_ppm: float,
        temperature_c: float,
        humidity_rh: float,
        mean_error_ppm: float,
    ) -> None:
        """Publish current software-only sandbox measurements in the output catalogue."""
        self._summary_fields["tvoc_concentration"].setText(f"{indicated_ppm:.4f} ppm (virtual)")
        self._summary_fields["voc_index"].setText(
            self._t.t("results.value.not_applicable_to_model", model=technology)
        )
        self._summary_fields["raw_signal"].setText(f"{indicated_ppm:.4f} ppm indicated")
        self._summary_fields["temperature"].setText(f"{temperature_c:.2f} °C (simulated)")
        self._summary_fields["humidity"].setText(f"{humidity_rh:.2f} %RH (simulated)")
        self._summary_fields["calibration"].setText(
            self._t.t("results.value.virtual_profile", model=technology)
        )
        self._summary_fields["detection_limit"].setText(f"{detection_limit_ppm:.4f} ppm")
        self._summary_fields["uncertainty"].setText(
            f"mean absolute indication error {mean_error_ppm:.4f} ppm"
        )


    def set_field_case(self, case_dir: Path, sensors: list) -> None:
        """Render concentration fields from a completed OpenFOAM case."""
        self._field_view.set_case(case_dir, sensors)
        self._tabs.setCurrentWidget(self._field_view)
    def _build_summary_tab(self) -> QWidget:
        content = QWidget()
        content.setObjectName("summaryContent")
        grid = QGridLayout(content)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._summary_hint = QLabel()
        self._summary_hint.setWordWrap(True)
        self._summary_hint.setObjectName("summaryHint")
        grid.addWidget(self._summary_hint, 0, 0, 1, 2)

        self._summary_fields: dict[str, QLabel] = {}
        sections = (
            ("gas_results", ("sensor_count", "gases", "concentration_statistics", "peak_sensor")),
            ("safety", ("threshold_assessment", "coverage", "blind_zone")),
            ("rdf", ("rdf_suitability", "rdf_standard", "offtaker_match", "ncv", "moisture", "ash", "chlorine", "sulfur")),
            ("tvoc", ("tvoc_concentration", "voc_index", "raw_signal", "temperature", "humidity", "calibration", "detection_limit", "uncertainty")),
            ("run", ("run_id", "started", "finished", "execution_status")),
            ("quality", ("classification", "convergence", "mesh_independence", "mass_balance", "validation")),
            ("physics", ("sources", "wind", "inlet", "viscosity", "diffusivity", "ventilation")),
            ("numerics", ("solver", "mesh_size", "iterations", "mesh_cells", "case_digest")),
        )
        for index, (section, keys) in enumerate(sections):
            frame = QFrame()
            frame.setObjectName("summarySection")
            form = QFormLayout(frame)
            form.setContentsMargins(12, 10, 12, 10)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            heading = QLabel()
            heading.setObjectName("summarySectionTitle")
            heading.setProperty("section", section)
            form.addRow(heading)
            for key in keys:
                name = QLabel()
                name.setObjectName("summaryFieldLabel")
                name.setProperty("field", key)
                value = QLabel("—")
                value.setObjectName("summaryValue")
                value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                value.setWordWrap(True)
                form.addRow(name, value)
                self._summary_fields[key] = value
            row, column = divmod(index, 2)
            grid.addWidget(frame, row + 1, column)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        QTimer.singleShot(0, lambda: scroll.verticalScrollBar().setValue(0))
        return scroll

    def set_run_record(self, record: RunRecord) -> None:
        """Display the persisted run contract, not inferred UI state."""
        self._record = record
        execution = record.execution
        physics = record.applied_physics
        quality = record.quality
        scenario = record.project.scenario
        diffusivity = ", ".join(
            f"{gas}: {value:.3g} m²/s"
            for gas, value in sorted(physics.scalar_diffusivity_m2_s.items())
        )
        digest = physics.case_input_digest or "—"
        digest_display = "\u200b".join(
            digest[index : index + 16] for index in range(0, len(digest), 16)
        )
        readings = record.results.sensor_readings
        gases = sorted({gas for reading in readings for gas in reading.values_ppmv})
        statistics: list[str] = []
        peaks: list[str] = []
        for gas in gases:
            samples = [
                (reading.sensor_id, reading.values_ppmv[gas])
                for reading in readings
                if gas in reading.values_ppmv
            ]
            if not samples:
                continue
            values_ppmv = [value for _, value in samples]
            peak_sensor, peak_value = max(samples, key=lambda item: item[1])
            statistics.append(
                f"{gas}: min {min(values_ppmv):.4g}, mean "
                f"{sum(values_ppmv) / len(values_ppmv):.4g}, max {peak_value:.4g} ppmv"
            )
            peaks.append(f"{gas}: {peak_sensor} ({peak_value:.4g} ppmv)")
        unavailable = self._t.t("results.value.not_available")
        needs_lab = self._t.t("results.value.needs_lab")
        needs_sensor = self._t.t(
            "results.value.virtual_pending" if self._sandbox_mode else "results.value.needs_sensor"
        )
        assessment = assessment_mod.evaluate(
            readings, moisture_fraction=scenario.moisture_fraction
        )
        verdict = assessment_mod.suitability_verdict(assessment)
        halogen = assessment.halogen
        halogen_detail = (
            f"Cl {halogen.chlorine_mg_per_nm3:.2f} mg/Nm³, "
            f"S {halogen.sulfur_mg_per_nm3:.2f} mg/Nm³ "
            "(gas phase, AP-42 Table 2.4-1 defaults)"
        )
        if halogen.chlorine_species:
            top_cl = halogen.chlorine_species[0]
            halogen_detail += f"\nLargest Cl carrier: {top_cl[0]} ({top_cl[1]:.2f} mg/Nm³)"
        if halogen.sulfur_species:
            top_s = halogen.sulfur_species[0]
            halogen_detail += f"\nLargest S carrier: {top_s[0]} ({top_s[1]:.2f} mg/Nm³)"
        if assessment.threshold_checks:
            worst = max(assessment.threshold_checks, key=lambda check: check.ratio)
            threshold_text = "\n".join(
                f"{check.gas}: {check.peak_ppmv:.4g} / {check.limit_ppmv:g} ppmv "
                f"= {check.ratio:.2f}× {check.limit_name} @ {check.peak_sensor}"
                for check in assessment.threshold_checks
            )
            threshold_text += (
                f"\nWorst: {worst.gas} at {worst.ratio:.2f}× its limit"
                + (" — EXCEEDS" if worst.exceeds else " — within limit")
            )
        else:
            threshold_text = unavailable
        if assessment.unchecked_gases:
            threshold_text += (
                "\nNo published limit applied to: " + ", ".join(assessment.unchecked_gases)
            )
        if assessment.peak_to_mean:
            coverage_text = "\n".join(
                f"{gas}: peak/mean {ratio:.2f}×"
                for gas, ratio in sorted(assessment.peak_to_mean.items())
            )
            coverage_text += (
                "\n1.00× is a uniform field; higher means the plume reaches only "
                "part of the placement."
            )
        else:
            coverage_text = unavailable
        blind_text = (
            "Needs a spatial field, not probe-only data: a sensor that reads zero "
            "cannot be distinguished from an unsampled region here."
        )
        moisture_text = (
            f"{scenario.moisture_fraction:.0%} (waste stream input; not a laboratory "
            "measurement of the material)"
        )
        not_assessed = self._t.t("results.value.not_assessed")
        sources = ", ".join(
            f"{gas}: {source.resolved_ppmv:g} ppmv ({source.mode})"
            for gas, source in sorted(scenario.gas_sources.items())
        )
        values = {
            "run_id": record.run_id,
            "started": record.started_at_utc,
            "finished": record.finished_at_utc or "—",
            "execution_status": record.execution_status,
            "sensor_count": str(len(readings)),
            "gases": ", ".join(gases) or "—",
            "concentration_statistics": "\n".join(statistics) or unavailable,
            "peak_sensor": "\n".join(peaks) or unavailable,
            "threshold_assessment": threshold_text,
            "coverage": coverage_text,
            "blind_zone": blind_text,
            "rdf_suitability": verdict,
            "rdf_standard": not_assessed,
            "offtaker_match": not_assessed,
            "ncv": needs_lab,
            "moisture": moisture_text,
            "ash": needs_lab,
            "chlorine": halogen_detail,
            "sulfur": (
                f"{halogen.sulfur_mg_per_nm3:.2f} mg/Nm³ gas phase; fuel-basis "
                "sulfur needs laboratory characterisation"
            ),
            "tvoc_concentration": needs_sensor,
            "voc_index": needs_sensor,
            "raw_signal": needs_sensor,
            "temperature": needs_sensor,
            "humidity": needs_sensor,
            "calibration": needs_sensor,
            "detection_limit": needs_sensor,
            "uncertainty": needs_sensor,
            "solver": f"{execution.solver} · {execution.container_image}",
            "mesh_size": f"{execution.mesh_size_m:g} m",
            "iterations": str(execution.requested_end_iteration),
            "mesh_cells": str(execution.mesh_cells) if execution.mesh_cells is not None else "—",
            "case_digest": digest_display,
            "sources": sources or "—",
            "wind": f"{physics.wind_speed_reported_m_s:g} m/s · {physics.wind_profile}",
            "inlet": f"{physics.inlet_speed_at_rim_m_s:.4g} m/s",
            "viscosity": f"{physics.nu_m2_s:.3g} m²/s",
            "diffusivity": diffusivity or "—",
            "ventilation": (
                f"requested={str(scenario.ventilation.requested_on).lower()}, "
                f"modelled={str(scenario.ventilation.modelled).lower()}"
            ),
            "classification": quality.classification,
            "convergence": quality.convergence,
            "mesh_independence": quality.mesh_independence,
            "mass_balance": quality.mass_balance,
            "validation": quality.experimental_validation,
        }
        for key, value in values.items():
            self._summary_fields[key].setText(value)
        self._update_status(record.execution_status)
        self._tabs.setCurrentWidget(self._summary_tab)

    def _update_status(self, status: str) -> None:
        self._status.setText(self._t.t(f"results.status.{status}"))
        self._status.setProperty("state", status)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    # -- state ---------------------------------------------------------------

    def readings(self) -> list[SensorReading]:
        return list(self._readings)

    def set_results(self, readings: list[SensorReading]) -> None:
        self._readings = list(readings)
        gases = sorted({gas for reading in readings for gas in reading.values})
        self._table.clear()
        self._table.setColumnCount(3 + len(gases))
        self._table.setHorizontalHeaderLabels(["#", "x [m]", "y [m]", *gases])
        self._table.setRowCount(len(readings))
        for row, reading in enumerate(readings):
            cells = [
                reading.sensor_id,
                f"{reading.x:.3f}",
                f"{reading.y:.3f}",
                *(f"{reading.values[gas]:.4g}" if gas in reading.values else "—" for gas in gases),
            ]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self._table.setItem(row, column, item)
        self._stack.setCurrentWidget(self._table if readings else self._placeholder)
        self._export_button.setEnabled(bool(readings))

    def set_running(self, running: bool) -> None:
        self._cancel_button.setVisible(running)
        self._cancel_button.setEnabled(running)
        if running:
            self._run_button.setEnabled(False)
            self._run_button.setToolTip("")
            self._stack.setCurrentWidget(self._placeholder)
            self._placeholder.setText(self._t.t("results.busy"))

    def set_run_enabled(self, enabled: bool, blocker_key: str | None = None) -> None:
        """Enable Run and explain, on the button itself, what is missing.

        The status bar is easy to miss, so the reason is repeated here and the
        placeholder says the same thing while no results exist.
        """
        if self._cancel_button.isVisible():
            return  # a run is in flight; its own state governs the button
        self._run_button.setEnabled(enabled)
        if blocker_key is not None:
            reason = self._t.t(blocker_key)
            self._run_button.setToolTip(reason)
            if not self._readings:
                self._placeholder.setText(reason)
                self._stack.setCurrentWidget(self._placeholder)
        else:
            self._run_button.setToolTip("")
            if not self._readings:
                self._placeholder.setText(self._t.t("results.empty"))
                self._stack.setCurrentWidget(self._placeholder)

    def clear(self) -> None:
        self._readings = []
        self._record = None
        self._table.clear()
        self._table.setRowCount(0)
        self._table.setColumnCount(0)
        self._stack.setCurrentWidget(self._placeholder)
        self._placeholder.setText(self._t.t("results.empty"))
        self._export_button.setEnabled(False)
        self._log.clear()
        for value in self._summary_fields.values():
            value.setText("—")
        self._update_status("pending")

    def append_log(self, text: str) -> None:
        self._log.appendPlainText(text.rstrip("\n"))

    def export_results_csv(self, path: Path) -> Path:
        """Write the current readings as CSV; returns the path written."""
        import csv

        gases = sorted({gas for reading in self._readings for gas in reading.values})
        path = Path(path)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["sensor_id", "x_m", "y_m", *gases])
            for reading in self._readings:
                writer.writerow(
                    [
                        reading.sensor_id,
                        f"{reading.x:.4f}",
                        f"{reading.y:.4f}",
                        *(f"{reading.values[gas]:.6g}" if gas in reading.values else "" for gas in gases),
                    ]
                )
        return path

    # -- i18n ----------------------------------------------------------------

    def retranslate(self) -> None:
        t = self._t.t
        self._title.setText(t("panel.results"))
        self._tabs.setTabText(0, t("results.tab.summary"))
        self._tabs.setTabText(1, t("results.tab.sensors"))
        self._tabs.setTabText(2, t("results.tab.log"))
        self._tabs.setTabText(3, t("results.tab.field"))
        self._summary_hint.setText(t("results.summary.hint"))
        for label in self.findChildren(QLabel):
            section = label.property("section")
            field = label.property("field")
            if section:
                label.setText(t(f"results.section.{section}"))
            elif field:
                label.setText(t(f"results.field.{field}"))
        self._export_button.setText(t("action.export_csv"))
        self._run_button.setText(t("action.run"))
        self._cancel_button.setText(t("action.cancel"))
        self._log.setPlaceholderText(t("log.empty"))
        self._placeholder.setText(
            t("results.busy") if self._cancel_button.isVisible() else t("results.empty")
        )
        self._update_status(self._record.execution_status if self._record else "pending")
