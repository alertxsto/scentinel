from pathlib import Path

import numpy as np
import pytest
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


def test_residual_targets_met_does_not_count_an_unmatched_target_as_met():
    met, reason = post.residual_targets_met_from_residuals(
        {"p": [(1.0, 1e-4)]}, {"p": 1e-3, "U": 1e-4}
    )
    assert met is False
    assert "not compared" in reason
    assert "U" in reason


def test_residual_targets_met_rejects_an_empty_comparison():
    met, reason = post.residual_targets_met_from_residuals({}, {"p": 1e-3})
    assert met is False
    assert "not compared" in reason


def test_solver_residuals_picks_the_numerically_newest_time(tmp_path):
    for time in (0, 100, 900, 1000):
        directory = tmp_path / "postProcessing" / "solverInfo" / str(time)
        directory.mkdir(parents=True)
        (directory / "solverInfo.dat").write_text(
            "# Time Ux_initial Ux_final\n"
            f"1\t{time}.0\t0\n"
        )
    assert post.solver_residuals(tmp_path)["Ux"][-1] == (1.0, 1000.0)



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


def _write_patch_flux(root: Path, name: str, value: float) -> None:
    output = root / "postProcessing" / name / "0" / "surfaceFieldValue.dat"
    output.parent.mkdir(parents=True)
    output.write_text(f"# Region type : patch\n1\t{value}\n")


def test_mass_balance_error_compares_signed_outlet_flux_to_analytic_source(tmp_path):
    # The signed net boundary flux is -0.5 + 1.5 = the imposed source 1.0.
    _write_patch_flux(tmp_path, "outletFluxLeftCO", -0.5)
    _write_patch_flux(tmp_path, "outletFluxRightCO", 1.5)

    error = post.mass_balance_error(tmp_path, "CO", source_flux=1.0)

    assert abs(error) < 1e-9


def test_mass_balance_error_is_negative_when_the_outlet_loses_flux(tmp_path):
    _write_patch_flux(tmp_path, "outletFluxRightCO", 0.5)

    error = post.mass_balance_error(tmp_path, "CO", source_flux=1.0)

    assert error == pytest.approx(-0.5)


def test_patch_fluxes_reads_the_latest_row(tmp_path):
    output = (
        tmp_path
        / "postProcessing"
        / "outletFluxRightCO"
        / "0"
        / "surfaceFieldValue.dat"
    )
    output.parent.mkdir(parents=True)
    output.write_text("# Time weightedSum(phi)\n1\t0.25\n2\t0.75\n")

    assert post.patch_fluxes(tmp_path) == {"outletFluxRightCO": 0.75}
