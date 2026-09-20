"""Analytical benchmarks: does the solver reproduce a known closed-form answer?

``pytest -m verification``. Each test builds a minimal case whose exact solution
is known, solves it in the container, and compares the sampled field against the
closed form. A pass means the transport physics and the sampling path are
accurate; a failure localises the error to a specific term.

These are deliberately *not* the bin geometry: the bin case has no analytical
solution, so agreement there proves nothing. Each benchmark isolates one
mechanism.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from scentinel.core import casegen, post, runner

pytestmark = pytest.mark.verification


def _requires_solver() -> None:
    if not runner.podman_available():
        pytest.skip("podman unavailable")
    if not runner.image_available():
        pytest.skip(f"{casegen.IMAGE} not pulled")


def _write_minimal_case(
    case_dir: Path,
    *,
    inlet_value: float,
    end_time: int,
    diffusion: float,
    outlet_value: float | None = None,
) -> Path:
    """A 1D duct: inflow at x=0 with a fixed scalar, outflow at x=L.

    Written by hand rather than through ``casegen`` on purpose: the benchmark
    must not depend on the case generator it is meant to validate.

    ``outlet_value`` sets a fixed concentration at the outlet, which turns the
    duct into a through-flow diffusion cell. Left ``None`` the outlet is
    ``zeroGradient``, so nothing diffuses out and the exact solution is the
    inlet value everywhere.
    """
    case_dir = Path(case_dir)
    for relative in ("0", "constant", "system"):
        (case_dir / relative).mkdir(parents=True, exist_ok=True)

    length = 1.0
    height = 0.05
    (case_dir / "system" / "blockMeshDict").write_text(
        f"""FoamFile {{ version 2.0; format ascii; class dictionary; object blockMeshDict; }}
scale 1;
vertices
(
    (0 0 0) ({length} 0 0) ({length} {height} 0) (0 {height} 0)
    (0 0 0.01) ({length} 0 0.01) ({length} {height} 0.01) (0 {height} 0.01)
);
blocks ( hex (0 1 2 3 4 5 6 7) (100 1 1) simpleGrading (1 1 1) );
edges ();
boundary
(
    inlet  {{ type patch; faces ((0 4 7 3)); }}
    outlet {{ type patch; faces ((1 2 6 5)); }}
    walls  {{ type wall;  faces ((3 7 6 2) (0 1 5 4)); }}
    frontAndBack {{ type empty; faces ((0 3 2 1) (4 5 6 7)); }}
);
"""
    )
    (case_dir / "system" / "controlDict").write_text(
        f"""FoamFile {{ version 2.0; format ascii; class dictionary; object controlDict; }}
application     simpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {end_time};
deltaT          1;
writeInterval   {end_time};
purgeWrite      0;
writeFormat     ascii;
writePrecision  10;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;

functions
{{
    scalarTransport
    {{
        type            scalarTransport;
        libs            (solverFunctionObjects);
        field           C;
        diffusivity     constant;
        D               {diffusion};
        nCorr           1;
        resetOnStartup  false;
    }}
}}
"""
    )
    (case_dir / "system" / "fvSchemes").write_text(
        """FoamFile { version 2.0; format ascii; class dictionary; object fvSchemes; }
ddtSchemes      { default steadyState; }
gradSchemes     { default Gauss linear; }
divSchemes
{
    default         none;
    div(phi,U)      bounded Gauss linearUpwind grad(U);
    div(phi,C)      bounded Gauss limitedLinear 1;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes   { default corrected; }
wallDist        { method meshWave; }
"""
    )
    (case_dir / "system" / "fvSolution").write_text(
        """FoamFile { version 2.0; format ascii; class dictionary; object fvSolution; }
solvers
{
    p
    {
        solver          GAMG;
        tolerance       1e-9;
        relTol          0.01;
        smoother        GaussSeidel;
    }
    U
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-9;
        relTol          0.1;
    }
    C
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-12;
        relTol          0;
    }
}
SIMPLE
{
    nNonOrthogonalCorrectors 1;
    consistent      yes;
    residualControl
    {
        p               1e-4;
        U               1e-6;
        C               1e-10;
    }
}
relaxationFactors
{
    fields
    {
        p               0.3;
    }
    equations
    {
        U               0.7;
        C               0.9;
    }
}
"""
    )
    (case_dir / "constant" / "transportProperties").write_text(
        """FoamFile { version 2.0; format ascii; class dictionary; object transportProperties; }
transportModel  Newtonian;

nu              1e-05;
"""
    )
    (case_dir / "constant" / "turbulenceProperties").write_text(
        """FoamFile { version 2.0; format ascii; class dictionary; object turbulenceProperties; }
simulationType  laminar;
"""
    )
    for field, field_class, body in (
        (
            "U",
            "volVectorField",
            """dimensions [0 1 -1 0 0 0 0];
internalField uniform (1 0 0);
boundaryField
{
    inlet  { type fixedValue; value uniform (1 0 0); }
    outlet { type zeroGradient; }
    walls  { type noSlip; }
    frontAndBack { type empty; }
}""",
        ),
        (
            "p",
            "volScalarField",
            """dimensions [0 2 -2 0 0 0 0];
internalField uniform 0;
boundaryField
{
    inlet  { type zeroGradient; }
    outlet { type fixedValue; value uniform 0; }
    walls  { type zeroGradient; }
    frontAndBack { type empty; }
}""",
        ),
        (
            "C",
            "volScalarField",
            f"""dimensions [0 0 0 0 0 0 0];
internalField uniform {inlet_value if outlet_value is None else 0};
boundaryField
{{
    inlet  {{ type fixedValue; value uniform {inlet_value}; }}
    outlet {{ {
        f"type fixedValue; value uniform {outlet_value};"
        if outlet_value is not None
        else "type zeroGradient;"
    } }}
    walls  {{ type zeroGradient; }}
    frontAndBack {{ type empty; }}
}}""",
        ),
    ):
        (case_dir / "0" / field).write_text(
            f"FoamFile {{ version 2.0; format ascii; class {field_class}; "
            f"object {field}; }}\n{body}\n"
        )
    return case_dir


def _solve(case_dir: Path, *, script: str = runner.BLOCKMESH_SCRIPT) -> None:
    result = runner.run_case(case_dir, script=script)
    assert result.ok, (
        f"benchmark solve failed at {result.failed_stage}:\n"
        + runner.stage_log(case_dir, result.failed_stage or "simpleFoam")[-3000:]
    )


def _profile(case_dir: Path, xs: list[float]) -> list[float]:
    """Sampled C at the given x positions on the duct centreline."""
    sensors = [
        type("S", (), {"sensor_id": f"x{x}", "x": x, "y": 0.025})() for x in xs
    ]
    readings = post.sample_sensors(case_dir, sensors)
    return [r.values["C"] for r in readings]


# -- 1. Pure advection: the exact answer is the inlet value -------------------


def test_uniform_advection_transports_the_inlet_value_without_decay(tmp_path):
    """Steady 1D advection with no diffusion must carry C=1 unchanged.

    This isolates the advection term and the sampling path. Any deviation is
    numerical diffusion from the discretisation, and it bounds how much the
    solver smears a plume even before geometry is involved.
    """
    _requires_solver()
    case = _write_minimal_case(
        tmp_path / "case", inlet_value=1.0, end_time=2000, diffusion=1e-12
    )
    _solve(case)

    xs = [0.05, 0.25, 0.5, 0.75, 0.95]
    values = _profile(case, xs)
    worst = max(abs(v - 1.0) for v in values)
    assert worst < 0.02, (
        f"pure advection should preserve C=1; worst error {worst:.4f} "
        f"at {dict(zip(xs, values))}"
    )


# -- 2. Diffusion against the exact solution ---------------------------------


def test_axial_diffusion_reproduces_the_exponential_profile(tmp_path):
    """Through-flow between two fixed concentrations has an exact exponential.

    With ``C(0)=1`` and ``C(L)=0`` the steady 1D advection-diffusion solution is

        ``C(x) = (exp(Pe) - exp(Pe*x/L)) / (exp(Pe) - 1)``

    where ``Pe = U*L/D``. A ``zeroGradient`` outlet would have no exact
    non-trivial solution (the profile is flat), so the benchmark fixes both
    ends. This exercises the diffusion term, which the advection test cannot.
    """
    _requires_solver()
    # Pe = U*L/D = 1/D. Pe must stay modest or the profile collapses into a
    # boundary layer thinner than the 100-cell mesh can resolve, and every
    # sample away from that layer reads the same value.
    diffusion = 0.2
    case = _write_minimal_case(
        tmp_path / "case",
        inlet_value=1.0,
        end_time=5000,
        diffusion=diffusion,
        outlet_value=0.0,
    )
    _solve(case)

    peclet = 1.0 / diffusion
    xs = [0.1, 0.3, 0.5, 0.7, 0.9]
    expected = [
        (math.exp(peclet) - math.exp(peclet * x)) / (math.exp(peclet) - 1.0)
        for x in xs
    ]
    values = _profile(case, xs)
    errors = [abs(v - e) for v, e in zip(values, expected)]
    worst = max(errors)
    # A first-order upwind scheme on 100 cells carries O(h) truncation error;
    # 8% bounds it while still catching a wrong diffusivity (which changes the
    # profile by hundreds of percent) or a mis-set boundary condition.
    assert worst < 0.08, (
        f"axial diffusion profile deviates by {worst:.4f}; "
        f"sampled={dict(zip(xs, values))} exact={dict(zip(xs, expected))}"
    )


# -- 3. The bin case: is the sampled value self-consistent? ------------------


def test_bin_probe_is_inside_the_source_bound_and_positive(tmp_path):
    """The bin case has no closed form, so only bounds can be asserted.

    A probe near the waste must read above zero, and every probe must read a
    finite, non-negative value. The old upper bound — "a probe cannot exceed the
    source concentration" — no longer holds: the source is now a mass flux
    (``fixedGradient``), not a fixed surface concentration, so the near-wall
    value is set by the flux and the diffusion balance rather than capped at the
    nominal ppmv. A wrong sign, a broken patch, or a sampling bug still shows up
    as a negative or absurd value.
    """
    _requires_solver()
    from scentinel.core.geometry import BinGeometry
    from scentinel.core.mesh import generate_mesh
    from scentinel.core.project import Sensor
    from scentinel.core.scenario import Scenario

    geom = BinGeometry(
        length_m=6.0, height_m=2.5, mound_shape="mounded", mound_fill_fraction=0.45
    )
    mesh = generate_mesh(geom, 0.25, tmp_path / "mesh")
    scenario = Scenario(wind_speed_m_s=2.0, gas_sources={"CO": "auto"})
    case = casegen.write_case(
        scenario, mesh, tmp_path / "case", geom=geom, end_time=300
    )
    _solve(case, script=runner.SOLVER_SCRIPT)

    sensors = [Sensor("near", 3.0, 2.6), Sensor("far", 5.5, 2.6), Sensor("floor", 0.5, 1.5)]
    readings = post.sample_sensors(case, sensors)
    for reading in readings:
        value = reading.values["CO"]
        assert value >= 0.0, f"{reading.sensor_id} read a negative {value}"
    assert readings[0].values["CO"] > 0.0, "a probe above the mound must see some gas"
