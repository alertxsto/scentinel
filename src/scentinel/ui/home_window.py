"""Persistent application shell for dashboard, simulation, and sensor sandbox."""

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
        self.resize(1520, 940)
        shell = QWidget(); shell.setObjectName("appShell")
        outer = QHBoxLayout(shell); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        outer.addWidget(self._build_navigation())
        main = QWidget(); main_layout = QVBoxLayout(main); main_layout.setContentsMargins(0,0,0,0); main_layout.setSpacing(0)
        main_layout.addWidget(self._build_context_bar())
        self._stack = QStackedWidget()
        self._home = self._build_home()
        self._studio = MainWindow(translator, project=project); self._prepare_embedded(self._studio)
        self._sandbox = SensorSandbox(translator, project=project); self._prepare_embedded(self._sandbox)
        self._studio.home_requested.connect(self.show_home)
        self._sandbox.back_requested.connect(self.show_home)
        self._stack.addWidget(self._home); self._stack.addWidget(self._studio); self._stack.addWidget(self._sandbox)
        main_layout.addWidget(self._stack, 1); outer.addWidget(main, 1)
        self.setCentralWidget(shell)
        QTimer.singleShot(0, self.show_home)

    def _prepare_embedded(self, window: QMainWindow) -> None:
        window.setWindowFlags(Qt.WindowType.Widget)
        window.menuBar().hide()
        window.statusBar().hide()

    def _build_navigation(self) -> QWidget:
        rail = QFrame(); rail.setFixedWidth(218)
        rail.setStyleSheet("QFrame{background:#123c2b} QLabel{color:white} QPushButton{color:#dbeae2;background:transparent;border:0;text-align:left;padding:0 16px;min-height:42px;font-weight:600} QPushButton:hover{background:#1b523b;color:white} QPushButton:checked{background:#e9f4ee;color:#12583a;border-left:4px solid #45a477}")
        layout = QVBoxLayout(rail); layout.setContentsMargins(0,20,0,16); layout.setSpacing(4)
        brand = QLabel("  SCENTINEL"); brand.setStyleSheet("font-size:19px;font-weight:900;letter-spacing:1px;padding:8px 8px 20px")
        layout.addWidget(brand)
        self._nav_home = self._nav_button("⌂  Dashboard", self.show_home)
        self._nav_studio = self._nav_button("◫  Simulation Studio", self.show_studio)
        self._nav_sandbox = self._nav_button("⌁  Sensor Sandbox", self.show_sandbox)
        for button in (self._nav_home,self._nav_studio,self._nav_sandbox): layout.addWidget(button)
        layout.addStretch(1)
        fidelity = QLabel("  FIDELITY\n  2D SCREENING")
        fidelity.setStyleSheet("color:#a9c8b7;font-size:11px;font-weight:700;padding:12px")
        layout.addWidget(fidelity)
        return rail

    @staticmethod
    def _nav_button(text: str, callback) -> QPushButton:
        button=QPushButton(text); button.setCheckable(True); button.clicked.connect(callback); return button

    def _build_context_bar(self) -> QWidget:
        bar=QFrame(); bar.setFixedHeight(64); bar.setStyleSheet("QFrame{background:white;border-bottom:1px solid #dce5e0}")
        layout=QHBoxLayout(bar); layout.setContentsMargins(22,0,22,0)
        self._page_title=QLabel(); self._page_title.setStyleSheet("font-size:18px;font-weight:800;color:#173c2b")
        self._page_context=QLabel(); self._page_context.setStyleSheet("color:#65786e")
        layout.addWidget(self._page_title); layout.addSpacing(14); layout.addWidget(self._page_context); layout.addStretch(1)
        badge=QLabel("OpenFOAM 2512"); badge.setStyleSheet("background:#e7f4ed;color:#176342;padding:6px 10px;border-radius:10px;font-weight:700")
        layout.addWidget(badge); return bar

    def _build_home(self) -> QWidget:
        page=QWidget(); page.setObjectName("homePage"); root=QVBoxLayout(page); root.setContentsMargins(38,32,38,32); root.setSpacing(20)
        title=QLabel("Design, simulate, validate."); title.setStyleSheet("font-size:30px;font-weight:900;color:#153f30")
        subtitle=QLabel("Satu workflow untuk CFD screening, spatial sensor placement, virtual-device evaluation, dan kesiapan validasi lapangan.")
        subtitle.setWordWrap(True); subtitle.setStyleSheet("font-size:14px;color:#60746a")
        root.addWidget(title); root.addWidget(subtitle)
        cards=QHBoxLayout(); cards.setSpacing(18)
        cards.addWidget(self._card("Simulation Studio","Bangun geometri, sumber gas, mesh, placement, dan run OpenFOAM. Semua hasil diberi quality gates.","Open 2D Screening",self.show_studio,"PHYSICS"))
        cards.addWidget(self._card("Universal Sensor Sandbox","Studio yang sama ditambah device models, telemetry, response error, detection time, dan evaluation.","Open Sensor Sandbox",self.show_sandbox,"DIGITAL TWIN"))
        root.addLayout(cards,1)
        warning=QLabel("3D engineering, live hardware, coverage, dan blind-zone analysis hanya akan ditandai tersedia setelah engine dan bukti validasinya benar-benar ada.")
        warning.setWordWrap(True); warning.setStyleSheet("background:#fff8e8;color:#88520c;border:1px solid #f2d9a5;border-radius:9px;padding:12px")
        root.addWidget(warning); return page

    def _card(self,title:str,text:str,action:str,callback,badge:str)->QFrame:
        card=QFrame(); card.setObjectName("modeCard"); card.setStyleSheet("QFrame#modeCard{background:white;border:1px solid #d7e2dc;border-radius:12px}")
        layout=QVBoxLayout(card); layout.setContentsMargins(24,22,24,22); layout.setSpacing(12)
        tag=QLabel(badge); tag.setStyleSheet("color:#1a7550;font-size:11px;font-weight:800")
        heading=QLabel(title); heading.setStyleSheet("font-size:21px;font-weight:800;color:#174c36")
        body=QLabel(text); body.setWordWrap(True); body.setStyleSheet("color:#5b6f64")
        button=QPushButton(action); button.setObjectName("modeButton"); button.clicked.connect(callback)
        layout.addWidget(tag); layout.addWidget(heading); layout.addWidget(body); layout.addStretch(1); layout.addWidget(button); return card

    def _select(self, page: QWidget, title: str, context: str, active: QPushButton) -> None:
        self._stack.setCurrentWidget(page); self._page_title.setText(title); self._page_context.setText(context)
        for button in (self._nav_home,self._nav_studio,self._nav_sandbox): button.setChecked(button is active)

    def show_home(self) -> None: self._select(self._home,"Dashboard","Digital twin workspace",self._nav_home)
    def show_studio(self) -> None: self._select(self._studio,"Simulation Studio","2D screening · CFD ground truth",self._nav_studio)
    def show_sandbox(self) -> None: self._select(self._sandbox,"Sensor Sandbox","CFD studio + virtual measurement chain",self._nav_sandbox)
