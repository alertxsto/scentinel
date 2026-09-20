from __future__ import annotations

import re
from pathlib import Path

import pytest

from scentinel.core import casegen, gas_data
from scentinel.core.casegen import (
    IMAGE,
    SOLVER,
    WALL_PATCHES,
    applied_physics,
    case_input_digest,
    emission_flux_kg_per_m2_s,
    emission_rate_kg_per_s,
    patch_roles,
    resolve_sources,
    scalar_diffusivity,
    wind_speed_at,
    write_case,
)
from scentinel.core.geometry import BinGeometry, emission_area_m2
from scentinel.core.mesh import PATCHES, MeshResult
from scentinel.core.scenario import Scenario


@pytest.fixture
def mesh(tmp_path: Path) -> MeshResult:
    msh = tmp_path / "case.msh"
    msh.write_text("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n")
    return MeshResult(msh_path=msh, patches={name: i for i, name in enumerate(PATCHES, 1)})


def test_the_source_patch_imposes_a_gradient_not_a_value(tmp_path, mesh):
    """The flux boundary is the fix: a value makes the near-wall gradient scale
    with the first cell height; a gradient does not."""
    scenario = Scenario(gas_sources={"CO": "auto"}, tonnage_t=10.0)
    case = write_case(scenario, mesh, tmp_path / "case", geom=BinGeometry())
    field = (case / "0" / "CO").read_text()
    source_block = field.split("source")[1].split("}")[0]
    assert "fixedGradient" in source_block
    assert "gradient" in source_block
    assert "fixedValue" not in source_block


def test_the_gradient_matches_the_flux_over_diffusivity(tmp_path, mesh):
    from scentinel.core.casegen import source_gradient

    scenario = Scenario(gas_sources={"CO": "auto"}, tonnage_t=10.0)
    geom = BinGeometry()
    case = write_case(scenario, mesh, tmp_path / "case", geom=geom)
    field = (case / "0" / "CO").read_text()
    source_block = field.split("source")[1].split("}")[0]
    expected = source_gradient(scenario, geom, "CO")
    assert f"{expected:g}" in source_block


def test_the_gradient_is_in_field_units_not_ppmv():
    """The transported scalar is a volume *fraction* (dimensionless).

    ``resolve_sources`` returns fractions, the source boundary used to write a
    fraction, and the post-processor multiplies by ``1e6`` only for display. So
    the imposed gradient must be ``J_C / D`` in fraction/m — a ``1e6`` there
    inflates the flux a million-fold and the sampled field above 1. The flux is
    ``J * (Vm / MW)`` in fraction*m/s; multiplied by ``D`` it must come back.
    """
    from scentinel.core.casegen import (
        MOLAR_VOLUME_M3_PER_MOL,
        emission_flux_kg_per_m2_s,
        source_gradient,
    )

    scenario = Scenario(gas_sources={"CO": "auto"}, tonnage_t=10.0, age_h=24 * 365 * 3)
    geom = BinGeometry()
    flux = emission_flux_kg_per_m2_s(scenario, geom, "CO")
    mw = gas_data.get_gas("CO").mw_g_mol / 1000.0
    fraction_flux = flux * (MOLAR_VOLUME_M3_PER_MOL / mw)
    assert source_gradient(scenario, geom, "CO") * scalar_diffusivity("CO") == pytest.approx(
        fraction_flux
    )



def test_applied_physics_records_the_flux_and_area(tmp_path, mesh):
    scenario = Scenario(gas_sources={"CO": "auto"})
    applied = casegen.applied_physics(scenario, BinGeometry())
    assert applied["emitting_area_m2"] > 0.0
    assert applied["emission_flux_kg_per_m2_s"]["CO"] > 0.0


def test_the_scalar_carries_turbulent_diffusivity(tmp_path, mesh):
    """The scalar must use D + nut/Sc_t, not molecular D alone.

    OpenFOAM's scalarTransport uses ``alphaD*nu + alphaDt*nut`` only when
    neither its ``D`` nor its ``nut`` entry is written: ``D`` forces the
    constant-molecular path, and ``nut`` makes it return ``nut`` alone. So the
    case writes ``alphaD``/``alphaDt`` and omits both.
    """
    case = write_case(
        Scenario(gas_sources={"CO": "auto"}), mesh, tmp_path / "case", geom=BinGeometry()
    )
    functions = (case / "system" / "functions").read_text()
    block = functions.split("COTransport\n")[1]
    assert "alphaD" in block
    assert "alphaDt" in block
    assert "\n    D " not in block
    assert "\n    nut " not in block


def test_the_source_wall_has_zero_turbulent_viscosity(tmp_path, mesh):
    """``scalarTransport`` uses ``D = alphaD*nu + alphaDt*nut`` at the face.

    A ``calculated`` nut on the solid source patch carries the first cell's
    value (~0.023) into the wall flux, inflating the imposed emission ~1789x
    (measured 2026-09-19). ``nut`` is physically zero at a solid wall, and only
    then does ``D_face == D_mol`` so ``gradient * D_mol`` is the flux the
    manifest claims.
    """
    case = write_case(
        Scenario(gas_sources={"CO": "auto"}), mesh, tmp_path / "case", geom=BinGeometry()
    )
    nut = (case / "0" / "nut").read_text()
    source = nut.split("source")[1].split("}")[0]
    assert "fixedValue" in source
    assert "uniform 0" in source
    assert "calculated" not in source
    # The bin walls keep their wall function.
    wall = nut.split("wallLeft")[1].split("}")[0]
    assert "nutkWallFunction" in wall


def test_the_schmidt_number_is_a_labelled_assumption():
    assert 0.5 <= casegen.TURBULENT_SCHMIDT_NUMBER <= 1.0
    assert casegen.TURBULENT_SCHMIDT_PROVENANCE == "model assumption"
    assert casegen.TURBULENT_SCHMIDT_BASIS


def test_each_gas_alphaD_restores_its_own_molecular_diffusivity(tmp_path, mesh):
    """``scalarTransport`` computes ``D = alphaD*nu + alphaDt*nut``.

    OpenFOAM's source (v2512) multiplies ``alphaD`` by the *kinematic
    viscosity*, not by a per-gas diffusivity, so a constant ``alphaD = 1``
    would carry every gas at ``nu_air`` and discard its own Fuller-Schettler-
    Giddings value. ``alphaD`` must therefore be ``D_gas / nu_air`` so that the
    molecular term is the gas's real diffusivity.
    """
    case = write_case(
        Scenario(gas_sources={"CO": "auto", "H2S": "auto"}),
        mesh,
        tmp_path / "case",
        geom=BinGeometry(),
    )
    functions = (case / "system" / "functions").read_text()
    for gas in ("CO", "H2S"):
        block = functions.split(f"{gas}Transport\n")[1].split("}")[0]
        written = float(re.search(r"alphaD\s+([0-9.eE+-]+)", block).group(1))
        # The case writes ``:g`` (6 significant figures); compare in that form.
        assert written == float(f"{scalar_diffusivity(gas) / casegen.NU_AIR:g}")
    # And the two gases genuinely differ, so a shared constant cannot pass.
    assert scalar_diffusivity("CO") != pytest.approx(scalar_diffusivity("H2S"))



def test_auto_sources_use_the_cited_ap42_defaults():
    scenario = Scenario(gas_sources={"CO": "auto", "H2S": "auto"})
    resolved = resolve_sources(scenario)
    assert resolved["CO"] == pytest.approx(105e-6)
    assert resolved["H2S"] == pytest.approx(36e-6)


def test_the_flux_is_the_rate_over_the_emitting_area():
    scenario = Scenario(
        gas_sources={"CH4": "auto"}, tonnage_t=10.0, age_h=24.0 * 365 * 3
    )
    geom = BinGeometry(width_m=2.0)
    rate = emission_rate_kg_per_s(scenario, "CH4")
    flux = emission_flux_kg_per_m2_s(scenario, geom, "CH4")
    assert rate > 0.0
    assert flux == pytest.approx(rate / emission_area_m2(geom))


def test_tonnage_scales_the_flux_and_age_changes_it():
    """The point of the rework: tonnage and age must move the CFD source.

    A first-order decay peaks at placement, so for a fixed batch the *rate* (and
    therefore the flux) is highest when the load is fresh and falls with age;
    the cumulative mass is what grows. Both are the same curve, which is what
    Phase 2 established.
    """
    geom = BinGeometry()
    light = Scenario(gas_sources={"CH4": "auto"}, tonnage_t=1.0, age_h=24.0 * 365 * 3)
    heavy = Scenario(gas_sources={"CH4": "auto"}, tonnage_t=10.0, age_h=24.0 * 365 * 3)
    assert emission_flux_kg_per_m2_s(heavy, geom, "CH4") == pytest.approx(
        10.0 * emission_flux_kg_per_m2_s(light, geom, "CH4")
    )

    fresh = Scenario(gas_sources={"CH4": "auto"}, tonnage_t=10.0, age_h=8.0)
    aged = Scenario(gas_sources={"CH4": "auto"}, tonnage_t=10.0, age_h=24.0 * 365 * 3)
    assert emission_flux_kg_per_m2_s(fresh, geom, "CH4") != pytest.approx(
        emission_flux_kg_per_m2_s(aged, geom, "CH4")
    )
    assert emission_flux_kg_per_m2_s(fresh, geom, "CH4") > emission_flux_kg_per_m2_s(
        aged, geom, "CH4"
    )


def test_a_wider_bin_dilutes_the_flux():
    scenario = Scenario(gas_sources={"CH4": "auto"}, tonnage_t=10.0, age_h=24.0 * 365 * 3)
    narrow = BinGeometry(width_m=1.0)
    wide = BinGeometry(width_m=4.0)
    assert emission_flux_kg_per_m2_s(scenario, wide, "CH4") == pytest.approx(
        emission_flux_kg_per_m2_s(scenario, narrow, "CH4") / 4.0
    )


def test_a_trace_gas_flux_scales_with_its_cited_share():
    """A trace gas carries its AP-42 volume share of the batch's gas molar rate."""
    scenario = Scenario(
        gas_sources={"CH4": "auto", "H2S": "auto"},
        tonnage_t=10.0,
        age_h=24.0 * 365 * 3,
    )
    geom = BinGeometry()
    h2s = emission_flux_kg_per_m2_s(scenario, geom, "H2S")
    assert h2s > 0.0
    # H2S's mass rate is its molar share (36 ppmv) of the bulk gas molar rate,
    # times its molecular weight. Doubling the batch doubles it.
    doubled = Scenario(
        gas_sources={"CH4": "auto", "H2S": "auto"},
        tonnage_t=20.0,
        age_h=24.0 * 365 * 3,
    )
    assert emission_rate_kg_per_s(doubled, "H2S") == pytest.approx(
        2.0 * emission_rate_kg_per_s(scenario, "H2S")
    )


def test_a_manual_source_overrides_the_generated_flux():
    auto = Scenario(gas_sources={"CO": "auto"})
    manual = Scenario(gas_sources={"CO": 50.0})
    geom = BinGeometry()
    assert emission_flux_kg_per_m2_s(auto, geom, "CO") != pytest.approx(
        emission_flux_kg_per_m2_s(manual, geom, "CO")
    )
    assert emission_flux_kg_per_m2_s(manual, geom, "CO") > 0.0


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


def test_scalar_field_imposes_the_source_flux(tmp_path, mesh):
    """The field's source patch carries a gradient, not a fixed concentration."""
    from scentinel.core.casegen import source_gradient

    scenario = Scenario(gas_sources={"CO": 105.0})
    geom = BinGeometry()
    case = write_case(scenario, mesh, tmp_path / "case", geom=geom)
    text = (case / "0" / "CO").read_text()
    assert "source" in text
    assert "fixedGradient" in text
    assert f"{source_gradient(scenario, geom, 'CO'):g}" in text


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

    # Each gas's own molecular diffusivity is still recorded, and now enters
    # the case through the alphaD*nu term of the turbulent scalar transport.
    functions = (case / "system" / "functions").read_text()
    for gas in ("CO", "VOC"):
        expected = gas_data.get_gas(gas).diffusivity_m2_s
        assert applied["scalar_diffusivity_m2_s"][gas] == pytest.approx(expected)
        assert f"{gas}Transport" in functions
        assert "alphaDt" in functions.split(f"{gas}Transport\n")[1]
    assert (
        applied["scalar_diffusivity_m2_s"]["CO"]
        != applied["scalar_diffusivity_m2_s"]["VOC"]
    )

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

    # A changed applied diffusivity, at identical UI inputs, changes the digest.
    monkeypatch.setattr(casegen, "scalar_diffusivity", lambda gas: 3.0e-05)
    changed = write_case(scenario, mesh, tmp_path / "changed", geom=geom)
    assert case_input_digest(changed, gases) != first


def test_each_gas_writes_its_own_diffusivity_into_the_case(tmp_path, mesh):
    """One scalarTransport object per gas, each with that gas's own D.

    This is the point of the change: a single hard-coded diffusivity made every
    species spread at the same rate regardless of molecular weight.
    """
    gases = ("CO", "ETHANE", "VOC", "BENZENE")
    scenario = Scenario(gas_sources={gas: "auto" for gas in gases})
    case = write_case(scenario, mesh, tmp_path / "case", geom=BinGeometry())

    functions = (case / "system" / "functions").read_text()
    for gas in gases:
        block = functions.split(f"{gas}Transport\n")[1]
        assert f"    field           {gas};\n" in block
        # The turbulent path carries the per-gas molecular diffusivity through
        # alphaD*nu; the case no longer writes a per-gas D (that would force
        # the molecular-only branch and ignore nut).
        assert "alphaDt" in block
        assert scalar_diffusivity(gas) == pytest.approx(
            gas_data.get_gas(gas).diffusivity_m2_s
        )

    # The molecular diffusivities still differ per gas; they now enter through
    # the alphaD*nu term rather than a written D.
    assert scalar_diffusivity("ETHANE") != scalar_diffusivity("BENZENE")
    assert applied_physics(scenario, BinGeometry())["scalar_diffusivity_m2_s"][
        "ETHANE"
    ] != applied_physics(scenario, BinGeometry())["scalar_diffusivity_m2_s"][
        "BENZENE"
    ]


def test_an_added_gas_resolves_and_writes_under_a_co_disposal_stream(tmp_path, mesh):
    """A gas AP-42 gives no co-disposal alternate for must still generate a case."""
    scenario = Scenario(
        waste_type="co-disposal", gas_sources={"ETHANE": "auto", "TOLUENE": "auto"}
    )
    case = write_case(scenario, mesh, tmp_path / "case", geom=BinGeometry())

    sources = resolve_sources(scenario)
    assert sources["ETHANE"] == pytest.approx(890e-6)
    assert sources["TOLUENE"] == pytest.approx(170e-6)
    # The field now carries the flux as a gradient; the resolved volume fraction
    # still drives it through the flux calculation.
    assert "fixedGradient" in (case / "0" / "ETHANE").read_text()
    assert "fixedGradient" in (case / "0" / "TOLUENE").read_text()


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
