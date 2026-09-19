"""OpenFOAM case generation: turn a scenario and a mesh into a runnable case.

Writes a complete case directory (``0/``, ``constant/``, ``system/``) for the
``incompressibleFluid`` solver module run by ``foamRun``, plus the mesh itself
and the patch-type dictionary that ``gmshToFoam`` needs.

Two details drive the layout:

* ``gmshToFoam`` writes every boundary as a plain ``patch``. Wall functions
  and the ``empty`` constraint therefore have to be applied afterwards with
  ``changeDictionary``, which reads ``system/changeDictionaryDict``.
* The waste surface is a concentration boundary (``fixedValue``) rather than a
  flux boundary: the source strength is specified as a surface concentration in
  ppmv, matching the AP-42 defaults.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from scentinel.core.gas_data import source_concentration
from scentinel.core.geometry import BinGeometry
from scentinel.core.mesh import MeshResult
from scentinel.core.scenario import Scenario

#: Container image used for the solver. Fully qualified: podman enforces
#: short-name resolution and refuses to guess a registry in a non-interactive
#: shell.
#:
#: This is an OpenCFD (ESI) build. Note that it does **not** ship ``foamRun``
#: or the ``incompressibleFluid`` solver module — those belong to the
#: OpenFOAM Foundation line. The ESI equivalent used here is ``simpleFoam``,
#: which is steady-state SIMPLE for incompressible turbulent flow.
IMAGE = "docker.io/opencfd/openfoam-default:2512"

#: Environment script that puts the OpenFOAM binaries on PATH. The image sets
#: no login profile for a non-interactive ``bash -lc``, so this must be sourced
#: explicitly.
FOAM_BASHRC = "/usr/lib/openfoam/openfoam2512/etc/bashrc"

#: Steady-state incompressible solver, as named in this distribution.
SOLVER = "simpleFoam"

#: Kinematic viscosity of air at 25 C [m^2/s].
NU_AIR = 1.5e-05

#: Reference wind height and roughness for the power-law profile [m].
WIND_REFERENCE_HEIGHT_M = 10.0

#: Patch roles. ``gmshToFoam`` names patches after the gmsh physical groups.
WALL_PATCHES = ("wallLeft", "wallRight")
OPEN_PATCHES = ("openLeft", "openRight")
ALL_PATCHES = ("source", "wallLeft", "wallRight", "openLeft", "openRight", "top", "frontAndBack")

#: PPM is converted to a volume fraction for the solver's dimensionless scalar.
PPM_SCALE = 1.0e-6


@dataclass(frozen=True)
class PatchRole:
    """How one mesh patch is treated by the solver."""

    name: str
    kind: str  # "inlet" | "outlet" | "wall" | "source" | "slip" | "empty"


def resolve_sources(scenario: Scenario) -> dict[str, float]:
    """Resolve ``"auto"`` gas entries against the cited AP-42 defaults.

    Returns volume fractions, which is the basis the scalar transport solves in.
    """
    resolved: dict[str, float] = {}
    for gas, value in scenario.gas_sources.items():
        if isinstance(value, str):
            if value != "auto":
                raise ValueError(f"gas source for {gas} must be a number or 'auto', got {value!r}")
            ppmv = source_concentration(gas)
        else:
            ppmv = float(value)
        resolved[gas] = ppmv * PPM_SCALE
    return resolved


def patch_roles(scenario: Scenario) -> dict[str, PatchRole]:
    """Assign a role to every patch for the given wind direction.

    The wind blows left to right when ``wind_sign`` is +1, so the upwind open
    side becomes the inlet and the downwind one the outlet.
    """
    roles = {
        "source": PatchRole("source", "source"),
        "top": PatchRole("top", "slip"),
        "frontAndBack": PatchRole("frontAndBack", "empty"),
    }
    left, right = OPEN_PATCHES
    if scenario.wind_sign >= 0.0:
        roles[left] = PatchRole(left, "inlet")
        roles[right] = PatchRole(right, "outlet")
    else:
        roles[left] = PatchRole(left, "outlet")
        roles[right] = PatchRole(right, "inlet")
    for name in WALL_PATCHES:
        roles[name] = PatchRole(name, "wall")
    return roles


def wind_speed_at(scenario: Scenario, height_m: float) -> float:
    """Scale the reported wind speed to the given height.

    AP-42 / meteorological wind speeds are quoted at 10 m; the bin sits much
    lower, where the boundary layer is slower. A 1/7 power law gives a
    defensible screening estimate, and vanishes at ground level.
    """
    if scenario.wind_speed_m_s <= 0.0 or height_m <= 0.0:
        return 0.0
    ratio = min(height_m, WIND_REFERENCE_HEIGHT_M) / WIND_REFERENCE_HEIGHT_M
    return scenario.wind_speed_m_s * ratio ** (1.0 / 7.0)


def write_case(
    scenario: Scenario,
    mesh: MeshResult,
    out_dir: Path,
    *,
    geom: BinGeometry | None = None,
    end_time: int = 2000,
) -> Path:
    """Write a complete, ready-to-run OpenFOAM case into ``out_dir``."""
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    for sub in ("0", "constant", "system"):
        (out_dir / sub).mkdir(parents=True)

    shutil.copy2(mesh.msh_path, out_dir / "case.msh")

    sources = resolve_sources(scenario)
    roles = patch_roles(scenario)
    missing = set(roles) - set(mesh.patches)
    if missing:
        raise ValueError(f"mesh is missing patches required by the case: {sorted(missing)}")

    reference_height = geom.height_m if geom is not None else 2.5
    inlet_speed = wind_speed_at(scenario, reference_height)

    _write(out_dir / "0" / "U", _field_u(roles, inlet_speed, scenario.wind_sign))
    _write(out_dir / "0" / "p", _field_p(roles))
    _write(out_dir / "0" / "k", _field_k(roles, inlet_speed))
    _write(out_dir / "0" / "epsilon", _field_epsilon(roles, inlet_speed))
    _write(out_dir / "0" / "nut", _field_nut(roles))
    for gas, fraction in sources.items():
        _write(out_dir / "0" / gas, _field_scalar(gas, roles, fraction))

    _write(out_dir / "constant" / "transportProperties", _physical_properties())
    _write(out_dir / "constant" / "turbulenceProperties", _momentum_transport())

    _write(out_dir / "system" / "controlDict", _control_dict(sources, end_time))
    _write(out_dir / "system" / "fvSchemes", _fv_schemes(sources))
    _write(out_dir / "system" / "fvSolution", _fv_solution(sources))
    _write(out_dir / "system" / "functions", _functions(sources))
    _write(out_dir / "system" / "changeDictionaryDict", _change_dictionary(roles))

    (out_dir / "case.json").write_text(
        json.dumps(
            {
                "sources_volume_fraction": sources,
                "inlet_speed_m_s": inlet_speed,
                "patch_roles": {name: role.kind for name, role in roles.items()},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return out_dir


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _header(cls: str, obj: str) -> str:
    return (
        "/*--------------------------------*- C++ -*----------------------------------*\\\n"
        "| =========                 |                                                 |\n"
        "| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |\n"
        "|  \\\\    /   O peration     | Website:  https://openfoam.org                  |\n"
        "|   \\\\  /    A nd           | Version:  13                                   |\n"
        "|    \\\\/     M anipulation  |                                                 |\n"
        "\\*---------------------------------------------------------------------------*/\n"
        "FoamFile\n"
        "{\n"
        "    format      ascii;\n"
        f"    class       {cls};\n"
        f"    object      {obj};\n"
        "}\n"
        "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n\n"
    )


def _field_u(roles: dict[str, PatchRole], inlet_speed: float, wind_sign: float) -> str:
    lines = [
        _header("volVectorField", "U"),
        "dimensions      [0 1 -1 0 0 0 0];\n",
        "internalField   uniform (0 0 0);\n",
        "boundaryField\n{\n",
    ]
    for name, role in roles.items():
        if role.kind == "inlet":
            lines.append(f"    {name}\n    {{\n        type            fixedValue;\n")
            lines.append(f"        value           uniform ({wind_sign * inlet_speed:g} 0 0);\n    }}\n")
        elif role.kind == "outlet":
            lines.append(f"    {name}\n    {{\n        type            zeroGradient;\n    }}\n")
        elif role.kind == "wall":
            lines.append(f"    {name}\n    {{\n        type            noSlip;\n    }}\n")
        elif role.kind == "source":
            lines.append(f"    {name}\n    {{\n        type            noSlip;\n    }}\n")
        elif role.kind == "slip":
            lines.append(f"    {name}\n    {{\n        type            slip;\n    }}\n")
        else:
            lines.append(f"    {name}\n    {{\n        type            empty;\n    }}\n")
    lines.append("}\n")
    return "".join(lines)


def _field_p(roles: dict[str, PatchRole]) -> str:
    lines = [
        _header("volScalarField", "p"),
        "dimensions      [0 2 -2 0 0 0 0];\n",
        "internalField   uniform 0;\n",
        "boundaryField\n{\n",
    ]
    for name, role in roles.items():
        if role.kind == "outlet":
            lines.append(f"    {name}\n    {{\n        type            fixedValue;\n        value           uniform 0;\n    }}\n")
        elif role.kind == "empty":
            lines.append(f"    {name}\n    {{\n        type            empty;\n    }}\n")
        else:
            lines.append(f"    {name}\n    {{\n        type            zeroGradient;\n    }}\n")
    lines.append("}\n")
    return "".join(lines)


def _turbulence_values(inlet_speed: float) -> tuple[float, float]:
    """Crude inlet turbulence: 5% intensity over a 0.1 m length scale."""
    intensity = 0.05
    k = 1.5 * (inlet_speed * intensity) ** 2
    epsilon = 0.09**0.75 * k**1.5 / 0.1 if k > 0 else 1e-6
    return max(k, 1e-6), max(epsilon, 1e-6)


def _field_k(roles: dict[str, PatchRole], inlet_speed: float) -> str:
    k, _ = _turbulence_values(inlet_speed)
    lines = [
        _header("volScalarField", "k"),
        "dimensions      [0 2 -2 0 0 0 0];\n",
        f"internalField   uniform {k:g};\n",
        "boundaryField\n{\n",
    ]
    for name, role in roles.items():
        if role.kind == "inlet":
            lines.append(f"    {name}\n    {{\n        type            fixedValue;\n        value           uniform {k:g};\n    }}\n")
        elif role.kind == "empty":
            lines.append(f"    {name}\n    {{\n        type            empty;\n    }}\n")
        elif role.kind == "wall":
            lines.append(f"    {name}\n    {{\n        type            kqRWallFunction;\n        value           uniform {k:g};\n    }}\n")
        else:
            # Outlet, source surface and the slip lid all let k pass through.
            lines.append(f"    {name}\n    {{\n        type            zeroGradient;\n    }}\n")
    lines.append("}\n")
    return "".join(lines)


def _field_epsilon(roles: dict[str, PatchRole], inlet_speed: float) -> str:
    _, epsilon = _turbulence_values(inlet_speed)
    lines = [
        _header("volScalarField", "epsilon"),
        "dimensions      [0 2 -3 0 0 0 0];\n",
        f"internalField   uniform {epsilon:g};\n",
        "boundaryField\n{\n",
    ]
    for name, role in roles.items():
        if role.kind == "inlet":
            lines.append(f"    {name}\n    {{\n        type            fixedValue;\n        value           uniform {epsilon:g};\n    }}\n")
        elif role.kind == "empty":
            lines.append(f"    {name}\n    {{\n        type            empty;\n    }}\n")
        elif role.kind == "wall":
            lines.append(f"    {name}\n    {{\n        type            epsilonWallFunction;\n        value           uniform {epsilon:g};\n    }}\n")
        else:
            lines.append(f"    {name}\n    {{\n        type            zeroGradient;\n    }}\n")
    lines.append("}\n")
    return "".join(lines)


def _field_nut(roles: dict[str, PatchRole]) -> str:
    """Turbulent viscosity: computed by the model, so only wall patches matter."""
    lines = [
        _header("volScalarField", "nut"),
        "dimensions      [0 2 -1 0 0 0 0];\n",
        "internalField   uniform 0;\n",
        "boundaryField\n{\n",
    ]
    for name, role in roles.items():
        if role.kind == "empty":
            lines.append(f"    {name}\n    {{\n        type            empty;\n    }}\n")
        elif role.kind == "wall":
            lines.append(f"    {name}\n    {{\n        type            nutkWallFunction;\n        value           uniform 0;\n    }}\n")
        else:
            lines.append(f"    {name}\n    {{\n        type            calculated;\n        value           uniform 0;\n    }}\n")
    lines.append("}\n")
    return "".join(lines)


def _field_scalar(gas: str, roles: dict[str, PatchRole], source_fraction: float) -> str:
    lines = [
        _header("volScalarField", gas),
        "dimensions      [0 0 0 0 0 0 0];\n",
        "internalField   uniform 0;\n",
        "boundaryField\n{\n",
    ]
    for name, role in roles.items():
        if role.kind == "source":
            lines.append(f"    {name}\n    {{\n        type            fixedValue;\n        value           uniform {source_fraction:g};\n    }}\n")
        elif role.kind == "inlet":
            lines.append(f"    {name}\n    {{\n        type            fixedValue;\n        value           uniform 0;\n    }}\n")
        elif role.kind == "empty":
            lines.append(f"    {name}\n    {{\n        type            empty;\n    }}\n")
        else:
            lines.append(f"    {name}\n    {{\n        type            zeroGradient;\n    }}\n")
    lines.append("}\n")
    return "".join(lines)


def _physical_properties() -> str:
    """Viscosity dictionary.

    The name is distribution-specific: ESI (openfoam.com) reads
    ``constant/transportProperties`` with ``transportModel``, while the
    Foundation line reads ``constant/physicalProperties`` with
    ``viscosityModel``.
    """
    return (
        _header("dictionary", "transportProperties")
        + f"transportModel  Newtonian;\n\nnu              {NU_AIR:g};\n"
    )


def _momentum_transport() -> str:
    """Turbulence dictionary, named as ESI expects it."""
    return (
        _header("dictionary", "turbulenceProperties")
        + "simulationType  RAS;\n\nRAS\n{\n    RASModel        kEpsilon;\n\n    turbulence      on;\n}\n"
    )


def _control_dict(sources: dict[str, float], end_time: int) -> str:
    return (
        _header("dictionary", "controlDict")
        + f"application     {SOLVER};\n\n"
        f"startFrom       startTime;\n\n"
        f"startTime       0;\n\n"
        f"stopAt          endTime;\n\n"
        f"endTime         {end_time};\n\n"
        f"deltaT          1;\n\n"
        f"writeControl    timeStep;\n\n"
        f"writeInterval   {max(end_time // 10, 1)};\n\n"
        f"purgeWrite      0;\n\n"
        f"writeFormat     ascii;\n\n"
        f"writePrecision  6;\n\n"
        f"writeCompression off;\n\n"
        f"timeFormat      general;\n\n"
        f"timePrecision   6;\n\n"
        f"runTimeModifiable true;\n\n"
        f"functions\n{{\n"
        f'    #include "functions"\n'
        f"}}\n"
    )


def _fv_schemes(sources: dict[str, float]) -> str:
    scalar_divs = "".join(
        f"    div(phi,{gas})    bounded Gauss limitedLinear 1;\n" for gas in sources
    )
    return (
        _header("dictionary", "fvSchemes")
        + "ddtSchemes\n{\n    default         steadyState;\n}\n\n"
        "gradSchemes\n{\n    default         Gauss linear;\n}\n\n"
        "divSchemes\n{\n"
        "    default         none;\n"
        "    div(phi,U)      bounded Gauss linearUpwind grad(U);\n"
        "    div(phi,k)      bounded Gauss limitedLinear 1;\n"
        "    div(phi,epsilon) bounded Gauss limitedLinear 1;\n"
        f"{scalar_divs}"
        "    div((nuEff*dev2(T(grad(U))))) Gauss linear;\n"
        "}\n\n"
        "laplacianSchemes\n{\n    default         Gauss linear corrected;\n}\n\n"
        "interpolationSchemes\n{\n    default         linear;\n}\n\n"
        "snGradSchemes\n{\n    default         corrected;\n}\n\n"
        "wallDist\n{\n    method meshWave;\n}\n"
    )


def _fv_solution(sources: dict[str, float]) -> str:
    gas_pattern = "|".join(sources) if sources else "none"
    return (
        _header("dictionary", "fvSolution")
        + "solvers\n{\n"
        "    p\n    {\n        solver          GAMG;\n        tolerance       1e-06;\n"
        "        relTol          0.1;\n        smoother        GaussSeidel;\n    }\n\n"
        "    pcorr\n    {\n        solver          GAMG;\n        tolerance       1e-06;\n"
        "        relTol          0;\n        smoother        GaussSeidel;\n    }\n\n"
        '    "(U|k|epsilon)"\n    {\n        solver          smoothSolver;\n'
        "        smoother        symGaussSeidel;\n        tolerance       1e-05;\n"
        "        relTol          0.1;\n    }\n\n"
        f'    "({gas_pattern})"\n    {{\n        solver          PBiCGStab;\n'
        "        preconditioner  DILU;\n        tolerance       1e-08;\n        relTol          0.1;\n    }\n}\n\n"
        "SIMPLE\n{\n    nNonOrthogonalCorrectors 0;\n    consistent      yes;\n\n"
        "    residualControl\n    {\n"
        "        p               1e-3;\n"
        "        U               1e-4;\n"
        '        "(k|epsilon)"   1e-4;\n'
        f'        "({gas_pattern})" 1e-5;\n'
        "    }\n}\n\n"
        "relaxationFactors\n{\n    equations\n    {\n"
        "        U               0.9;\n"
        '        ".*"            0.9;\n'
        "    }\n}\n"
    )


def _functions(sources: dict[str, float]) -> str:
    body = "".join(
        f"{gas}Transport\n{{\n"
        f"    type            scalarTransport;\n"
        f"    libs            (solverFunctionObjects);\n"
        f"    field           {gas};\n"
        f"    diffusivity     constant;\n"
        f"    D               2e-05;\n"
        f"    nCorr           1;\n"
        f"    resetOnStartup  false;\n"
        f"}}\n\n"
        for gas in sources
    )
    return (
        _header("dictionary", "functions")
        + "residuals\n{\n    type            residuals;\n"
        + "    libs            (utilityFunctionObjects);\n"
        + "    fields          (p U k epsilon"
        + "".join(f" {gas}" for gas in sources)
        + ");\n}\n\n"
        + body
    )


def _change_dictionary(roles: dict[str, PatchRole]) -> str:
    """Patch types for ``changeDictionary`` after ``gmshToFoam``.

    ``gmshToFoam`` creates every boundary as a generic ``patch``, which the
    wall functions reject and which cannot serve as an ``empty`` constraint.
    """
    body = "".join(
        f'    "{name}"\n    {{\n        type            {_poly_patch_type(role)};\n    }}\n'
        for name, role in roles.items()
    )
    return (
        _header("dictionary", "changeDictionaryDict")
        + "boundary\n{\n"
        + body
        + "}\n"
    )


def _poly_patch_type(role: PatchRole) -> str:
    """Poly-mesh patch type for ``changeDictionary``.

    The waste surface is a solid boundary, so it has to be a ``wall`` for the
    wall functions to attach to it; leaving it as a generic ``patch`` makes
    ``kqRWallFunction`` fail at run time.
    """
    if role.kind == "empty":
        return "empty"
    if role.kind in ("wall", "source"):
        return "wall"
    return "patch"
