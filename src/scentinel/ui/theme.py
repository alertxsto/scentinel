"""Application-wide Scentinel visual system."""

APP_STYLE = """
* { font-family: Inter, 'Noto Sans', sans-serif; font-size: 13px; }
QWidget { color: #18251f; }
QMainWindow, QWidget#appShell, QWidget#homePage { background: #f4f7f5; }
QMenuBar { background: #ffffff; color: #31443b; border-bottom: 1px solid #dce5e0; padding: 3px; }
QMenuBar::item:selected, QMenu::item:selected { background: #e7f3ed; color: #105f3d; }
QMenu { background: #ffffff; color: #24382e; border: 1px solid #d6e1db; }
QLabel { color: #263a30; background: transparent; }
QGroupBox { background: #ffffff; border: 1px solid #d8e2dd; border-radius: 10px; margin-top: 17px; padding: 14px 10px 10px; font-weight: 700; color: #174c36; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { min-height: 30px; background: #ffffff; color: #17231d; border: 1px solid #c8d5ce; border-radius: 6px; padding: 0 8px; selection-background-color: #1a7650; }
QComboBox::drop-down { border: 0; width: 24px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 2px solid #26845d; }
QCheckBox { color: #263a30; spacing: 7px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #9eb1a7; border-radius: 4px; background: white; }
QCheckBox::indicator:checked { background: #18734b; border-color: #18734b; }
QPushButton { min-height: 31px; background: #ffffff; color: #24513d; border: 1px solid #b9cbc1; border-radius: 7px; padding: 0 13px; font-weight: 600; }
QPushButton:hover { background: #edf7f1; border-color: #348565; }
QPushButton:pressed { background: #dcefe5; }
QPushButton:disabled { color: #9aa9a1; background: #eef2f0; border-color: #dfe6e2; }
QPushButton#primaryAction, QPushButton#modeButton { background: #16734b; color: white; border: 0; font-weight: 700; }
QPushButton#primaryAction:hover, QPushButton#modeButton:hover { background: #105f3d; }
QScrollArea, QAbstractScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #b7c6be; border-radius: 5px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QTableWidget { background: #ffffff; alternate-background-color: #f4f8f6; color: #1f3028; border: 1px solid #d8e2dd; border-radius: 8px; gridline-color: #e7edea; selection-background-color: #d9eee3; selection-color: #173c2b; }
QHeaderView::section { background: #edf3f0; color: #395247; border: 0; border-bottom: 1px solid #d2ddd7; padding: 7px; font-weight: 700; }
QPlainTextEdit { background: #17221d; color: #d7f8e7; border: 1px solid #24382e; border-radius: 8px; padding: 7px; font-family: 'JetBrains Mono', monospace; }
QTabWidget::pane { background: #ffffff; border: 1px solid #d8e2dd; border-radius: 8px; top: -1px; }
QTabBar::tab { background: #e9efec; color: #4d6258; padding: 8px 15px; margin-right: 3px; border-top-left-radius: 7px; border-top-right-radius: 7px; }
QTabBar::tab:selected { background: #ffffff; color: #12623f; font-weight: 700; }
QSplitter::handle { background: #dce5e0; }
QStatusBar { background: #ffffff; border-top: 1px solid #dce5e0; }
QDockWidget { color: #173c2b; font-weight: 700; }
QDockWidget::title { background: #eaf2ee; padding: 8px; }
"""
