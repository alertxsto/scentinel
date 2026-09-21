from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from scentinel.core.geometry import BinGeometry
from scentinel.core.history import HistoryError
from scentinel.core.project import Project, Sensor, save_project
from scentinel.core.scenario import Scenario
from scentinel.ui.home_window import HomeWindow
from scentinel.ui.results_panel import SensorReading


def _settings(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)


def test_the_shell_has_one_editor_and_a_start_screen(qapp, translator, tmp_path):
    """There is no mode switch: opening a project raises the one workspace."""
    window = HomeWindow(translator, settings=_settings(tmp_path))
    assert window._stack.currentWidget() is window._start
    window.show_workspace()
    assert window._stack.currentWidget() is window._editor
    window.show_start()
    assert window._stack.currentWidget() is window._start
    window.deleteLater()


def test_opening_a_project_never_swaps_the_editor(qapp, translator, tmp_path):
    window = HomeWindow(translator, settings=_settings(tmp_path))
    editor = window._editor
    window.show_workspace()
    editor.viewport().add_sensor(3.0, 2.0)
    window.show_start()
    window.show_workspace()
    assert window._editor is editor
    assert [s.sensor_id for s in editor.viewport().sensors()] == ["S1"]
    window.deleteLater()


def test_the_lab_is_a_panel_on_the_same_project(qapp, translator, tmp_path):
    """The lab reads the editor's sensors and results; it is not a second copy."""
    window = HomeWindow(translator, settings=_settings(tmp_path))
    editor = window._editor
    editor.viewport().add_sensor(3.0, 2.0)
    QApplication.processEvents()
    assert [s.sensor_id for s in editor.sensor_lab()._sensors] == ["S1"]
    window.deleteLater()


def test_lab_replay_produces_telemetry(qapp, translator, tmp_path):
    window = HomeWindow(translator, settings=_settings(tmp_path))
    editor = window._editor
    editor.viewport().add_sensor(3.0, 2.0)
    QApplication.processEvents()
    lab = editor.sensor_lab()
    lab.truth.setValue(50)
    lab.advance()
    assert lab._telemetry.item(0, 4).text().endswith(" ppm")
    assert lab._values["S1"] > 0
    window.deleteLater()


def test_lab_uses_cfd_readings_as_ground_truth(qapp, translator, tmp_path):
    window = HomeWindow(translator, settings=_settings(tmp_path))
    editor = window._editor
    editor.viewport().add_sensor(3.0, 2.0)
    editor.results_panel().set_results(
        [SensorReading(sensor_id="S1", x=3.0, y=2.0, values={"VOC": 12.5, "CH4": 80.0})]
    )
    QApplication.processEvents()
    lab = editor.sensor_lab()
    lab.set_context(editor.viewport().sensors(), editor.results_panel().readings())
    lab.advance()
    assert lab._telemetry.item(0, 2).text() == "cfd-voc"
    assert lab._telemetry.item(0, 3).text().startswith("12.5000")
    window.deleteLater()


def test_lab_reset_clears_its_state(qapp, translator, tmp_path):
    window = HomeWindow(translator, settings=_settings(tmp_path))
    editor = window._editor
    editor.viewport().add_sensor(3.0, 2.0)
    QApplication.processEvents()
    lab = editor.sensor_lab()
    lab.advance()
    lab.reset_sensor_state()
    assert lab._values == {}
    window.deleteLater()


def test_lab_edits_persist_into_the_project(qapp, translator, tmp_path):
    """A device model edited in the panel is part of the project, not the widget."""
    window = HomeWindow(translator, settings=_settings(tmp_path))
    editor = window._editor
    lab = editor.sensor_lab()
    lab.lod.setValue(0.5)
    QApplication.processEvents()
    assert editor.project().sensor_lab.detection_limit_ppm == pytest.approx(0.5)
    window.deleteLater()


def test_home_reopens_a_saved_project(qapp, translator, tmp_path):
    path = tmp_path / "bin.scentinel"
    save_project(
        Project(
            name="bin",
            geometry=BinGeometry(length_m=7.0),
            scenario=Scenario(waste_type="organic-rich", age_h=12.0, gas_sources={"VOC": "auto"}),
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

def test_home_opens_a_project_when_legacy_history_cannot_be_decoded(
    qapp, translator, tmp_path, monkeypatch
):
    path = tmp_path / "legacy.scentinel"
    save_project(Project(name="legacy", geometry=BinGeometry(length_m=7.5)), path)
    window = HomeWindow(translator, settings=_settings(tmp_path))
    window._remember_project(path)

    monkeypatch.setattr(
        "scentinel.ui.main_window.history.list_runs",
        lambda _root: (_ for _ in ()).throw(HistoryError("unsupported format_version 4")),
    )

    window._open_recent_item(window._recents.item(0))

    assert window._stack.currentWidget() is window._editor
    assert window._editor.project().geometry.length_m == pytest.approx(7.5)
    assert window._editor.project_path() == path
    assert window._editor.results_panel().readings() == []
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

