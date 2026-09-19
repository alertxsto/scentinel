from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal

from scentinel.core import history
from scentinel.core.geometry import BinGeometry
from scentinel.core.history import HistoryError
from scentinel.core.post import SensorReading as RawReading
from scentinel.core.project import Project, Sensor, load_project, save_project
from scentinel.core.scenario import Scenario
from scentinel.ui.main_window import MainWindow
from scentinel.ui.solver_worker import (
    DEFAULT_END_ITERATION,
    DEFAULT_MESH_SIZE_M,
    RunOutcome,
)


class _SynchronousThread(QObject):
    """Stand-in for ``SolverThread`` that runs the worker inline.

    Keeps the orchestration tests free of Qt threading and of the CFD pipeline:
    the point under test is the history boundary, not the event loop.
    """

    finished = Signal()

    def __init__(self, worker) -> None:
        super().__init__()
        self._worker = worker

    def start(self) -> None:
        self._worker.run()
        self.finished.emit()

    def isRunning(self) -> bool:  # noqa: N802 - mirrors QThread
        return False

    def cancel(self) -> None:
        self._worker.cancel()


def _runnable_project() -> Project:
    """A project that passes every ``start_run()`` precondition."""
    return Project(
        name="Example",
        geometry=BinGeometry(),
        scenario=Scenario(gas_sources={"CO": 105.0}),
        sensors=[Sensor(sensor_id="S1", x=1.2, y=2.1)],
    )


def _success_outcome(run_dir: Path) -> RunOutcome:
    """What a completed pipeline reports: raw volume fractions, not ppmv."""
    return RunOutcome(
        case_dir=run_dir / "case",
        readings=[RawReading(sensor_id="S1", x=1.2, y=2.1, values={"CO": 0.465e-6})],
        mesh_cells=7248,
        element_types={"Hexahedron 8": 7248},
        exit_code=0,
    )


@pytest.fixture
def window(qapp, translator):
    widget = MainWindow(translator)
    yield widget
    widget.deleteLater()


def test_window_starts_on_the_default_project(window):
    assert window.project().geometry == BinGeometry()
    assert window.viewport().sensors() == []
    assert not window.is_dirty()


def test_editing_geometry_marks_the_project_dirty(window):
    window.setup_panel()._length.setValue(9.0)
    assert window.is_dirty()
    assert window.project().geometry.length_m == pytest.approx(9.0)
    assert window.viewport().geometry().length_m == pytest.approx(9.0)


def test_placing_a_sensor_flows_into_the_project(window):
    window.viewport().add_sensor(3.0, 2.0)
    assert [sensor.sensor_id for sensor in window.project().sensors] == ["S1"]


def test_save_then_open_round_trips_through_the_window(window, tmp_path):
    window.setup_panel()._length.setValue(7.0)
    window.setup_panel()._gas_boxes["CO"].setChecked(True)
    window.setup_panel()._gas_spins["CO"].setValue(105.0)
    window.viewport().add_sensor(3.0, 2.0)

    path = tmp_path / "run.scentinel"
    assert window._write_project(path)
    assert not window.is_dirty()
    assert window.project_path() == path

    window._apply_project(Project())
    assert window.viewport().sensors() == []

    window.open_project(path)
    assert window.project().geometry.length_m == pytest.approx(7.0)
    assert window.project().scenario.gas_sources == {"CO": 105.0}
    assert [sensor.sensor_id for sensor in window.project().sensors] == ["S1"]
    assert not window.is_dirty()


def test_saved_file_is_reloadable_by_the_core_loader(window, tmp_path):
    window.viewport().add_sensor(2.0, 1.9)
    path = tmp_path / "round.scentinel"
    window._write_project(path)
    assert load_project(path).sensors[0].x == pytest.approx(2.0)


def test_opening_a_broken_file_leaves_the_project_untouched(window, tmp_path, monkeypatch):
    path = tmp_path / "broken.scentinel"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(
        "scentinel.ui.main_window.QMessageBox.warning", lambda *args, **kwargs: None
    )

    window.open_project(path)

    assert window.project().geometry == BinGeometry()
    assert window.project_path() is None


def test_language_switch_updates_the_menus(window):
    window._set_locale("id")
    assert window._file_menu.title() == "Berkas"
    assert window._action_save.text() == "Simpan Proyek"


def test_export_writes_the_current_readings(window, tmp_path):
    from scentinel.ui.results_panel import SensorReading

    window.results_panel().set_results(
        [SensorReading(sensor_id="S1", x=1.0, y=2.0, values={"CO": 12.5})]
    )
    target = window.results_panel().export_results_csv(tmp_path / "out.csv")

    text = Path(target).read_text()
    assert "sensor_id" in text
    assert "S1" in text
    assert "12.5" in text


def test_sensor_eviction_keeps_project_in_sync(window):
    window.viewport().add_sensor(3.0, 1.4)
    window.setup_panel()._fill.setValue(0.9)
    assert window.project().sensors == []


# -- run history orchestration ------------------------------------------------
#
# The worker/history boundary is exercised here; the CFD pipeline itself is
# covered by the integration tests and is stubbed out by _run_pipeline.


@pytest.fixture
def solver(monkeypatch):
    """Make the window believe the solver is available and run it synchronously."""
    monkeypatch.setattr("scentinel.ui.main_window._probe_solver", lambda: (True, ""))
    monkeypatch.setattr(
        "scentinel.ui.main_window.SolverThread", _SynchronousThread, raising=True
    )


@pytest.fixture
def run_window(qapp, translator, tmp_path, solver):
    """A window whose project is saved, so runs land in tmp_path/runs."""
    path = tmp_path / "Example.scentinel"
    widget = MainWindow(translator, _runnable_project(), path=path)
    yield widget
    widget.deleteLater()


def test_start_run_reserves_a_record_before_the_worker_is_constructed(
    run_window, tmp_path, monkeypatch
):
    seen: dict[str, object] = {}

    def pipeline(self):
        # The manifest must already exist: the reservation is the run identity.
        manifest = self._run_dir / history.MANIFEST_NAME
        seen["manifest_existed"] = manifest.is_file()
        seen["run_dir"] = self._run_dir
        seen["mesh_size_m"] = self._mesh_size_m
        seen["end_time"] = self._end_time
        seen["project"] = self._project
        return _success_outcome(self._run_dir)

    monkeypatch.setattr("scentinel.ui.solver_worker.SolverWorker._run_pipeline", pipeline)

    assert run_window.start_run() is True

    assert seen["manifest_existed"] is True
    assert seen["run_dir"] == tmp_path / "runs" / "run-001"
    assert seen["mesh_size_m"] == DEFAULT_MESH_SIZE_M
    assert seen["end_time"] == DEFAULT_END_ITERATION

    assert run_window.setup_panel().mesh_size_m() == DEFAULT_MESH_SIZE_M
    assert run_window.setup_panel().end_iteration() == DEFAULT_END_ITERATION

    # The manifest records the same explicit execution settings the worker got.
    record = history.get_run(tmp_path / "runs", "run-001")
    assert record.execution.mesh_size_m == seen["mesh_size_m"]
    assert record.execution.requested_end_iteration == seen["end_time"]

    # MB-3: the worker got a *copy*, not the live editor model.
    assert seen["project"] is not run_window.project()


def test_the_worker_receives_a_frozen_snapshot_that_mutation_cannot_reach(
    run_window, tmp_path, monkeypatch
):
    """MB-3: mutating the live project mid-run must not change what is sampled.

    The viewport is disabled while a run is in flight, but that is UX defence,
    not the correctness mechanism: the worker holds an independent copy, so a
    sensor added between reservation and sampling can neither move a probe nor
    invalidate the record.
    """
    seen: dict[str, object] = {}

    def pipeline(self):
        # Adversarially mutate the live model while the pipeline is "running".
        run_window.viewport().add_sensor(3.0, 2.0)
        seen["sensors_during_run"] = list(self._project.sensors)
        return _success_outcome(self._run_dir)

    monkeypatch.setattr("scentinel.ui.solver_worker.SolverWorker._run_pipeline", pipeline)

    assert run_window.start_run() is True

    # The live project gained a sensor; the worker's frozen copy did not.
    assert [s.sensor_id for s in run_window.project().sensors] == ["S1", "S2"]
    assert [s.sensor_id for s in seen["sensors_during_run"]] == ["S1"]

    # The record stores the frozen sensor set and its matching reading.
    record = history.get_run(tmp_path / "runs", "run-001")
    assert record.execution_status == "succeeded"
    assert [s.sensor_id for s in record.project.sensors] == ["S1"]
    assert [r.sensor_id for r in record.results.sensor_readings] == ["S1"]


def test_the_editing_surfaces_are_disabled_while_a_run_is_in_flight(
    run_window, tmp_path, monkeypatch
):
    seen: dict[str, object] = {}

    def pipeline(self):
        seen["viewport_enabled"] = run_window.viewport().isEnabled()
        seen["setup_enabled"] = run_window.setup_panel().isEnabled()
        return _success_outcome(self._run_dir)

    monkeypatch.setattr("scentinel.ui.solver_worker.SolverWorker._run_pipeline", pipeline)

    assert run_window.start_run() is True

    assert seen["viewport_enabled"] is False
    assert seen["setup_enabled"] is False
    # ... and restored afterwards.
    assert run_window.viewport().isEnabled() is True


def test_a_successful_run_finalizes_once_and_the_table_matches_the_manifest(
    run_window, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "scentinel.ui.solver_worker.SolverWorker._run_pipeline",
        lambda self: _success_outcome(self._run_dir),
    )

    assert run_window.start_run() is True

    record = history.get_run(tmp_path / "runs", "run-001")
    assert record.execution_status == "succeeded"
    assert record.finished_at_utc is not None

    displayed = run_window.results_panel().readings()
    assert [reading.sensor_id for reading in displayed] == ["S1"]
    # One conversion from volume fraction to ppmv, shared by table and manifest.
    assert displayed[0].values["CO"] == pytest.approx(0.465)
    assert record.results.sensor_readings[0].values_ppmv == displayed[0].values
    assert record.results.concentration_unit == "ppmv"

    summary = run_window.results_panel()._summary_fields
    assert summary["sensor_count"].text() == "1"
    assert summary["gases"].text() == "CO"
    assert "min 0.465" in summary["concentration_statistics"].text()
    assert "max 0.465 ppmv" in summary["concentration_statistics"].text()
    assert summary["peak_sensor"].text() == "CO: S1 (0.465 ppmv)"
    assert summary["rdf_suitability"].text() == "Requires laboratory characterisation data"
    assert summary["tvoc_concentration"].text() == "Requires sensor hardware and calibration"


def test_a_failed_run_is_finalized_as_failed(run_window, tmp_path, monkeypatch):
    def pipeline(self):
        return RunOutcome(
            case_dir=self._run_dir / "case",
            mesh_cells=7100,
            element_types={"Hexahedron 8": 7100},
            exit_code=1,
            failed_stage="solve",
            error="FOAM FATAL ERROR",
        )

    monkeypatch.setattr("scentinel.ui.solver_worker.SolverWorker._run_pipeline", pipeline)

    assert run_window.start_run() is True

    record = history.get_run(tmp_path / "runs", "run-001")
    assert record.execution_status == "failed"
    assert record.execution.failed_stage == "solve"
    assert record.results.sensor_readings == ()


def test_a_cancelled_run_is_finalized_as_cancelled(run_window, tmp_path, monkeypatch):
    def pipeline(self):
        return RunOutcome(mesh_cells=3444, exit_code=-2)

    monkeypatch.setattr("scentinel.ui.solver_worker.SolverWorker._run_pipeline", pipeline)

    assert run_window.start_run() is True

    record = history.get_run(tmp_path / "runs", "run-001")
    assert record.execution_status == "cancelled"
    assert record.execution.exit_code == -2
    assert record.finished_at_utc is not None


def test_run_ids_persist_across_a_restart(run_window, translator, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scentinel.ui.solver_worker.SolverWorker._run_pipeline",
        lambda self: _success_outcome(self._run_dir),
    )
    assert run_window.start_run() is True

    # A fresh window on the same project must not reuse run-001.
    reopened = MainWindow(translator, _runnable_project(), path=tmp_path / "Example.scentinel")
    try:
        assert reopened.start_run() is True
    finally:
        reopened.deleteLater()

    assert [record.run_id for record in history.list_runs(tmp_path / "runs")] == [
        "run-001",
        "run-002",
    ]


def test_a_persistence_failure_at_start_launches_no_worker(
    run_window, tmp_path, monkeypatch
):
    launched: list[bool] = []

    def boom(*_args, **_kwargs):
        raise HistoryError("manifest not writable")

    monkeypatch.setattr("scentinel.ui.main_window.history.begin_run", boom)
    monkeypatch.setattr(
        "scentinel.ui.solver_worker.SolverWorker._run_pipeline",
        lambda self: launched.append(True) or _success_outcome(self._run_dir),
    )

    assert run_window.start_run() is False
    assert launched == []
    assert run_window.results_panel().readings() == []
    assert run_window._status_label.text() == run_window._t.t("run.history_failed")
    assert not (tmp_path / "runs" / "run-001").exists()


def test_a_solve_without_readings_is_recorded_as_failed_not_a_success(
    run_window, tmp_path, monkeypatch
):
    """A clean exit with an empty table is not a successful empty result."""

    def pipeline(self):
        return RunOutcome(case_dir=self._run_dir / "case", mesh_cells=7248, exit_code=0)

    monkeypatch.setattr("scentinel.ui.solver_worker.SolverWorker._run_pipeline", pipeline)

    assert run_window.start_run() is True

    record = history.get_run(tmp_path / "runs", "run-001")
    assert record.execution_status == "failed"
    # The failure is auditable, not an opaque exit-0 record.
    assert record.execution.error == history.NO_READINGS_ERROR
    assert record.results.sensor_readings == ()
    assert run_window._status_label.text() == run_window._t.t("status.error")


def test_a_successful_run_still_reports_every_scientific_gate_as_not_passing(
    run_window, tmp_path, monkeypatch
):
    """MB-4: a green run must not be renderable as converged or verified."""
    monkeypatch.setattr(
        "scentinel.ui.solver_worker.SolverWorker._run_pipeline",
        lambda self: _success_outcome(self._run_dir),
    )

    assert run_window.start_run() is True

    record = history.get_run(tmp_path / "runs", "run-001")
    assert record.execution_status == "succeeded"
    assert record.quality.classification == "screening_estimate"
    assert record.quality.convergence == "not_evaluated"
    assert record.quality.mesh_independence == "not_run"
    assert record.quality.mass_balance == "not_run"
    assert record.quality.experimental_validation == "not_run"


def test_a_finalization_failure_keeps_the_results_but_reports_the_failure(
    run_window, tmp_path, monkeypatch
):
    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(
        "scentinel.ui.solver_worker.SolverWorker._run_pipeline",
        lambda self: _success_outcome(self._run_dir),
    )
    monkeypatch.setattr("scentinel.ui.main_window.history.finish_run", boom)

    assert run_window.start_run() is True

    # The solver outcome survives, but the run is not claimed as recorded.
    assert [reading.sensor_id for reading in run_window.results_panel().readings()] == ["S1"]
    assert run_window._status_label.text() == run_window._t.t("status.done_history_failed")
    assert history.load_run(tmp_path / "runs" / "run-001").execution_status == "incomplete"
