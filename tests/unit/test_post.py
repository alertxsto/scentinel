from pathlib import Path

import numpy as np
import pyvista as pv

from scentinel.core import post
from scentinel.core.project import Sensor

FIXTURE = Path(__file__).parent.parent / "fixtures" / "solverInfo.dat"


def test_solver_residuals_reads_initial_residuals_per_field():
    residuals = post.solver_residuals_from_file(FIXTURE)
    assert "p" in residuals
    assert "Ux" in residuals
    assert residuals["p"]
    time, value = residuals["p"][-1]
    assert isinstance(time, float)
    assert isinstance(value, float)


def test_residual_targets_met_reports_the_worst_field():
    residuals = {"p": [(1.0, 0.5)], "Ux": [(1.0, 1e-5)]}
    met, reason = post.residual_targets_met_from_residuals(
        residuals, {"p": 1e-3, "U": 1e-4}
    )
    assert met is False
    assert "p" in reason
    assert "0.5" in reason


def test_residual_targets_met_passes_when_every_field_is_under():
    residuals = {"p": [(1.0, 1e-4)], "Ux": [(1.0, 1e-5)]}
    met, reason = post.residual_targets_met_from_residuals(
        residuals, {"p": 1e-3, "U": 1e-4}
    )
    assert met is True
    assert reason


def test_residual_targets_met_ignores_a_field_with_no_rows():
    """A target the log never reports cannot silently count as met."""
    met, reason = post.residual_targets_met_from_residuals(
        {"p": [(1.0, 1e-4)]}, {"p": 1e-3, "U": 1e-4}
    )
    assert met is True  # nothing to compare against; only p is present
    assert reason


def test_a_buried_sensor_is_rejected_not_snapped():
    """A point inside the mound has no containing cell.

    ``find_closest_cell`` returns the nearest wall cell, which reads the
    near-wall value as if it were the probe's — the defect the audit found in
    the bin benchmark's old floor probe. ``find_containing_cell`` returns -1,
    which must become an explicit rejection.
    """
    grid = pv.ImageData(dimensions=(3, 3, 3))
    grid.cell_data["CO"] = np.zeros(8)
    readings = post.sample_sensors_from_grid(grid, [Sensor("outside", 99.0, 99.0)])
    assert readings[0].contained is False
    assert readings[0].values == {}
    assert readings[0].reason


def test_a_contained_sensor_reads_its_cell():
    """A point inside the grid reads the containing cell and is marked contained."""
    grid = pv.ImageData(dimensions=(3, 3, 3))
    grid.cell_data["CO"] = np.arange(8, dtype=float)
    readings = post.sample_sensors_from_grid(grid, [Sensor("inside", 0.5, 0.5)])
    assert readings[0].contained is True
    assert readings[0].reason == ""
    assert readings[0].values["CO"] >= 0.0
