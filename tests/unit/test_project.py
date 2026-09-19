from __future__ import annotations

import json

import pytest

from scentinel.core.geometry import BinGeometry
from scentinel.core.project import Project, Sensor, load_project, save_project
from scentinel.core.scenario import WASTE_SPECS, Scenario


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


def test_a_version_1_project_loads_with_the_default_width(tmp_path):
    """A v1 file predates the bin width; it loads with the default, not an error."""
    path = tmp_path / "old.scentinel"
    path.write_text(
        json.dumps(
            {
                "format_version": 1,
                "name": "old",
                "geometry": {
                    "length_m": 6.0,
                    "height_m": 2.5,
                    "mound_shape": "flat",
                    "mound_fill_fraction": 0.5,
                },
                "scenario": {
                    "wind_speed_m_s": 1.0,
                    "wind_direction": "left-to-right",
                    "ventilation_on": False,
                    "waste_type": "mixed-msw",
                    "age_h": 8.0,
                    "moisture_fraction": 0.4,
                    "gas_sources": {},
                },
                "sensors": [],
            }
        ),
        encoding="utf-8",
    )
    loaded = load_project(path)
    assert loaded.geometry.width_m == pytest.approx(2.4)
    assert loaded.name == "old"


def test_a_saved_project_is_version_2_and_carries_the_width(tmp_path):
    path = tmp_path / "new.scentinel"
    save_project(
        Project(name="w", geometry=BinGeometry(width_m=3.0)), path
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["format_version"] == 2
    assert payload["geometry"]["width_m"] == pytest.approx(3.0)
    assert load_project(path).geometry.width_m == pytest.approx(3.0)


def test_sensor_list_survives_reload_with_order(tmp_path):
    path = tmp_path / "order.scentinel"
    save_project(_sample(), path)
    ids = [sensor.sensor_id for sensor in load_project(path).sensors]
    assert ids == ["S1", "S2"]

def test_waste_stream_and_sensor_lab_round_trip(tmp_path):
    from scentinel.core.virtual_sensor import VirtualSensorConfig

    path = tmp_path / "waste.scentinel"
    original = Project(
        name="waste",
        geometry=BinGeometry(),
        scenario=Scenario(
            waste_type="organic-rich",
            age_h=12.0,
            moisture_fraction=0.6,
            gas_sources={"VOC": "auto"},
        ),
        sensor_lab=VirtualSensorConfig(family="MOX", response_time_s=4.0),
    )
    save_project(original, path)
    loaded = load_project(path)
    assert loaded == original


def test_the_batch_inputs_round_trip_through_the_project_file(tmp_path):
    """The composition and tonnage the batch panel edits must persist.

    They are inputs to the run now, not display-only state: losing them on save
    would mean reopening a project silently solves a different waste.
    """
    from scentinel.core.composition import WasteComposition

    path = tmp_path / "batch.scentinel"
    original = Project(
        name="batch",
        geometry=BinGeometry(),
        scenario=Scenario(
            gas_sources={"CH4": "auto"},
            age_h=24.0 * 365 * 2,
            moisture_fraction=0.25,
            tonnage_t=6.5,
            composition_fractions=WasteComposition(paper=0.7, food=0.3).as_dict(),
        ),
    )
    save_project(original, path)
    loaded = load_project(path)

    assert loaded.scenario.tonnage_t == pytest.approx(6.5)
    assert loaded.scenario.composition == WasteComposition(paper=0.7, food=0.3)


def test_legacy_project_without_waste_or_lab_still_loads(tmp_path):
    path = tmp_path / "legacy.scentinel"
    path.write_text(
        """
{
  "format_version": 1,
  "name": "old",
  "geometry": {
    "length_m": 6.0,
    "height_m": 2.5,
    "mound_shape": "flat",
    "mound_fill_fraction": 0.5
  },
  "scenario": {
    "wind_speed_m_s": 1.0,
    "wind_direction": "left-to-right",
    "ventilation_on": false,
    "gas_sources": {"CO": "auto"}
  },
  "sensors": []
}
""",
        encoding="utf-8",
    )
    loaded = load_project(path)
    assert loaded.scenario.waste_type == "mixed-msw"
    # Derived from the default preset, not a stored scalar.
    assert loaded.scenario.organic_fraction == pytest.approx(
        WASTE_SPECS["mixed-msw"].composition.degradable_fraction()
    )
    assert loaded.scenario.age_h == pytest.approx(8.0)
    assert loaded.sensor_lab.family == "PID"
