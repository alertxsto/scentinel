"""End-to-end runs against the real OpenFOAM container.

These skip unless podman and the solver image are both present.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scentinel.core import casegen, post, runner
from scentinel.core.geometry import BinGeometry
from scentinel.core.mesh import generate_mesh
from scentinel.core.project import Sensor
from scentinel.core.scenario import Scenario

pytestmark = pytest.mark.integration


def _requires_container() -> None:
    if not runner.podman_available():
        pytest.skip("podman unavailable")
    if not runner.image_available():
        pytest.skip(f"{casegen.IMAGE} not pulled")


@pytest.fixture(scope="module")
def solved_case(tmp_path_factory) -> Path:
    _requires_container()
    root = tmp_path_factory.mktemp("e2e")
    geom = BinGeometry(length_m=6.0, height_m=2.5, mound_shape="mounded", mound_fill_fraction=0.45)
    mesh = generate_mesh(geom, 0.5, root / "mesh")
    case = casegen.write_case(
        Scenario(wind_speed_m_s=2.0, gas_sources={"CO": "auto"}),
        mesh,
        root / "case",
        geom=geom,
        end_time=200,
    )
    result = runner.run_case(case)
    assert result.ok, runner.read_log(result) + runner.stage_log(case, result.failed_stage or "")
    return case


def test_mesh_conversion_produces_cells(solved_case: Path):
    log = runner.stage_log(solved_case, "gmshToFoam")
    assert "FOAM FATAL" not in log
    assert (solved_case / "constant" / "polyMesh" / "points").exists()


def test_patch_types_are_corrected(solved_case: Path):
    """gmshToFoam writes every patch as `patch`; changeDictionary fixes them."""
    boundary = (solved_case / "constant" / "polyMesh" / "boundary").read_text()
    assert "defaultFaces" not in boundary
    assert "empty" in boundary
    assert "wall" in boundary


def test_solver_converges_without_fatal_errors(solved_case: Path):
    log = runner.stage_log(solved_case, casegen.SOLVER)
    assert "FOAM FATAL" not in log
    assert "End" in log


def test_vtk_output_is_written(solved_case: Path):
    assert post.time_directories(solved_case)
    internal = post.internal_vtu(solved_case)
    assert internal.exists()


def test_probes_read_a_positive_concentration_near_the_waste(solved_case: Path):
    sensors = [Sensor("near", 5.5, 1.0), Sensor("high", 3.0, 4.5)]
    readings = {r.sensor_id: r for r in post.sample_sensors(solved_case, sensors)}
    assert readings["near"].values["CO"] > readings["high"].values["CO"]
    assert readings["near"].values["CO"] > 0.0


def test_real_field_renders_with_sensor_and_hotspot_overlays(
    solved_case: Path, tmp_path: Path
):
    sensors = [Sensor("near", 5.5, 1.0), Sensor("high", 3.0, 2.2)]
    image = tmp_path / "co-field.png"
    summary = post.render_concentration_field(
        solved_case, "CO", image, sensors=sensors
    )

    assert image.is_file()
    assert image.stat().st_size > 10_000
    assert summary.maximum_ppmv > summary.mean_ppmv > summary.minimum_ppmv
    assert 0.0 <= summary.hotspot_x_m <= 6.0
    assert 0.0 <= summary.hotspot_y_m <= 2.5


def test_concentration_is_positive_and_finite(solved_case: Path):
    """A probe near the waste reads a positive, finite value.

    The old bound — "nothing may exceed the source concentration" — no longer
    holds: the source is an emission mass flux imposed as a ``fixedGradient``,
    not a fixed surface concentration, so the near-wall value is set by the
    flux/diffusion balance rather than capped at the nominal ppmv. What remains
    true is that a probe above the waste sees gas and the value is physical.
    """
    for reading in post.sample_sensors(solved_case, [Sensor("s", 3.0, 2.5)]):
        value = reading.values["CO"]
        assert value > 0.0
        assert value < 1.0e6, f"absurd ppmv {value}"
