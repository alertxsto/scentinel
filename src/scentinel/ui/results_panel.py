"""Right-hand panel: the per-sensor probe table and the solver log view.

Both views are deliberately dumb — :meth:`ResultsPanel.set_results` and
:meth:`ResultsPanel.append_log` are the only entry points, so the panel can be
driven from a future solver worker without any panel-side threading.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from scentinel.ui.i18n import Translator


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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._title = QLabel()
        self._title.setObjectName("resultsTitle")
        layout.addWidget(self._title)

        splitter = QSplitter(Qt.Orientation.Vertical, self)

        self._stack = QStackedWidget()
        self._placeholder = QLabel()
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._placeholder.setStyleSheet("color: #6b7280;")

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
        splitter.addWidget(self._stack)

        log_container = QWidget()
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(4)
        self._log_title = QLabel()
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(5000)
        self._log.setFont(QFont("monospace"))
        log_layout.addWidget(self._log_title)
        log_layout.addWidget(self._log)
        splitter.addWidget(log_container)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        self._run_button = QPushButton()
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
        self._run_button.setEnabled(not running)
        self._cancel_button.setVisible(running)
        self._cancel_button.setEnabled(running)
        if running:
            self._stack.setCurrentWidget(self._placeholder)
            self._placeholder.setText(self._t.t("results.busy"))

    def clear(self) -> None:
        self._readings = []
        self._table.clear()
        self._table.setRowCount(0)
        self._table.setColumnCount(0)
        self._stack.setCurrentWidget(self._placeholder)
        self._placeholder.setText(self._t.t("results.empty"))
        self._export_button.setEnabled(False)
        self._log.clear()

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
        self._log_title.setText(t("panel.log"))
        self._export_button.setText(t("action.export_csv"))
        self._run_button.setText(t("action.run"))
        self._cancel_button.setText(t("action.cancel"))
        self._log.setPlaceholderText(t("log.empty"))
        self._placeholder.setText(
            t("results.busy") if self._cancel_button.isVisible() else t("results.empty")
        )
