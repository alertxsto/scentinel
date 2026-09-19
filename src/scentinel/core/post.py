"""Post-processing: read solver output and sample it at the sensor positions.

The solver writes a VTK tree per written time (``VTK/<case>_<time>/``), with the
cell data in ``internal.vtu``. Sensor values are read from the cell containing
each point, which is what a physical inlet samples: the concentration in the
air the sensor sits in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: Fields carried by every case but not concentrations. ``TimeValue`` is
#: metadata that foamToVTK attaches to the grid rather than a physical field.
NON_SCALAR_FIELDS = ("U", "p", "k", "epsilon", "nut", "phi", "TimeValue")

_TIME_DIR = re.compile(r"^\d+(?:\.\d+)?$")


@dataclass
class SensorReading:
    """One sensor and the fields sampled at its position."""

    sensor_id: str
    x: float
    y: float
    values: dict[str, float]


def time_directories(case_dir: Path) -> list[float]:
    """Numeric time directories present in the case, ascending."""
    times: list[float] = []
    for child in Path(case_dir).iterdir():
        if child.is_dir() and _TIME_DIR.match(child.name):
            times.append(float(child.name))
    return sorted(times)


def latest_time_dir(case_dir: Path) -> Path:
    """Highest-numbered time directory in the case."""
    times = time_directories(case_dir)
    if not times:
        raise FileNotFoundError(f"no time directories in {case_dir}")
    return Path(case_dir) / _format_time(times[-1])


def vtk_dir(case_dir: Path) -> Path:
    return Path(case_dir) / "VTK"


def internal_vtu(case_dir: Path, time: float | None = None) -> Path:
    """Path to the internal-field VTU for a time, defaulting to the latest."""
    case_dir = Path(case_dir)
    if time is None:
        time = time_directories(case_dir)[-1]
    candidate = vtk_dir(case_dir) / f"{case_dir.name}_{_format_time(time)}" / "internal.vtu"
    if not candidate.exists():
        available = sorted(p.name for p in vtk_dir(case_dir).glob("*_*") if p.is_dir())
        raise FileNotFoundError(
            f"{candidate} not found; VTK times available: {available or 'none'}"
        )
    return candidate


def _format_time(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _cell_scalars(grid) -> list[str]:
    """Scalar names held as cell data, excluding velocity and turbulence.

    ``array_names`` merges the cell and point arrays (foamToVTK writes both),
    so the cell dictionary is consulted directly.
    """
    return [
        name
        for name in grid.cell_data.keys()
        if name not in NON_SCALAR_FIELDS and grid.cell_data[name].ndim == 1
    ]


def concentration_fields(case_dir: Path, time: float | None = None) -> list[str]:
    """Names of the transported scalars in the written fields."""
    import pyvista as pv

    return _cell_scalars(pv.read(internal_vtu(case_dir, time)))


def sample_sensors(
    case_dir: Path,
    sensors: list,
    time: float | None = None,
) -> list[SensorReading]:
    """Sample every sensor against the cell that contains it.

    ``sensors`` needs ``sensor_id``, ``x`` and ``y`` attributes; the project's
    :class:`~scentinel.core.project.Sensor` satisfies that.

    The probe is placed on the mid-plane of the extruded slab, since the case
    is 2D and the sensors carry no depth.
    """
    import pyvista as pv

    case_dir = Path(case_dir)
    grid = pv.read(internal_vtu(case_dir, time))
    scalars = _cell_scalars(grid)
    depth = grid.center[2]

    readings: list[SensorReading] = []
    for sensor in sensors:
        cell = grid.find_closest_cell((sensor.x, sensor.y, depth))
        values: dict[str, float] = {}
        if cell >= 0:
            for name in scalars:
                values[name] = float(grid.cell_data[name][cell])
        readings.append(
            SensorReading(
                sensor_id=sensor.sensor_id,
                x=sensor.x,
                y=sensor.y,
                values=values,
            )
        )
    return readings


def mass_balance_error(
    case_dir: Path,
    gas: str,
    time: float | None = None,
) -> float:
    """Relative imbalance between scalar leaving the domain and the source.

    A converged steady case should balance: what the waste surface releases
    either leaves through the outlet or accumulates. Returns
    ``(out_flux - in_flux) / source_flux``, so 0 is perfect balance and 1 means
    nothing left the domain.

    Requires ``foamToVTK -surfaceFields`` output, which carries the face fluxes.
    """
    import pyvista as pv

    case_dir = Path(case_dir)
    if time is None:
        time = time_directories(case_dir)[-1]
    boundary_dir = vtk_dir(case_dir) / f"{case_dir.name}_{_format_time(time)}" / "boundary"
    if not boundary_dir.exists():
        raise FileNotFoundError(
            f"{boundary_dir} not found; re-run foamToVTK with -surfaceFields"
        )

    source_flux = 0.0
    outlet_flux = 0.0
    for patch_file in boundary_dir.glob("*.vtp"):
        patch = pv.read(patch_file)
        flux_name = f"phi_{gas}"
        if flux_name not in patch.array_names:
            continue
        flux = float((patch[flux_name] * patch.area()).sum())
        name = patch_file.stem
        if name.startswith("source"):
            source_flux += flux
        elif name.startswith(("openLeft", "openRight")):
            outlet_flux += flux

    if abs(source_flux) < 1e-30:
        raise ValueError(f"no source flux found for {gas} in {boundary_dir}")
    return (outlet_flux - source_flux) / abs(source_flux)
