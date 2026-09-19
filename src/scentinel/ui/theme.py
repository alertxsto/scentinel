"""Small palette-aware polish layered over the native Qt desktop style."""

APP_STYLE = """
QWidget { font-size: 13px; }
QFrame#navigationRail {
    background: palette(alternate-base);
    border-right: 1px solid palette(mid);
}
QLabel#railCaption { padding: 10px 12px; }
QPushButton#navigationButton {
    min-height: 38px; padding: 0 12px; text-align: left;
    border: 1px solid transparent; border-radius: 4px;
}
QPushButton#navigationButton:hover { background: palette(base); border-color: palette(mid); }
QPushButton#navigationButton:checked {
    background: palette(highlight); color: palette(highlighted-text);
    border-color: palette(highlight);
}
QFrame#contextBar { background: palette(base); border-bottom: 1px solid palette(mid); }
QLabel#solverBadge {
    background: palette(alternate-base); border: 1px solid palette(mid);
    border-radius: 4px; padding: 5px 9px;
}
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
"""
