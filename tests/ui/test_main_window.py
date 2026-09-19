from __future__ import annotations

from pathlib import Path

import pytest

from scentinel.core.geometry import BinGeometry
from scentinel.core.project import Project, Sensor, load_project, save_project
from scentinel.core.scenario import Scenario
from scentinel.ui.main_window import MainWindow


@pytest.fixture
def window(qapp, translator):
    widget = MainWindow(translator)
    yield widget
    widget.deleteLater()


def test_window_starts_on_the_default_project(window):
    assert window.project().geometry == BinGeometry()
    assert window.viewport().sensors() == []
    assert not window.is_dirty()


def test_editing_geometry_marks_the_project_dirty(window):
    window.setup_panel()._length.setValue(9.0)
    assert window.is_dirty()
    assert window.project().geometry.length_m == pytest.approx(9.0)
    assert window.viewport().geometry().length_m == pytest.approx(9.0)


def test_placing_a_sensor_flows_into_the_project(window):
    window.viewport().add_sensor(3.0, 2.0)
    assert [sensor.sensor_id for sensor in window.project().sensors] == ["S1"]


def test_save_then_open_round_trips_through_the_window(window, tmp_path):
    window.setup_panel()._length.setValue(7.0)
    window.setup_panel()._gas_boxes["CO"].setChecked(True)
    window.setup_panel()._gas_spins["CO"].setValue(105.0)
    window.viewport().add_sensor(3.0, 2.0)

    path = tmp_path / "run.scentinel"
    assert window._write_project(path)
    assert not window.is_dirty()
    assert window.project_path() == path

    window._apply_project(Project())
    assert window.viewport().sensors() == []

    window.open_project(path)
    assert window.project().geometry.length_m == pytest.approx(7.0)
    assert window.project().scenario.gas_sources == {"CO": 105.0}
    assert [sensor.sensor_id for sensor in window.project().sensors] == ["S1"]
    assert not window.is_dirty()


def test_saved_file_is_reloadable_by_the_core_loader(window, tmp_path):
    window.viewport().add_sensor(2.0, 1.9)
    path = tmp_path / "round.scentinel"
    window._write_project(path)
    assert load_project(path).sensors[0].x == pytest.approx(2.0)


def test_opening_a_broken_file_leaves_the_project_untouched(window, tmp_path, monkeypatch):
    path = tmp_path / "broken.scentinel"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(
        "scentinel.ui.main_window.QMessageBox.warning", lambda *args, **kwargs: None
    )

    window.open_project(path)

    assert window.project().geometry == BinGeometry()
    assert window.project_path() is None


def test_language_switch_updates_the_menus(window):
    window._set_locale("id")
    assert window._file_menu.title() == "Berkas"
    assert window._action_save.text() == "Simpan Proyek"


def test_export_writes_the_current_readings(window, tmp_path):
    from scentinel.ui.results_panel import SensorReading

    window.results_panel().set_results(
        [SensorReading(sensor_id="S1", x=1.0, y=2.0, values={"CO": 12.5})]
    )
    target = window.results_panel().export_results_csv(tmp_path / "out.csv")

    text = Path(target).read_text()
    assert "sensor_id" in text
    assert "S1" in text
    assert "12.5" in text


def test_sensor_eviction_keeps_project_in_sync(window):
    window.viewport().add_sensor(3.0, 1.4)
    window.setup_panel()._fill.setValue(0.9)
    assert window.project().sensors == []
