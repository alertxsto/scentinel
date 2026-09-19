"""Home dashboard and working navigation between Scentinel modes."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from scentinel.core.project import Project
from scentinel.ui.i18n import Translator
from scentinel.ui.main_window import MainWindow
from scentinel.ui.sensor_sandbox import SensorSandbox


class HomeWindow(QMainWindow):
    def __init__(self, translator: Translator, project: Project | None = None) -> None:
        super().__init__()
        self._translator = translator
        self.setWindowTitle("Scentinel — Digital Twin Studio")
        self.resize(1440, 900)
        self._stack = QStackedWidget()
        self._home = self._build_home()
        self._studio = MainWindow(translator, project=project)
        self._studio.setWindowFlags(Qt.WindowType.Widget)
        self._sandbox = SensorSandbox(translator, project=project)
        self._sandbox.setWindowFlags(Qt.WindowType.Widget)
        self._sandbox.back_requested.connect(self.show_home)
        self._stack.addWidget(self._home)
        self._studio.home_requested.connect(self.show_home)
        self._stack.addWidget(self._studio)
        self._stack.addWidget(self._sandbox)
        self._stack.setCurrentWidget(self._home)
        self.setCentralWidget(self._stack)
        self.setStyleSheet("QMainWindow{background:#f3f6f4} QFrame#modeCard{background:white;border:1px solid #d7e0db;border-radius:12px} QPushButton#modeButton{background:#176b46;color:white;border:0;border-radius:7px;padding:10px 18px;font-weight:700}")
        QTimer.singleShot(0, self.show_home)

    def _build_home(self) -> QWidget:
        page = QWidget(); root = QVBoxLayout(page); root.setContentsMargins(54, 42, 54, 42); root.setSpacing(22)
        title = QLabel("Scentinel Digital Twin Studio"); title.setStyleSheet("font-size:32px;font-weight:800;color:#153f30")
        subtitle = QLabel("Rancang eksperimen CFD, uji respons sensor virtual, lalu hubungkan hasilnya dengan perangkat fisik dan validasi lapangan.")
        subtitle.setWordWrap(True); subtitle.setStyleSheet("font-size:15px;color:#52635b")
        root.addWidget(title); root.addWidget(subtitle)
        cards = QHBoxLayout(); cards.setSpacing(18)
        cards.addWidget(self._card("Simulation Studio", "2D screening tersedia sekarang. Workflow 3D engineering akan menjadi fidelity terpisah—bukan klaim tersembunyi.", "Buka 2D Screening", self.show_studio))
        cards.addWidget(self._card("Universal Sensor Sandbox", "Emulasikan PID, MOX, electrochemical, NDIR, dan pellistor dengan lag, noise, drift, LOD, saturasi, dan cross-sensitivity.", "Buka Sandbox", self.show_sandbox))
        root.addLayout(cards, 1)
        note = QLabel("LIVE HARDWARE  ·  Adapter perangkat akan dipilih setelah protokol dan hardware nyata ditetapkan. Sandbox tidak memalsukan koneksi sensor fisik.")
        note.setWordWrap(True); note.setStyleSheet("background:#fff7ed;color:#9a4d0b;border:1px solid #fed7aa;border-radius:8px;padding:12px")
        root.addWidget(note)
        return page

    def _card(self, title: str, text: str, action: str, callback) -> QFrame:
        card = QFrame(); card.setObjectName("modeCard"); layout = QVBoxLayout(card); layout.setContentsMargins(24,24,24,24); layout.setSpacing(14)
        heading = QLabel(title); heading.setStyleSheet("font-size:21px;font-weight:700;color:#174c36")
        body = QLabel(text); body.setWordWrap(True); body.setStyleSheet("color:#52635b")
        button = QPushButton(action); button.setObjectName("modeButton"); button.clicked.connect(callback)
        layout.addWidget(heading); layout.addWidget(body); layout.addStretch(1); layout.addWidget(button)
        return card

    def show_home(self) -> None:
        self._stack.setCurrentWidget(self._home)

    def show_studio(self) -> None:
        self._stack.setCurrentWidget(self._studio)

    def show_sandbox(self) -> None:
        self._stack.setCurrentWidget(self._sandbox)
