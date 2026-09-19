from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from scentinel.core.geometry import BinGeometry
from scentinel.core.project import Project, Sensor, save_project
from scentinel.core.scenario import Scenario
from scentinel.ui.home_window import HomeWindow
from scentinel.ui.results_panel import SensorReading


def _settings(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)


def test_home_routes_to_studio_and_sandbox_on_one_editor(qapp, translator, tmp_path):
    window = HomeWindow(translator, settings=_settings(tmp_path))
    assert window._stack.currentWidget() is window._home
    window.show_studio()
    assert window._stack.currentWidget() is window._editor
    assert not window._editor.lab_visible()
    window.show_sandbox()
    assert window._editor.lab_visible()
    window._editor.back_requested.emit()
    assert window._stack.currentWidget() is window._home
    window.deleteLater()


def test_studio_and_sandbox_share_the_same_project(qapp, translator, tmp_path):
    window = HomeWindow(translator, settings=_settings(tmp_path))
    window.show_studio()
    window._editor.viewport().add_sensor(3.0, 2.0)
    window.show_sandbox()
    assert [sensor.sensor_id for sensor in window._editor.viewport().sensors()] == ["S1"]
    window.deleteLater()


def test_sandbox_generates_virtual_telemetry(qapp, translator, tmp_path):
    window = HomeWindow(translator, settings=_settings(tmp_path))
    sandbox = window._editor
    sandbox.viewport().add_sensor(3.0, 2.0)
    sandbox.truth.setValue(50)
    sandbox.advance()
    assert sandbox._telemetry.item(0, 4).text().endswith(" ppm")
    assert sandbox._values["S1"] > 0
    summary = sandbox.results_panel()._summary_fields
    assert summary["tvoc_concentration"].text().endswith("ppm (virtual)")
    assert "no hardware required" in summary["calibration"].text()
    window.deleteLater()


def test_sandbox_uses_cfd_voc_and_lab_settings(qapp, translator, tmp_path):
    window = HomeWindow(translator, settings=_settings(tmp_path))
    sandbox = window._editor
    sandbox.viewport().add_sensor(3.0, 2.0)
    sandbox.truth.setValue(50)
    sandbox.results_panel().set_results(
        [SensorReading(sensor_id="S1", x=3.0, y=2.0, values={"VOC": 12.5, "CH4": 80.0})]
    )
    sandbox.advance()
    assert sandbox._telemetry.item(0, 2).text() == "cfd-voc"
    assert sandbox._telemetry.item(0, 3).text().startswith("12.5000")
    window.deleteLater()


def test_sandbox_publishes_lab_readings_into_the_results_table(qapp, translator, tmp_path):
    """The device model's output is what a reviewer reads, not a separate widget."""
    window = HomeWindow(translator, settings=_settings(tmp_path))
    sandbox = window._editor
    sandbox.viewport().add_sensor(3.0, 2.0)
    sandbox.truth.setValue(50)
    sandbox.advance()
    readings = sandbox.results_panel().readings()
    assert [reading.sensor_id for reading in readings] == ["S1"]
    assert readings[0].values["TVOC"] == pytest.approx(sandbox._values["S1"])
    assert readings[0].values["GROUND_TRUTH"] == pytest.approx(50.0)
    window.deleteLater()


def test_sandbox_results_table_survives_a_reset(qapp, translator, tmp_path):
    window = HomeWindow(translator, settings=_settings(tmp_path))
    sandbox = window._editor
    sandbox.viewport().add_sensor(3.0, 2.0)
    sandbox.advance()
    sandbox.reset_sensor_state()
    assert sandbox._values == {}
    assert sandbox.results_panel().readings() == []
    window.deleteLater()


def test_home_reopens_a_saved_project(qapp, translator, tmp_path):
    path = tmp_path / "bin.scentinel"
    save_project(
        Project(
            name="bin",
            geometry=BinGeometry(length_m=7.0),
            scenario=Scenario(waste_type="organic-rich", organic_fraction=0.8, gas_sources={"VOC": "auto"}),
            sensors=[Sensor(sensor_id="S1", x=1.0, y=2.0)],
        ),
        path,
    )
    window = HomeWindow(translator, settings=_settings(tmp_path))
    window._remember_project(path)
    assert window._recents.count() == 1
    window._open_recent_item(window._recents.item(0))
    assert window._stack.currentWidget() is window._editor
    assert window._editor.project().geometry.length_m == pytest.approx(7.0)
    assert window._editor.project().scenario.waste_type == "organic-rich"
    assert [sensor.sensor_id for sensor in window._editor.project().sensors] == ["S1"]
    window.deleteLater()


def test_opening_by_path_alone_loads_the_project(qapp, translator, tmp_path):
    """A caller that has only a path must still get the project it points at."""
    path = tmp_path / "direct.scentinel"
    save_project(
        Project(
            name="direct",
            geometry=BinGeometry(length_m=9.0),
            scenario=Scenario(waste_type="green-waste", gas_sources={"VOC": "auto"}),
            sensors=[Sensor(sensor_id="S7", x=2.0, y=1.0)],
        ),
        path,
    )
    window = HomeWindow(translator, path=path, settings=_settings(tmp_path))
    assert window._editor.project().geometry.length_m == pytest.approx(9.0)
    assert window._editor.project().scenario.waste_type == "green-waste"
    assert [sensor.sensor_id for sensor in window._editor.project().sensors] == ["S7"]
    assert window._editor.project_path() == path
    window.deleteLater()


def test_a_missing_path_falls_back_to_a_blank_project(qapp, translator, tmp_path):
    window = HomeWindow(translator, path=tmp_path / "nope.scentinel", settings=_settings(tmp_path))
    assert window._editor.project().sensors == []
    assert window._editor.project_path() is None
    window.deleteLater()

