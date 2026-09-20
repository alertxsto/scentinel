from __future__ import annotations

import pytest

from scentinel.core import geometry
from scentinel.core.geometry import (
    BinGeometry,
    MOUND_SHAPES,
    air_domain,
    bin_polygon,
    emission_area_m2,
    fill_fraction,
    mound_area,
    mound_height_at,
    mound_polygon,
    mound_profile_length,
)


def test_bin_polygon_dimensions():
    geom = BinGeometry(length_m=6.0, height_m=2.5, mound_shape="flat", mound_fill_fraction=0.5)
    xs = [p[0] for p in bin_polygon(geom)]
    ys = [p[1] for p in bin_polygon(geom)]
    assert (min(xs), max(xs)) == (0.0, 6.0)
    assert (min(ys), max(ys)) == (0.0, 2.5)


@pytest.mark.parametrize("shape", MOUND_SHAPES)
def test_requested_fill_fraction_is_met(shape: str):
    geom = BinGeometry(length_m=6.0, height_m=2.5, mound_shape=shape, mound_fill_fraction=0.4)
    assert mound_area(geom) == pytest.approx(6.0 * 2.5 * 0.4, rel=1e-6)
    assert fill_fraction(geom) == pytest.approx(0.4, rel=1e-6)


@pytest.mark.parametrize("shape", [shape for shape in MOUND_SHAPES if shape != "flat"])
def test_mound_peaks_above_a_flat_fill(shape: str):
    flat = BinGeometry(mound_shape="flat", mound_fill_fraction=0.4)
    peaked = BinGeometry(mound_shape=shape, mound_fill_fraction=0.4)
    assert max(y for _, y in mound_polygon(peaked)) > max(y for _, y in mound_polygon(flat))


def test_mound_never_leaves_the_bin():
    geom = BinGeometry(length_m=6.0, height_m=2.5, mound_shape="mounded", mound_fill_fraction=0.9)
    assert max(y for _, y in mound_polygon(geom)) <= 2.5


def test_mound_height_at_tracks_the_outline():
    geom = BinGeometry(length_m=6.0, height_m=2.5, mound_shape="flat", mound_fill_fraction=0.5)
    assert mound_height_at(geom, 3.0) == pytest.approx(1.25)
    assert mound_height_at(geom, -0.5) == 0.0
    assert mound_height_at(geom, 6.5) == 0.0

    peaked = BinGeometry(length_m=6.0, height_m=2.5, mound_shape="mounded", mound_fill_fraction=0.4)
    assert mound_height_at(peaked, 3.0) > mound_height_at(peaked, 0.5)


def test_placement_problem_names_why_a_point_is_rejected():
    geom = BinGeometry(
        length_m=6.0,
        height_m=2.5,
        mound_shape="mounded",
        mound_fill_fraction=0.45,
    )
    assert geometry.placement_problem(geom, 3.0, 2.0) == ""
    assert "outside" in geometry.placement_problem(geom, -0.1, 1.0)
    assert "mound" in geometry.placement_problem(geom, 0.5, 0.2)


def test_irregular_mound_is_deterministic():
    geom = BinGeometry(length_m=6.0, height_m=2.5, mound_shape="irregular", mound_fill_fraction=0.5)
    assert mound_polygon(geom) == mound_polygon(geom)


def test_left_and_right_heavy_profiles_are_mirrors():
    left = mound_polygon(BinGeometry(mound_shape="left-heavy", mound_fill_fraction=0.4))
    right = mound_polygon(BinGeometry(mound_shape="right-heavy", mound_fill_fraction=0.4))
    length = 6.0
    mirrored_right = [(length - x, y) for x, y in reversed(right)]
    assert left == pytest.approx(mirrored_right)


def test_air_domain_extends_above_bin():
    geom = BinGeometry(length_m=6.0, height_m=2.5)
    ys = [p[1] for p in air_domain(geom, extension_m=3.0)]
    assert max(ys) == pytest.approx(5.5)


def test_invalid_mound_shape_raises():
    with pytest.raises(ValueError):
        BinGeometry(length_m=6.0, height_m=2.5, mound_shape="pyramid", mound_fill_fraction=0.5)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"length_m": 0.0},
        {"height_m": -1.0},
        {"width_m": 0.0},
        {"mound_fill_fraction": 0.0},
        {"mound_fill_fraction": 1.5},
    ],
)
def test_invalid_dimensions_raise(kwargs: dict):
    with pytest.raises(ValueError):
        BinGeometry(**kwargs)


def test_width_defaults_to_a_truck_bin_width():
    assert BinGeometry().width_m == pytest.approx(2.4)


def test_emission_area_is_the_profile_length_times_the_width():
    """A flat mound's surface is the bin length; the area extrudes it by width."""
    geom = BinGeometry(
        length_m=6.0, height_m=2.5, width_m=2.0,
        mound_shape="flat", mound_fill_fraction=0.5,
    )
    assert mound_profile_length(geom) == pytest.approx(6.0)
    assert emission_area_m2(geom) == pytest.approx(12.0)


def test_a_curved_mound_has_a_longer_profile_than_its_span():
    geom = BinGeometry(
        length_m=6.0, height_m=2.5, width_m=2.0,
        mound_shape="mounded", mound_fill_fraction=0.45,
    )
    assert mound_profile_length(geom) > geom.length_m
    assert emission_area_m2(geom) == pytest.approx(
        mound_profile_length(geom) * 2.0
    )
