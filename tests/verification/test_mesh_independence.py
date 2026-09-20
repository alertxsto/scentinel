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
    2x refined one. Two reworks have cut it but not closed it — measured
    2026-09-19, worst probe:

    * pre-Phase-5 ``fixedValue`` concentration: ~87%
    * Phase 5 mass-flux boundary: ~63%
    * Phase 6 turbulent scalar transport (Sc_t = 0.7): ~19%

    It is still missed and the sequence is not monotone (0.50->0.25 worst 19.5%,
    0.25->0.125 worst 17.8%; S1 improves to 7.1% while S2 rises to 17.8%). More
    SIMPLE iterations do not change it (300 vs 1500: 19.4% vs 19.5%).

    Root cause, measured: the k-epsilon velocity field itself differs between
    meshes at the probes (S1: 0.236 vs 0.116 m/s) and is not mesh-converged at
    these cell counts. The scalar now follows it through D + nut/Sc_t, which is
    why the deviation fell sharply, but the velocity field is the remaining
    limit. Raising the turbulent dispersion (lower Sc_t) shrinks the deviation
    further but outside the cited 0.7-0.9 RANS range, which would be tuning to
    pass rather than physics; Sc_t is left at 0.7.

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
