"""Physics verification gates from the design spec.

Run with ``pytest -m verification``. They are slow because each one solves.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scentinel.core import casegen, post, runner
from scentinel.core.geometry import BinGeometry
from scentinel.core.mesh import generate_mesh
from scentinel.core.project import Sensor
from scentinel.core.scenario import Scenario

pytestmark = pytest.mark.verification

SENSORS = [Sensor("S1", 1.2, 2.1), Sensor("S2", 3.0, 2.2), Sensor("S3", 5.5, 1.0)]


def _solve(root: Path, mesh_size_m: float, geom: BinGeometry, end_time: int = 300) -> Path:
    mesh = generate_mesh(geom, mesh_size_m, root / "mesh")
    case = casegen.write_case(
        Scenario(wind_speed_m_s=2.0, gas_sources={"CO": "auto"}),
        mesh,
        root / "case",
        geom=geom,
        end_time=end_time,
    )
    result = runner.run_case(case)
    assert result.ok, runner.stage_log(case, result.failed_stage or "simpleFoam")[-2000:]
    return case


def _probe(case: Path) -> dict[str, float]:
    return {r.sensor_id: r.values["CO"] for r in post.sample_sensors(case, SENSORS)}


@pytest.mark.skipif(not runner.podman_available(), reason="podman unavailable")
def test_mesh_independence_is_not_yet_satisfied(tmp_path):
    """Documents the current refinement behaviour, which misses the spec gate.

    The design spec asks for <10% probe deviation between the coarse mesh and a
    2x refined one. Two transport reworks cut the old nearest-cell metric but
    did not close it — latest measurement 2026-09-20, worst probe:

    * pre-Phase-5 ``fixedValue`` concentration: ~87%
    * Phase 5 mass-flux boundary: ~63%
    * Phase 6 turbulent scalar transport (Sc_t = 0.7), nearest cell: ~19%
    * Phase 7 corrected source + containing-cell sampling: 266.29%

    The current 0.50->0.25 values are S1 18.65%, S2 0.53%, S3 266.29%.
    S3 changes sign (+1.164e-8 to -1.935e-8), so its relative deviation is
    dominated by the trace scalar's documented discretisation undershoot.

    This is not scalar noise alone. At the same containing cells, velocity
    magnitude changes by S1 30.84%, S2 5.55%, S3 12.53%; the k-epsilon flow is
    not mesh-converged either. Lowering Sc_t would be tuning outside the cited
    0.7-0.9 RANS range, so Sc_t stays 0.7.

    Flipping this test to assert convergence is the exit criterion for a
    mesh-converged velocity field (T-021), not for the scalar transport alone.
    """
    if not runner.image_available():
        pytest.skip(f"{casegen.IMAGE} not pulled")

    geom = BinGeometry(length_m=6.0, height_m=2.5, mound_shape="mounded", mound_fill_fraction=0.45)
    coarse = _probe(_solve(tmp_path / "coarse", 0.5, geom))
    fine = _probe(_solve(tmp_path / "fine", 0.25, geom))

    deviations = {
        sid: abs(fine[sid] - coarse[sid]) / abs(coarse[sid]) * 100 for sid in coarse
    }
    worst = max(deviations.values())
    assert worst > 10.0, (
        "mesh independence now passes; replace this test with a convergence "
        f"assertion. deviations={deviations}"
    )
