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
    """One sensor and the fields sampled at its position.

    ``contained`` is False when the sensor position has no containing fluid
    cell (it is buried in the mound or outside the mesh); ``values`` is then
    empty and ``reason`` says why. A reading is never silently snapped to the
    nearest cell, which would report a wall value as the probe's own.
    """

    sensor_id: str
    x: float
    y: float
    values: dict[str, float]
    contained: bool = True
    reason: str = ""


@dataclass(frozen=True)
class FieldSummary:
    """Observable statistics and artifact path for one rendered gas field."""

    gas: str
    minimum_ppmv: float
    mean_ppmv: float
    maximum_ppmv: float
    hotspot_x_m: float
    hotspot_y_m: float
    image_path: Path


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
    return sample_sensors_from_grid(grid, sensors)


def sample_sensors_from_grid(grid, sensors: list) -> list[SensorReading]:
    """Sample sensors against a grid, rejecting any with no containing cell.

    ``find_containing_cell`` returns ``-1`` for a point outside the fluid (a
    sensor buried in the mound, or beyond the mesh). That is an explicit
    rejection, not a snap to the nearest wall cell: ``find_closest_cell`` would
    silently report a wall value as the probe's own. The probe depth is the
    grid's mid-plane, since the case is a 2D slab extruded one cell thick.
    """
    scalars = _cell_scalars(grid)
    depth = grid.center[2]

    readings: list[SensorReading] = []
    for sensor in sensors:
        cell = grid.find_containing_cell((sensor.x, sensor.y, depth))
        if cell < 0:
            readings.append(
                SensorReading(
                    sensor_id=sensor.sensor_id,
                    x=sensor.x,
                    y=sensor.y,
                    values={},
                    contained=False,
                    reason="the sensor position has no containing fluid cell",
                )
            )
            continue
        values = {name: float(grid.cell_data[name][cell]) for name in scalars}
        readings.append(
            SensorReading(
                sensor_id=sensor.sensor_id,
                x=sensor.x,
                y=sensor.y,
                values=values,
            )
        )
    return readings


def render_concentration_field(
    case_dir: Path,
    gas: str,
    image_path: Path,
    *,
    sensors: list | None = None,
    time: float | None = None,
) -> FieldSummary:
    """Render the real OpenFOAM cell field in the XY plane and return its statistics."""
    import numpy as np
    import pyvista as pv
    # Imported by name on purpose. ``pv.Plotter`` goes through pyvista's module
    # ``__getattr__``, which imports ``pyvista.plotting`` on first access; when
    # the solver thread is concurrently importing that submodule, the attribute
    # lookup can run against a partially initialised module and raise
    # ``AttributeError: module 'pyvista' has no attribute 'Plotter'``. A direct
    # submodule import is served from ``sys.modules`` and has no such window.
    from pyvista.plotting import Plotter

    grid = pv.read(internal_vtu(case_dir, time))
    if gas not in _cell_scalars(grid):
        raise KeyError(f"{gas!r} is not a concentration field in {case_dir}")
    values_ppmv = np.asarray(grid.cell_data[gas], dtype=float) * 1.0e6
    display_name = f"{gas}_ppmv"
    grid.cell_data[display_name] = values_ppmv
    maximum_cell = int(values_ppmv.argmax())
    hotspot = grid.cell_centers().points[maximum_cell]

    image_path = Path(image_path)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    plotter = Plotter(off_screen=True, window_size=(1200, 700))
    plotter.set_background("white")
    plotter.add_mesh(
        grid,
        scalars=display_name,
        preference="cell",
        cmap="turbo",
        show_edges=True,
        edge_color="#d4d4d4",
        scalar_bar_args={"title": f"{gas} [ppmv]", "fmt": "%.3g"},
    )
    if sensors:
        depth = grid.center[2]
        points = np.array([(sensor.x, sensor.y, depth) for sensor in sensors])
        if len(points):
            plotter.add_points(
                points,
                color="#dc2626",
                point_size=14,
                render_points_as_spheres=True,
                label="Sensors",
            )
            plotter.add_point_labels(
                points,
                [sensor.sensor_id for sensor in sensors],
                text_color="#991b1b",
                font_size=10,
                shape_opacity=0.65,
                show_points=False,
            )
    plotter.add_point_labels(
        [hotspot],
        [f"Hotspot {float(values_ppmv[maximum_cell]):.4g} ppmv"],
        point_color="#7c2d12",
        text_color="#7c2d12",
        font_size=12,
        shape_opacity=0.75,
    )
    plotter.view_xy()
    plotter.camera.parallel_projection = True
    plotter.show(screenshot=str(image_path), auto_close=True)
    return FieldSummary(
        gas=gas,
        minimum_ppmv=float(values_ppmv.min()),
        mean_ppmv=float(values_ppmv.mean()),
        maximum_ppmv=float(values_ppmv.max()),
        hotspot_x_m=float(hotspot[0]),
        hotspot_y_m=float(hotspot[1]),
        image_path=image_path,
    )


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


def solver_residuals_from_file(path: Path) -> dict[str, list[tuple[float, float]]]:
    """Initial residuals per solver field, from a ``solverInfo.dat``.

    The header names the columns (``# Time  U_solver  Ux_initial  ...``); the
    first column is time and each ``<field>_initial`` column is that field's
    initial residual. Vector fields are reported per component (``Ux``,
    ``Uy``), so a caller matching the target ``U`` must accept the prefix.
    """
    text = Path(path).read_text()
    header: list[str] = []
    for line in text.splitlines():
        if line.startswith("#") and "Time" in line:
            header = line.lstrip("#").split()
            break
    if not header:
        raise ValueError(f"{path} has no solverInfo header")
    columns = {
        name.removesuffix("_initial"): index
        for index, name in enumerate(header)
        if name.endswith("_initial")
    }
    parsed: dict[str, list[tuple[float, float]]] = {name: [] for name in columns}
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cells = line.split()
        if len(cells) < len(header):
            continue
        time = float(cells[0])
        for name, index in columns.items():
            parsed[name].append((time, float(cells[index])))
    return parsed


def solver_residuals(case_dir: Path) -> dict[str, list[tuple[float, float]]]:
    """The newest ``solverInfo.dat`` under ``case_dir``, or ``{}`` when absent."""
    files = sorted(
        Path(case_dir).glob("postProcessing/solverInfo/*/solverInfo.dat")
    )
    return solver_residuals_from_file(files[-1]) if files else {}


def residual_targets_met_from_residuals(
    residuals: dict[str, list[tuple[float, float]]],
    targets: dict[str, float],
) -> tuple[bool, str]:
    """Compare each target's last initial residual against its ``fvSolution`` value.

    ``targets`` keys are the written field patterns: ``p``, ``U``, and the
    parenthesised ``"(k|epsilon)"``. A pattern matches a column when the column
    equals one of its names or starts with it (``U`` matches ``Ux``/``Uy``).
    A target with no matching column is not evidence of convergence, so it is
    skipped — the reason string says so when nothing was compared.
    """
    offenders: list[tuple[float, str, float, float]] = []
    compared = 0
    for pattern, target in targets.items():
        for name in pattern.strip('"()').split("|"):
            for field, series in residuals.items():
                if (field == name or field.startswith(name)) and series:
                    compared += 1
                    value = series[-1][1]
                    if value > target:
                        offenders.append((value / target, field, value, target))
    if not compared:
        return True, "no residual columns matched the targets; nothing to compare"
    if not offenders:
        return True, "every residual target met at the last iteration"
    _, field, value, target = max(offenders)
    return (
        False,
        f"{field} initial residual {value:.3g} exceeds its target {target:.3g}",
    )
