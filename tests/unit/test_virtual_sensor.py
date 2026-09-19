from __future__ import annotations

import pytest

from scentinel.core.virtual_sensor import VirtualSensorConfig, step_response


def test_step_response_approaches_ground_truth_without_overshoot():
    config = VirtualSensorConfig(noise_ppm=0, response_time_s=2)
    value = 0.0
    for index in range(40):
        reading = step_response(config, ground_truth_ppm=10, previous_ppm=value, elapsed_s=index + 1, step_s=1, sample_index=index)
        assert value <= reading.indicated_ppm <= 10
        value = reading.indicated_ppm
    assert value == pytest.approx(10, rel=1e-6)


def test_detection_limit_and_saturation_are_observable():
    config = VirtualSensorConfig(range_ppm=5, detection_limit_ppm=1, noise_ppm=0, response_time_s=0.01)
    low = step_response(config, ground_truth_ppm=0.5, previous_ppm=0, elapsed_s=1, step_s=1)
    high = step_response(config, ground_truth_ppm=20, previous_ppm=0, elapsed_s=1, step_s=1)
    assert low.below_detection and low.indicated_ppm == 0
    assert high.saturated and high.indicated_ppm == 5


def test_cross_sensitivity_changes_indicated_value():
    config = VirtualSensorConfig(cross_sensitivity=0.5, noise_ppm=0, response_time_s=0.01)
    reading = step_response(config, ground_truth_ppm=10, cross_gas_ppm=4, previous_ppm=0, elapsed_s=1, step_s=1)
    assert reading.indicated_ppm == pytest.approx(12)
