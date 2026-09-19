"""OpenFOAM case generation: turn a scenario and a mesh into a runnable case.

Writes a complete case directory (``0/``, ``constant/``, ``system/``) for the
ESI ``simpleFoam`` solver, plus the mesh itself and the patch-type dictionary
that ``gmshToFoam`` needs.

Every constant this module applies — wind profile, viscosity, linear-solver
tolerances, SIMPLE residual targets, relaxation factors — is a named module
constant, and the case files are rendered *from* those constants. Per-gas
scalar diffusivity is the exception, and deliberately so: it is not one value
for the case but one per species, read from ``gas_data``'s FSG-computed table by
:func:`scalar_diffusivity`. `scentinel.core.history` persists the same constants,
so a manifest cannot claim a value the generated case does not use.

Two details drive the layout:

* ``gmshToFoam`` writes every boundary as a plain ``patch``. Wall functions
  and the ``empty`` constraint therefore have to be applied afterwards with
  ``changeDictionary``, which reads ``system/changeDictionaryDict``.
* The waste surface is a concentration boundary (``fixedValue``) rather than a
  flux boundary: the source strength is specified as a surface concentration in
  ppmv, matching the AP-42 defaults.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scentinel.core import gas_data
from scentinel.core.geometry import BinGeometry
from scentinel.core.scenario import Scenario, auto_concentration_ppmv

if TYPE_CHECKING:
    # Imported for annotations only. ``core.mesh`` imports ``gmsh``, which is
    # an optional (``cfd``) dependency, so a case writer must not drag it in:
    # ``core.history`` imports this module and the history read API has to work
    # on a machine without the mesher installed.
    from scentinel.core.mesh import MeshResult

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

#: Wind profile applied to the inlet boundary. The reported wind speed is
#: scaled from the reference height to the bin rim by a power law; both the
#: profile name and the exponent are persisted, because they change the applied
#: inlet velocity as much as the reported speed does.
WIND_PROFILE = "power-law"
WIND_PROFILE_EXPONENT = 1.0 / 7.0

#: Reference wind height for the power-law profile [m].
WIND_REFERENCE_HEIGHT_M = 10.0

#: Scalar diffusivity is **not** a module constant: it is read per gas from
#: :func:`scalar_diffusivity`, which returns ``gas_data``'s FSG-computed value for
#: that species. A light gas and a heavy one therefore spread at different rates,
#: and the manifest persists the same number that was written into the case.

#: Linear-solver settings written into ``system/fvSolution``. ``fields`` holds
#: the OpenFOAM key **exactly as it is emitted**, quotes included, so the
#: persisted settings can be compared byte-for-byte with the generated file.
#: The per-gas entry is appended by :func:`linear_solver_settings`.
LINEAR_SOLVER_SETTINGS = (
    {
        "fields": "p",
        "solver": "GAMG",
        "tolerance": 1e-06,
        "relTol": 0.1,
        "smoother": "GaussSeidel",
    },
    {
        "fields": "pcorr",
        "solver": "GAMG",
        "tolerance": 1e-06,
        "relTol": 0.0,
        "smoother": "GaussSeidel",
    },
    {
        "fields": '"(U|k|epsilon)"',
        "solver": "smoothSolver",
        "smoother": "symGaussSeidel",
        "tolerance": 1e-05,
        "relTol": 0.1,
    },
)

#: Settings for the per-gas scalar fields, appended to the solver dictionary.
SCALAR_SOLVER_SETTINGS = {
    "solver": "PBiCGStab",
    "preconditioner": "DILU",
    "tolerance": 1e-08,
    "relTol": 0.1,
}

#: SIMPLE residual targets actually written into ``residualControl``, keyed by
#: the emitted OpenFOAM pattern. Reaching ``endTime`` is not the same as
#: satisfying these; nothing in an ordinary run parses the achieved residuals,
#: so a manifest must not claim convergence.
SIMPLE_RESIDUAL_TARGETS = {"p": 1e-3, "U": 1e-4, '"(k|epsilon)"': 1e-4}
SCALAR_RESIDUAL_TARGET = 1e-5

#: Relaxation factors written into ``relaxationFactors``, keyed as emitted.
RELAXATION_FACTORS = {"U": 0.9, '".*"': 0.9}

#: Non-orthogonal correctors in the SIMPLE dictionary.
NON_ORTHOGONAL_CORRECTORS = 0

#: Patch roles. ``gmshToFoam`` names patches after the gmsh physical groups.
WALL_PATCHES = ("wallLeft", "wallRight")
OPEN_PATCHES = ("openLeft", "openRight")
ALL_PATCHES = ("source", "wallLeft", "wallRight", "openLeft", "openRight", "top", "frontAndBack")

#: PPM is converted to a volume fraction for the solver's dimensionless scalar.
PPM_SCALE = 1.0e-6

#: Files ``write_case`` writes into ``constant/`` and ``system/``.
CASE_STATIC_INPUTS = (
    "constant/transportProperties",
    "constant/turbulenceProperties",
    "system/controlDict",
    "system/fvSchemes",
    "system/fvSolution",
    "system/functions",
    "system/changeDictionaryDict",
)

#: Files ``write_case`` writes into ``0/`` that are not per-gas scalar fields.
CASE_FIXED_FIELD_INPUTS = ("0/U", "0/p", "0/k", "0/epsilon", "0/nut")

#: Files ``write_case`` writes beside those directories.
CASE_ROOT_INPUTS = ("case.msh", "case.json")


def case_input_paths(gases: Iterable[str]) -> list[str]:
    """Every file ``write_case`` generates, as relative POSIX paths, sorted.

    The set is declared rather than discovered by walking the directory,
    because the container writes *into* the same tree: ``constant/polyMesh``,
    ``VTK/``, ``postProcessing/``, and the per-stage ``log.*`` files are solver
    output. Walking would fold them into the digest, so an identical case would
    digest differently depending on whether it had been solved — and a run that
    failed before the solve could never match a run that succeeded.

    ``gases`` supplies the per-gas scalar field names.
    """
    paths = [
        *CASE_ROOT_INPUTS,
        *CASE_FIXED_FIELD_INPUTS,
        *(f"0/{gas}" for gas in gases),
        *CASE_STATIC_INPUTS,
    ]
    return sorted(set(paths))


def case_input_digest(case_dir: Path, gases: Iterable[str]) -> str:
    """SHA-256 over the generated case inputs, as ``"sha256:<hex>"``.

    Algorithm, fixed so two independent implementations agree:

    1. Take :func:`case_input_paths`, sorted by relative POSIX path.
    2. For each file, feed the digest the UTF-8 relative path, a ``NUL`` byte,
       the decimal file size in bytes, another ``NUL``, then the file bytes.
    3. Render the 32-byte digest as lowercase hex.

    The relative path and size are hashed alongside the bytes so that renaming
    or truncating a file changes the digest even when the remaining bytes do.
    Only declared inputs are read; see :func:`case_input_paths` for why solver
    output must stay out.

    This digest is the authoritative guard for "same applied experiment": a
    change to any generated input, at identical UI inputs, changes it. A
    missing declared input raises, because a digest over a partial case would
    silently understate what was applied.
    """
    digest = hashlib.sha256()
    case_dir = Path(case_dir)
    for relative in case_input_paths(gases):
        path = case_dir / relative
        try:
            data = path.read_bytes()
        except OSError as error:
            raise ValueError(f"case input {relative} is missing or unreadable: {error}") from error
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(data)).encode("ascii"))
        digest.update(b"\0")
        digest.update(data)
    return f"sha256:{digest.hexdigest()}"


def scalar_diffusivity(gas: str) -> float:
    """Diffusivity in air [m^2/s] applied to ``gas``'s scalar transport.

    Read from :func:`scentinel.core.gas_data.get_gas`, whose table is computed
    by the Fuller-Schettler-Giddings correlation at 25 C, 1 atm. This is the
    single source of the number: the case writer and :func:`applied_physics`
    both call it, so a manifest cannot claim a diffusivity the case did not use.
    """
    return gas_data.get_gas(gas).diffusivity_m2_s


def linear_solver_settings(sources: dict[str, float]) -> list[dict[str, object]]:
    """The ``solvers`` block as written, including the per-gas entry.

    ``fields`` is the emitted dictionary key; the scalar entry keeps the
    parenthesised, quoted form the case writer has always produced.
    """
    settings: list[dict[str, object]] = [dict(entry) for entry in LINEAR_SOLVER_SETTINGS]
    if sources:
        pattern = "|".join(sources)
        settings.append({"fields": f'"({pattern})"', **SCALAR_SOLVER_SETTINGS})
    return settings


def residual_targets(sources: dict[str, float]) -> dict[str, float]:
    """The ``residualControl`` targets as written, including the per-gas entry."""
    targets = dict(SIMPLE_RESIDUAL_TARGETS)
    if sources:
        targets[f'"({"|".join(sources)})"'] = SCALAR_RESIDUAL_TARGET
    return targets


@dataclass(frozen=True)
class PatchRole:
    """How one mesh patch is treated by the solver."""

    name: str
    kind: str  # "inlet" | "outlet" | "wall" | "source" | "slip" | "empty"


def resolve_sources(scenario: Scenario) -> dict[str, float]:
    """Resolve ``"auto"`` gas entries against the cited AP-42 defaults.

    Returns volume fractions, which is the basis the scalar transport solves in.
    ``auto`` uses the selected waste stream: MSW-only vs co-disposal regime,
    with an organic-fraction scale on CH₄/VOC/H₂S for MSW-only streams.
    """
    resolved: dict[str, float] = {}
    for gas, value in scenario.gas_sources.items():
        if isinstance(value, str):
            if value != "auto":
                raise ValueError(f"gas source for {gas} must be a number or 'auto', got {value!r}")
            ppmv = auto_concentration_ppmv(scenario, gas)
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
    return scenario.wind_speed_m_s * ratio ** WIND_PROFILE_EXPONENT


def write_case(
    scenario: Scenario,
    mesh: MeshResult,
    out_dir: Path,
    *,
    geom: BinGeometry,
    end_time: int = 2000,
) -> Path:
    """Write a complete, ready-to-run OpenFOAM case into ``out_dir``.

    ``geom`` is required: the inlet velocity is the reported wind speed scaled
    to the bin rim, so the case cannot be written without the height it is
    scaled to. An internal default here would let the case and the persisted
    ``applied_physics`` block describe different reference heights.
    """
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

    inlet_speed = wind_speed_at(scenario, geom.height_m)

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
                "applied_physics": applied_physics(scenario, geom),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return out_dir


def applied_physics(scenario: Scenario, geom: BinGeometry) -> dict[str, object]:
    """The numerical settings this case actually applies, as a JSON-able block.

    Every value is read from the same module constant the case writer renders
    into the OpenFOAM dictionaries, so persisting this block cannot claim a
    setting the generated case does not use. It carries no digest: that belongs
    to the run record and is computed from the written files.
    """
    sources = resolve_sources(scenario)
    return {
        "wind_speed_reported_m_s": scenario.wind_speed_m_s,
        "inlet_speed_at_rim_m_s": wind_speed_at(scenario, geom.height_m),
        "wind_profile": WIND_PROFILE,
        "wind_profile_exponent": WIND_PROFILE_EXPONENT,
        "wind_reference_height_m": WIND_REFERENCE_HEIGHT_M,
        "nu_m2_s": NU_AIR,
        "scalar_diffusivity_m2_s": {gas: scalar_diffusivity(gas) for gas in sources},
        "linear_solver_settings": linear_solver_settings(sources),
        "residual_targets": residual_targets(sources),
        "relaxation_factors": dict(RELAXATION_FACTORS),
        "non_orthogonal_correctors": NON_ORTHOGONAL_CORRECTORS,
    }


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
    blocks = []
    for entry in linear_solver_settings(sources):
        fields = str(entry["fields"])
        body = "".join(
            f"        {key:<15} {_foam_value(value)};\n"
            for key, value in entry.items()
            if key != "fields"
        )
        blocks.append(f"    {fields}\n    {{\n{body}    }}\n")

    # ``_residual_lines`` keeps the per-gas entry in its historical unpadded
    # form so this refactor leaves every generated byte unchanged.
    targets = _residual_lines(sources)
    relaxation = "".join(
        f"        {key:<16}{_foam_value(value)};\n"
        for key, value in RELAXATION_FACTORS.items()
    )
    return (
        _header("dictionary", "fvSolution")
        + "solvers\n{\n"
        + "\n".join(blocks)
        + "}\n\n"
        "SIMPLE\n{\n"
        f"    nNonOrthogonalCorrectors {NON_ORTHOGONAL_CORRECTORS};\n"
        "    consistent      yes;\n\n"
        "    residualControl\n    {\n"
        + targets
        + "    }\n}\n\n"
        "relaxationFactors\n{\n    equations\n    {\n"
        + relaxation
        + "    }\n}\n"
    )


def _residual_lines(sources: dict[str, float]) -> str:
    """``residualControl`` body: fixed targets padded, the gas entry as before."""
    lines = [
        f"        {key:<16}{_foam_value(value)};\n"
        for key, value in SIMPLE_RESIDUAL_TARGETS.items()
    ]
    if sources:
        pattern = "|".join(sources)
        lines.append(f'        "({pattern})" {_foam_value(SCALAR_RESIDUAL_TARGET)};\n')
    return "".join(lines)


def _foam_value(value: object) -> str:
    """Render a Python value the way the case dictionaries spell it.

    Floats use general form (``1e-06``, ``0.1``) and ints stay ints, so a
    constant and the file it produced are visibly the same value. The only
    cosmetic difference from the pre-constant writer is that a threshold such as
    ``1e-3`` now renders as ``0.001`` — the same number, parsed identically by
    OpenFOAM.
    """
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    return f"{float(value):g}"


def _functions(sources: dict[str, float]) -> str:
    body = "".join(
        f"{gas}Transport\n{{\n"
        f"    type            scalarTransport;\n"
        f"    libs            (solverFunctionObjects);\n"
        f"    field           {gas};\n"
        f"    diffusivity     constant;\n"
        f"    D               {scalar_diffusivity(gas):g};\n"
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
