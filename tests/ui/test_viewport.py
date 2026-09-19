from __future__ import annotations

import pytest

from scentinel.core.geometry import BinGeometry
from scentinel.core.project import Sensor
from scentinel.ui.viewport import ViewportWidget


@pytest.fixture
def viewport(qapp):
    widget = ViewportWidget()
    widget.set_geometry(BinGeometry(length_m=6.0, height_m=2.5, mound_shape="flat", mound_fill_fraction=0.5))
    yield widget
    widget.deleteLater()


def test_sensors_are_placed_inside_the_free_air(viewport):
    sensor = viewport.add_sensor(3.0, 2.0)
    assert sensor is not None
    assert viewport.sensors() == [sensor]


def test_clicks_inside_the_mound_are_rejected(viewport):
    assert viewport.add_sensor(3.0, 1.0) is None
    assert viewport.sensors() == []


def test_clicks_outside_the_bin_are_rejected(viewport):
    assert viewport.add_sensor(-1.0, 1.0) is None
    assert viewport.add_sensor(3.0, 9.0) is None
    assert viewport.sensors() == []


def test_ids_increment_and_are_not_reused(viewport):
    first = viewport.add_sensor(1.0, 2.0)
    second = viewport.add_sensor(2.0, 2.0)
    viewport.remove_sensor(first.sensor_id)
    third = viewport.add_sensor(3.0, 2.0)
    assert (first.sensor_id, second.sensor_id, third.sensor_id) == ("S1", "S2", "S3")


def test_removing_a_sensor_updates_the_list(viewport):
    sensor = viewport.add_sensor(1.0, 2.0)
    viewport.remove_sensor(sensor.sensor_id)
    assert viewport.sensors() == []


def test_sensor_added_signal_fires(viewport):
    seen = []
    viewport.sensor_added.connect(seen.append)
    viewport.add_sensor(2.0, 2.0)
    assert len(seen) == 1


def test_raising_the_mound_evicts_now_buried_sensors(viewport):
    viewport.add_sensor(3.0, 1.5)
    viewport.set_geometry(
        BinGeometry(length_m=6.0, height_m=2.5, mound_shape="flat", mound_fill_fraction=0.8)
    )
    assert viewport.sensors() == []


def test_set_sensors_filters_positions_outside_the_free_air(viewport):
    viewport.set_sensors(
        [
            Sensor(sensor_id="S1", x=3.0, y=2.2),
            Sensor(sensor_id="S2", x=3.0, y=0.5),
        ]
    )
    assert [sensor.sensor_id for sensor in viewport.sensors()] == ["S1"]


def test_clear_sensors_empties_the_viewport(viewport):
    viewport.add_sensor(1.0, 2.0)
    viewport.clear_sensors()
    assert viewport.sensors() == []
