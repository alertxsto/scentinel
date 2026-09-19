from __future__ import annotations

from scentinel.ui.home_window import HomeWindow


def test_home_routes_to_both_working_modes(qapp, translator):
    window = HomeWindow(translator)
    assert window._stack.currentWidget() is window._home
    window.show_studio()
    assert window._stack.currentWidget() is window._studio
    window.show_sandbox()
    assert window._stack.currentWidget() is window._sandbox
    window._sandbox.back_requested.emit()
    assert window._stack.currentWidget() is window._home
    window.deleteLater()


def test_sandbox_generates_virtual_telemetry(qapp, translator):
    window = HomeWindow(translator)
    sandbox = window._sandbox
    sandbox.viewport.add_sensor(3.0, 2.0)
    sandbox.truth.setValue(50)
    sandbox.advance()
    assert "truth=" in sandbox.log.toPlainText()
    assert sandbox._values["S1"] > 0
    window.deleteLater()
