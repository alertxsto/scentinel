"""Small palette-aware polish layered over the native Qt desktop style."""

APP_STYLE = """
QWidget { font-size: 13px; }
QToolBar#mainToolbar {
    spacing: 6px;
    padding: 4px 8px;
    border-bottom: 1px solid palette(mid);
    background: palette(base);
}
QToolBar#mainToolbar QToolButton {
    min-height: 28px;
    padding: 4px 10px;
}
QLabel#toolbarProject { padding: 0 10px; }
QLabel#dashboardTitle { font-size: 27px; font-weight: 700; }
QFrame#modeCard, QFrame#summarySection, QFrame#noticeBox {
    background: palette(base); border: 1px solid palette(mid); border-radius: 5px;
}
QLabel#cardTag, QLabel#summarySectionTitle { font-weight: 700; }
QLabel#cardHeading { font-size: 19px; font-weight: 700; }
QLabel#noticeText { padding: 10px; }
QPushButton#modeButton, QPushButton#primaryAction { min-height: 32px; font-weight: 600; }
QLabel#summarySectionTitle { padding-bottom: 4px; }
QLabel#runStatus { padding: 3px 8px; font-weight: 600; }
QTabWidget::pane { border: 1px solid palette(mid); }
QTabBar::tab { padding: 7px 12px; }
QGroupBox { font-weight: 600; }
QDockWidget::title { padding: 6px; }
QListWidget#recentList { border: 1px solid palette(mid); }
"""
