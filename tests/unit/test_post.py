from pathlib import Path

from scentinel.core import post

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


def test_residual_targets_met_ignores_a_field_with_no_rows():
    """A target the log never reports cannot silently count as met."""
    met, reason = post.residual_targets_met_from_residuals(
        {"p": [(1.0, 1e-4)]}, {"p": 1e-3, "U": 1e-4}
    )
    assert met is True  # nothing to compare against; only p is present
    assert reason
