import pytest

from scentinel.core import casegen, post, runner
from scentinel.core.geometry import BinGeometry, mound_profile_length
from scentinel.core.mesh import generate_mesh
from scentinel.core.scenario import Scenario

pytestmark = pytest.mark.verification


def test_mass_balance_on_a_solved_bin_case(tmp_path):
    if not runner.podman_available():
        pytest.skip("podman unavailable")
    if not runner.image_available():
        pytest.skip(f"{casegen.IMAGE} not pulled")

    geom = BinGeometry(
        length_m=6.0,
        height_m=2.5,
        mound_shape="mounded",
        mound_fill_fraction=0.45,
    )
    scenario = Scenario(
        gas_sources={"CO": "auto"},
        tonnage_t=10.0,
        age_h=24 * 365 * 3,
    )
    mesh = generate_mesh(geom, 0.5, tmp_path / "mesh")
    case = casegen.write_case(
        scenario,
        mesh,
        tmp_path / "case",
        geom=geom,
        end_time=500,
    )
    result = runner.run_case(case)
    assert result.ok, runner.stage_log(case, result.failed_stage or "simpleFoam")[-2000:]

    # Integrate the imposed boundary condition over the computational source
    # patch. The physical bin width is already used to derive J_mass; the 2D
    # CFD slab is only mesh.thickness_m deep, so its patch area is profile
    # length * slab thickness, not the physical profile length * bin width.
    source_patch_area = mound_profile_length(geom) * mesh.thickness_m
    source = (
        casegen.source_gradient(scenario, geom, "CO")
        * casegen.scalar_diffusivity("CO")
        * source_patch_area
    )
    error = post.mass_balance_error(case, "CO", source_flux=source)
    assert abs(error) < 0.05, f"mass balance error {error:.1%}"
