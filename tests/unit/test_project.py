from __future__ import annotations

import pytest

from scentinel.core.geometry import BinGeometry
from scentinel.core.project import Project, Sensor, load_project, save_project
from scentinel.core.scenario import Scenario


def _sample() -> Project:
    return Project(
        name="Test run",
        geometry=BinGeometry(
            length_m=6.0, height_m=2.5, mound_shape="mounded", mound_fill_fraction=0.6
        ),
        scenario=Scenario(
            wind_speed_m_s=1.5,
            wind_direction="right-to-left",
            ventilation_on=True,
            gas_sources={"CO": 105.0, "CH4": 500000.0},
        ),
        sensors=[Sensor(sensor_id="S1", x=1.0, y=2.0), Sensor(sensor_id="S2", x=4.5, y=1.75)],
    )


def test_round_trip(tmp_path):
    path = tmp_path / "test.scentinel"
    original = _sample()
    save_project(original, path)
    loaded = load_project(path)
    assert loaded == original


def test_file_is_json(tmp_path):
    path = tmp_path / "test.scentinel"
    save_project(_sample(), path)
    text = path.read_text()
    assert text.lstrip().startswith("{")
    assert '"geometry"' in text
    assert '"sensors"' in text


def test_unknown_format_version_is_rejected(tmp_path):
    path = tmp_path / "future.scentinel"
    path.write_text('{"format_version": 99, "name": "x"}', encoding="utf-8")
    with pytest.raises(ValueError, match="format_version"):
        load_project(path)


def test_sensor_list_survives_reload_with_order(tmp_path):
    path = tmp_path / "order.scentinel"
    save_project(_sample(), path)
    ids = [sensor.sensor_id for sensor in load_project(path).sensors]
    assert ids == ["S1", "S2"]
