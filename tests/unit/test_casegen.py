from __future__ import annotations

from pathlib import Path

import pytest

from scentinel.core.casegen import (
    IMAGE,
    SCALAR_DIFFUSIVITY_M2_S,
    SOLVER,
    WALL_PATCHES,
    applied_physics,
    case_input_digest,
    patch_roles,
    resolve_sources,
    wind_speed_at,
    write_case,
)
from scentinel.core.geometry import BinGeometry
from scentinel.core.mesh import PATCHES, MeshResult
from scentinel.core.scenario import Scenario


@pytest.fixture
def mesh(tmp_path: Path) -> MeshResult:
    msh = tmp_path / "case.msh"
    msh.write_text("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n")
    return MeshResult(msh_path=msh, patches={name: i for i, name in enumerate(PATCHES, 1)})


def test_auto_sources_use_the_cited_ap42_defaults():
    scenario = Scenario(gas_sources={"CO": "auto", "H2S": "auto"})
    resolved = resolve_sources(scenario)
    assert resolved["CO"] == pytest.approx(105e-6)
    assert resolved["H2S"] == pytest.approx(36e-6)


def test_explicit_sources_are_kept_as_given():
    resolved = resolve_sources(Scenario(gas_sources={"CO": 50.0}))
    assert resolved["CO"] == pytest.approx(50e-6)


def test_unknown_auto_gas_raises():
    with pytest.raises(KeyError):
        resolve_sources(Scenario(gas_sources={"NOPE": "auto"}))


@pytest.mark.parametrize(
    ("direction", "inlet", "outlet"),
    [("left-to-right", "openLeft", "openRight"), ("right-to-left", "openRight", "openLeft")],
)
def test_wind_direction_swaps_inlet_and_outlet(direction: str, inlet: str, outlet: str):
    roles = patch_roles(Scenario(wind_direction=direction))
    assert roles[inlet].kind == "inlet"
    assert roles[outlet].kind == "outlet"


def test_bin_walls_are_walls_and_the_lid_slips():
    roles = patch_roles(Scenario())
    for name in WALL_PATCHES:
        assert roles[name].kind == "wall"
    assert roles["top"].kind == "slip"
    assert roles["frontAndBack"].kind == "empty"


def test_wind_is_slowed_from_the_reference_height():
    """AP-42 wind speeds are quoted at 10 m; the bin sits lower."""
    scenario = Scenario(wind_speed_m_s=2.0)
    assert wind_speed_at(scenario, 10.0) == pytest.approx(2.0)
    assert wind_speed_at(scenario, 2.5) < 2.0
    assert wind_speed_at(scenario, 0.0) == 0.0


def test_calm_wind_stays_zero():
    assert wind_speed_at(Scenario(wind_speed_m_s=0.0), 2.5) == 0.0


def test_case_has_the_files_openfoam_needs(tmp_path, mesh):
    case = write_case(
        Scenario(gas_sources={"CO": "auto"}), mesh, tmp_path / "case", geom=BinGeometry()
    )
    for relative in (
        "0/U",
        "0/p",
        "0/k",
        "0/epsilon",
        "0/nut",
        "0/CO",
        "constant/transportProperties",
        "constant/turbulenceProperties",
        "system/controlDict",
        "system/fvSchemes",
        "system/fvSolution",
        "system/functions",
        "system/changeDictionaryDict",
        "case.msh",
    ):
        assert (case / relative).exists(), relative


def test_solver_and_image_are_named_for_the_esi_distribution():
    """The ESI image ships simpleFoam, not foamRun/incompressibleFluid."""
    assert SOLVER == "simpleFoam"
    assert IMAGE.startswith("docker.io/")


def test_control_dict_names_the_solver(tmp_path, mesh):
    case = write_case(
        Scenario(gas_sources={"CO": "auto"}), mesh, tmp_path / "case", geom=BinGeometry()
    )
    assert f"application     {SOLVER};" in (case / "system" / "controlDict").read_text()


def test_scalar_field_carries_the_source_concentration(tmp_path, mesh):
    case = write_case(
        Scenario(gas_sources={"CO": 105.0}), mesh, tmp_path / "case", geom=BinGeometry()
    )
    text = (case / "0" / "CO").read_text()
    assert "source" in text
    assert "0.000105" in text


def test_wind_sign_reaches_the_inlet_velocity(tmp_path, mesh):
    scenario = Scenario(wind_speed_m_s=2.0, wind_direction="right-to-left")
    case = write_case(scenario, mesh, tmp_path / "case", geom=BinGeometry())
    text = (case / "0" / "U").read_text()
    speed = wind_speed_at(scenario, 2.5)
    assert f"-{speed:g}" in text


def test_every_patch_gets_a_boundary_condition(tmp_path, mesh):
    """A missing entry makes OpenFOAM abort while reading the fields."""
    case = write_case(
        Scenario(gas_sources={"CO": "auto"}), mesh, tmp_path / "case", geom=BinGeometry()
    )
    for field in ("U", "p", "k", "epsilon", "nut", "CO"):
        text = (case / "0" / field).read_text()
        body = text.split("boundaryField", 1)[1]
        for patch in PATCHES:
            assert patch in body, f"{patch} missing from 0/{field}"


def test_change_dictionary_types_the_special_patches(tmp_path, mesh):
    case = write_case(
        Scenario(gas_sources={"CO": "auto"}), mesh, tmp_path / "case", geom=BinGeometry()
    )
    text = (case / "system" / "changeDictionaryDict").read_text()
    assert '"frontAndBack"' in text and "type            empty;" in text
    assert "wallLeft" in text
    # gmshToFoam writes plain `patch`; the wall functions need real walls.
    assert text.count("type            wall;") >= 3


def test_missing_mesh_patch_is_rejected(tmp_path):
    msh = tmp_path / "case.msh"
    msh.write_text("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n")
    incomplete = MeshResult(msh_path=msh, patches={"source": 1})
    with pytest.raises(ValueError, match="missing patches"):
        write_case(Scenario(), incomplete, tmp_path / "case", geom=BinGeometry())


def test_writing_twice_replaces_the_case(tmp_path, mesh):
    scenario = Scenario(gas_sources={"CO": "auto"})
    case = write_case(scenario, mesh, tmp_path / "case", geom=BinGeometry())
    stale = case / "0" / "stale"
    stale.write_text("x")
    write_case(scenario, mesh, tmp_path / "case", geom=BinGeometry())
    assert not stale.exists()


# -- applied physics ----------------------------------------------------------


def test_persisted_applied_physics_matches_the_generated_case(tmp_path, mesh):
    """Every persisted applied value must be readable out of the case files.

    This is the MB-1 guarantee: a manifest that claims a diffusivity, a solver
    tolerance, or a residual target the generated case does not contain would
    let comparison attribute a code/physics delta to the scenario.
    """
    geom = BinGeometry(length_m=6.0, height_m=2.5)
    scenario = Scenario(wind_speed_m_s=2.0, gas_sources={"CO": "auto", "VOC": 12.5})
    case = write_case(scenario, mesh, tmp_path / "case", geom=geom)

    applied = applied_physics(scenario, geom)

    functions = (case / "system" / "functions").read_text()
    assert f"D               {SCALAR_DIFFUSIVITY_M2_S:g};" in functions
    for gas in ("CO", "VOC"):
        assert applied["scalar_diffusivity_m2_s"][gas] == SCALAR_DIFFUSIVITY_M2_S

    transport = (case / "constant" / "transportProperties").read_text()
    assert f"nu              {applied['nu_m2_s']:g};" in transport

    solution = (case / "system" / "fvSolution").read_text()
    for entry in applied["linear_solver_settings"]:
        assert entry["fields"] in solution
        assert f"{entry['solver']}" in solution
    for key in applied["residual_targets"]:
        assert key in solution

    # The applied inlet speed is the scaled value, not the reported one, and it
    # is what the case actually wrote into the inlet boundary condition.
    assert applied["inlet_speed_at_rim_m_s"] == pytest.approx(
        wind_speed_at(scenario, geom.height_m)
    )
    assert applied["wind_speed_reported_m_s"] == 2.0
    assert applied["inlet_speed_at_rim_m_s"] != applied["wind_speed_reported_m_s"]
    assert f"{applied['inlet_speed_at_rim_m_s']:g}" in (case / "0" / "U").read_text()


def test_the_case_digest_is_stable_and_sensitive_to_applied_constants(tmp_path, mesh, monkeypatch):
    """Identical UI inputs plus a changed applied constant must change the digest."""
    geom = BinGeometry()
    scenario = Scenario(wind_speed_m_s=2.0, gas_sources={"CO": "auto"})
    gases = ["CO"]
    case = write_case(scenario, mesh, tmp_path / "case", geom=geom)

    first = case_input_digest(case, gases)
    assert first == case_input_digest(case, gases)
    assert first.startswith("sha256:") and len(first) == len("sha256:") + 64

    # The solver writes into the same tree; none of it may enter the digest.
    (case / "constant" / "polyMesh").mkdir()
    (case / "constant" / "polyMesh" / "points").write_text("solver output")
    (case / "log.simpleFoam").write_text("solver log")
    (case / "VTK").mkdir()
    (case / "VTK" / "internal.vtu").write_text("vtk")
    assert case_input_digest(case, gases) == first

    # A changed applied constant, at identical UI inputs, changes the digest.
    monkeypatch.setattr("scentinel.core.casegen.SCALAR_DIFFUSIVITY_M2_S", 3.0e-05)
    changed = write_case(scenario, mesh, tmp_path / "changed", geom=geom)
    assert case_input_digest(changed, gases) != first


def test_the_case_digest_covers_each_selected_gas(tmp_path, mesh):
    geom = BinGeometry()
    one = write_case(Scenario(gas_sources={"CO": "auto"}), mesh, tmp_path / "one", geom=geom)
    two = write_case(
        Scenario(gas_sources={"CO": "auto", "VOC": 12.5}), mesh, tmp_path / "two", geom=geom
    )

    assert case_input_digest(one, ["CO"]) != case_input_digest(two, ["CO", "VOC"])


def test_the_case_digest_rejects_a_missing_declared_input(tmp_path, mesh):
    case = write_case(
        Scenario(gas_sources={"CO": "auto"}), mesh, tmp_path / "case", geom=BinGeometry()
    )
    (case / "system" / "fvSolution").unlink()

    with pytest.raises(ValueError, match="missing or unreadable"):
        case_input_digest(case, ["CO"])


def test_write_case_requires_the_geometry(tmp_path, mesh):
    """The rim height sets the inlet speed, so it cannot be defaulted internally."""
    with pytest.raises(TypeError):
        write_case(Scenario(), mesh, tmp_path / "case")  # type: ignore[call-arg]
