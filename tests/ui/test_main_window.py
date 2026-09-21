from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal

from scentinel.core import history
from scentinel.core.composition import WasteComposition
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
    # Select a gas explicitly and switch it off auto, so the round trip has to
    # carry an explicit value. The panel no longer preselects gases on load, so
    # the test states its own precondition instead of relying on a default.
    window.setup_panel()._gas_boxes["CO"].setChecked(True)
    window.setup_panel()._gas_auto["CO"].setChecked(False)
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
    # The default holding time is 8 h (aerobic), so methane is filtered out and
    # the explicit CO value plus the other headline gases round-trip.
    assert window.project().scenario.gas_sources == {
        "CO": 105.0, "VOC": "auto", "H2S": "auto",
    }
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
    # The RDF block reports the gas-phase loading it can actually compute and
    # names the fuel-basis gap rather than claiming a class it cannot derive.
    rdf_text = summary["rdf_suitability"].text()
    assert "mg/Nm³" in rdf_text
    assert "laboratory characterisation" in rdf_text
    assert "mg/Nm³" in summary["chlorine"].text()
    # 0.465 ppmv CO against the 35 ppmv NIOSH REL is well within limit.
    threshold_text = summary["threshold_assessment"].text()
    assert "CO" in threshold_text
    assert "within limit" in threshold_text
    assert summary["tvoc_concentration"].text() == "Requires sensor hardware and calibration"


def test_the_sensor_lab_receives_the_finished_run_readings(run_window, monkeypatch):
    """The lab is the device-model view of this run; it must see the run.

    ``_on_run_finished`` updated the results table but never pushed the new
    readings into the lab, so a replay kept using the lab fallback (or an older
    run's numbers) instead of the concentrations just solved.
    """
    monkeypatch.setattr(
        "scentinel.ui.solver_worker.SolverWorker._run_pipeline",
        lambda self: _success_outcome(self._run_dir),
    )
    lab = run_window.sensor_lab()
    lab.truth.setValue(999.0)

    assert run_window.start_run() is True

    truth, _cross, source = lab._exposure("S1")
    assert source == "cfd-co"
    assert truth == pytest.approx(0.465)


def test_the_lab_keeps_the_device_configuration_it_is_given(window):
    """``set_config`` -> ``config`` must round-trip every model parameter.

    The panel only carried the eight widgets it builds, so a project's
    ``sensitivity``, ``baseline_ppm``, and temperature/humidity coefficients
    were silently reset to their dataclass defaults on load, and the next edit
    wrote those defaults back into the project.
    """
    from scentinel.core.virtual_sensor import VirtualSensorConfig

    lab = window.sensor_lab()
    original = VirtualSensorConfig(
        family="MOX",
        range_ppm=500.0,
        detection_limit_ppm=0.2,
        response_time_s=12.0,
        recovery_time_s=30.0,
        sensitivity=2.0,
        cross_sensitivity=0.15,
        noise_ppm=0.5,
        drift_ppm_h=0.1,
        baseline_ppm=7.0,
        temperature_coefficient_per_c=0.03,
        humidity_coefficient_per_rh=0.02,
    )
    lab.set_config(original)

    restored = lab.config()
    assert restored.sensitivity == pytest.approx(original.sensitivity)
    assert restored.baseline_ppm == pytest.approx(original.baseline_ppm)
    assert restored.temperature_coefficient_per_c == pytest.approx(
        original.temperature_coefficient_per_c
    )
    assert restored.humidity_coefficient_per_rh == pytest.approx(
        original.humidity_coefficient_per_rh
    )


def test_the_target_gas_is_not_counted_as_its_own_interference(window):
    """A gas cannot interfere with the measurement of itself.

    When VOC is absent the lab promotes the first remaining gas to ground truth
    and then summed CH4/H2S/CO as cross-gas without excluding the promoted one,
    so with a non-zero cross-sensitivity the same CH4 counted twice.
    """
    from scentinel.core.post import SensorReading as RawReading
    from scentinel.core.virtual_sensor import VirtualSensorConfig

    window.viewport().add_sensor(3.0, 2.0)
    lab = window.sensor_lab()
    lab.set_config(VirtualSensorConfig(cross_sensitivity=1.0))
    lab.set_context(
        window.viewport().sensors(),
        [RawReading(sensor_id="S1", x=3.0, y=2.0, values={"CH4": 80.0})],
    )

    truth, cross, source = lab._exposure("S1")
    assert source == "cfd-ch4"
    assert truth == pytest.approx(80.0)
    assert cross == pytest.approx(0.0)


def test_the_batch_panel_edits_reach_the_scenario_the_run_uses(window):
    """The assessment and the run must describe the same waste.

    ``_on_batch_assessed`` used to only stash the assessment on the window, so a
    user could edit the fraction table, read a recommendation for it, and then
    run a simulation with the setup panel's unchanged preset.
    """
    from scentinel.core.composition import WasteComposition

    panel = window.batch_panel()
    panel._preset.setCurrentIndex(panel._preset.findData("green-waste"))
    # A hand-edited table that no preset describes.
    for widget in panel._fractions.values():
        widget.setValue(0.0)
    panel._fractions["paper"].setValue(0.7)
    panel._fractions["food"].setValue(0.3)
    panel._age_h.setValue(24.0 * 365 * 2)
    panel._moisture.setValue(0.25)
    panel._tonnage.setValue(6.0)

    scenario = window.project().scenario
    assert scenario.composition == WasteComposition(paper=0.7, food=0.3)
    assert scenario.age_h == pytest.approx(24.0 * 365 * 2)
    assert scenario.moisture_fraction == pytest.approx(0.25)
    assert scenario.tonnage_t == pytest.approx(6.0)


def test_a_successful_run_records_the_batch_that_was_assessed(run_window, tmp_path, monkeypatch):
    """The manifest must carry the composition, not just the stream label."""
    monkeypatch.setattr(
        "scentinel.ui.solver_worker.SolverWorker._run_pipeline",
        lambda self: _success_outcome(self._run_dir),
    )
    run_window.batch_panel()._tonnage.setValue(6.0)

    assert run_window.start_run() is True

    record = history.get_run(tmp_path / "runs", "run-001")
    assert record.project.scenario.tonnage_t == pytest.approx(6.0)
    assert record.project.scenario.composition["food"] > 0.0
    assert record.project.scenario.generation.phase in ("I", "II", "III", "IV")


def test_opening_a_project_loads_the_batch_panel(qapp, translator, tmp_path):
    """The batch editor must show the stored batch, not its widget defaults."""
    from scentinel.core.scenario import Scenario as Scn

    path = tmp_path / "batch.scentinel"
    save_project(
        Project(
            name="batch",
            geometry=BinGeometry(),
            scenario=Scn(
                gas_sources={"CO": 105.0},
                age_h=1000.0,
                moisture_fraction=0.2,
                tonnage_t=6.5,
                composition_fractions=WasteComposition(paper=0.7, food=0.3).as_dict(),
            ),
            sensors=[Sensor(sensor_id="S1", x=1.2, y=2.1)],
        ),
        path,
    )
    widget = MainWindow(translator, project=load_project(path), path=path)
    batch = widget.batch_panel()

    assert batch.tonnage_t() == pytest.approx(6.5)
    assert batch.age_h() == pytest.approx(1000.0)
    assert batch.moisture() == pytest.approx(0.2)
    assert batch.composition() == WasteComposition(paper=0.7, food=0.3)
    # And the loaded project was not rewritten by the panel's first recompute.
    assert widget.project().scenario.tonnage_t == pytest.approx(6.5)
    widget.deleteLater()


def test_a_setup_edit_does_not_erase_the_assessed_batch(window):
    """Both panels edit one project; a wind change must not drop the batch.

    ``_on_setup_changed`` replaces the whole scenario with the setup panel's
    fresh ``Scenario``, which knows nothing about the batch panel's fractions or
    tonnage. Without carrying those fields over, touching any setup field
    silently reset the assessed composition.
    """
    batch = window.batch_panel()
    for widget in batch._fractions.values():
        widget.setValue(0.0)
    batch._fractions["paper"].setValue(0.7)
    batch._fractions["food"].setValue(0.3)
    batch._tonnage.setValue(6.0)

    window.setup_panel()._wind_speed.setValue(3.5)

    scenario = window.project().scenario
    assert scenario.wind_speed_m_s == pytest.approx(3.5)
    assert scenario.tonnage_t == pytest.approx(6.0)
    assert scenario.composition == WasteComposition(paper=0.7, food=0.3)


def test_the_two_panels_show_the_same_holding_time_and_moisture(window):
    """The batch panel's age/moisture are mirrored into the setup form.

    Both panels carry the same two inputs. Leaving the setup widgets stale would
    let the next setup edit overwrite the values the assessment was made with.
    """
    batch = window.batch_panel()
    batch._age_h.setValue(500.0)
    batch._moisture.setValue(0.25)

    setup = window.setup_panel()
    assert setup._age_h.value() == pytest.approx(500.0)
    assert setup._moisture.value() == pytest.approx(0.25)

    # And the other way: a setup edit reaches the batch panel.
    setup._age_h.setValue(48.0)
    assert batch.age_h() == pytest.approx(48.0)


def test_choosing_a_stream_in_either_panel_selects_it_in_both(window):
    """The stream key drives the AP-42 regime, so the panels must agree.

    The batch panel used to leave the scenario's ``waste_type`` untouched: a run
    started from an edited batch could resolve its trace species under the setup
    panel's stream instead of the one the assessment named.
    """
    batch = window.batch_panel()
    setup = window.setup_panel()

    batch._preset.setCurrentIndex(batch._preset.findData("co-disposal"))
    assert window.project().scenario.waste_type == "co-disposal"
    assert setup._waste_type.currentData() == "co-disposal"

    setup._waste_type.setCurrentIndex(setup._waste_type.findData("rdf-feedstock"))
    assert window.project().scenario.waste_type == "rdf-feedstock"
    assert batch.preset_key() == "rdf-feedstock"


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


def test_a_rejected_probe_is_persisted_as_a_failed_run(run_window, tmp_path, monkeypatch):
    def rejected(self):
        return RunOutcome(
            case_dir=self._run_dir / "case",
            readings=[
                RawReading(
                    sensor_id="S1",
                    x=1.2,
                    y=2.1,
                    values={},
                    contained=False,
                    reason="the sensor position has no containing fluid cell",
                )
            ],
            mesh_cells=7248,
            element_types={"Hexahedron 8": 7248},
            exit_code=0,
        )

    monkeypatch.setattr(
        "scentinel.ui.solver_worker.SolverWorker._run_pipeline", rejected
    )

    assert run_window.start_run() is True

    record = history.get_run(tmp_path / "runs", "run-001")
    assert record.execution_status == "failed"
    assert record.results.sensor_readings == ()
    assert "S1" in record.execution.error
    assert "no containing fluid cell" in record.execution.error


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


def test_a_field_render_failure_still_finalizes_the_run(run_window, tmp_path, monkeypatch):
    """Rendering is a view of the run; a VTK failure must not lose the record.

    ``post.render_concentration_field`` reaches into VTK and a plotting backend.
    When that raised, the exception escaped ``_on_run_finished`` before
    ``_finalize_run``, leaving a `succeeded` solve recorded as `incomplete`.
    """
    monkeypatch.setattr(
        "scentinel.ui.solver_worker.SolverWorker._run_pipeline",
        lambda self: _success_outcome(self._run_dir),
    )

    def boom(*_args, **_kwargs):
        raise AttributeError("module 'pyvista' has no attribute 'Plotter'")

    monkeypatch.setattr("scentinel.ui.results_panel.ResultsPanel.set_field_case", boom)

    assert run_window.start_run() is True

    record = history.load_run(tmp_path / "runs" / "run-001")
    assert record.execution_status == "succeeded"
    assert record.results.sensor_readings[0].sensor_id == "S1"
    assert run_window._status_label.text() == run_window._t.t("status.done")
    log = run_window.results_panel()._log.toPlainText()
    assert "WARNING: field visual unavailable" in log


def test_finalize_run_records_the_parsed_convergence_state(run_window, tmp_path, monkeypatch):
    """_finalize_run reads solverInfo.dat and stores the residual verdict."""
    monkeypatch.setattr(
        "scentinel.ui.solver_worker.SolverWorker._run_pipeline",
        lambda self: _success_outcome(self._run_dir),
    )
    monkeypatch.setattr(
        "scentinel.ui.main_window.post.solver_residuals",
        lambda case_dir: {
            field: [(100.0, 0.5 if field == "p" else 1e-9)]
            for field in ("p", "Ux", "k", "epsilon", "CO")
        },
    )

    assert run_window.start_run() is True

    record = history.get_run(tmp_path / "runs", "run-001")
    assert record.quality.convergence == "residual_targets_not_met"
    assert "p initial residual" in record.quality.convergence_reason
    assert record.execution.solver_termination == "end_time_reached"


def test_finalize_run_records_met_targets_when_residuals_are_small(run_window, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scentinel.ui.solver_worker.SolverWorker._run_pipeline",
        lambda self: _success_outcome(self._run_dir),
    )
    monkeypatch.setattr(
        "scentinel.ui.main_window.post.solver_residuals",
        lambda case_dir: {
            field: [(100.0, 1e-9)]
            for field in ("p", "Ux", "k", "epsilon", "CO")
        },
    )

    assert run_window.start_run() is True

    record = history.get_run(tmp_path / "runs", "run-001")
    assert record.quality.convergence == "residual_targets_met"
    assert record.execution.solver_termination == "residual_targets_met"

def test_finalize_run_does_not_claim_convergence_from_an_empty_comparison(
    run_window, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "scentinel.ui.solver_worker.SolverWorker._run_pipeline",
        lambda self: _success_outcome(self._run_dir),
    )
    monkeypatch.setattr(
        "scentinel.ui.main_window.post.solver_residuals",
        lambda case_dir: {"p": [(100.0, 1e-12)]},
    )
    monkeypatch.setattr(
        "scentinel.ui.main_window.post.residual_targets_met_from_residuals",
        lambda residuals, targets: (False, "not compared: no residual columns matched U"),
    )
    assert run_window.start_run() is True
    record = history.get_run(tmp_path / "runs", "run-001")
    assert record.quality.convergence == "not_evaluated"
    assert record.execution.solver_termination != "residual_targets_met"


def test_finalize_run_uses_the_cases_own_residual_targets(
    run_window, tmp_path, monkeypatch
):
    captured = {}

    def fake_compare(residuals, targets):
        captured.update(targets)
        return True, "every residual target met at the last iteration"

    monkeypatch.setattr(
        "scentinel.ui.solver_worker.SolverWorker._run_pipeline",
        lambda self: _success_outcome(self._run_dir),
    )
    monkeypatch.setattr(
        "scentinel.ui.main_window.post.solver_residuals",
        lambda case_dir: {"p": [(1.0, 1e-12)]},
    )
    monkeypatch.setattr(
        "scentinel.ui.main_window.post.residual_targets_met_from_residuals",
        fake_compare,
    )
    assert run_window.start_run() is True
    assert captured["p"] == pytest.approx(1e-3)
    assert any(abs(value - 1e-5) < 1e-12 for value in captured.values())


def test_finalize_run_says_not_evaluated_when_solverinfo_is_absent(run_window, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scentinel.ui.solver_worker.SolverWorker._run_pipeline",
        lambda self: _success_outcome(self._run_dir),
    )
    monkeypatch.setattr(
        "scentinel.ui.main_window.post.solver_residuals", lambda case_dir: {}
    )

    assert run_window.start_run() is True

    record = history.get_run(tmp_path / "runs", "run-001")
    assert record.quality.convergence == "not_evaluated"
    assert "no solverInfo.dat" in record.quality.convergence_reason
