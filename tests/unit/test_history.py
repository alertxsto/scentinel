from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scentinel import __version__
from scentinel.core import casegen, gas_data, history
from scentinel.core.geometry import BinGeometry
from scentinel.core.history import HistoryError
from scentinel.core.mesh import PATCHES
from scentinel.core.post import SensorReading
from scentinel.core.project import Project, Sensor
from scentinel.core.scenario import WASTE_SPECS, Scenario

STARTED = datetime(2026, 9, 19, 12, 34, 56, tzinfo=timezone.utc)
FINISHED = datetime(2026, 9, 19, 12, 36, 12, tzinfo=timezone.utc)


def _project(**overrides) -> Project:
    defaults = dict(
        name="Example",
        geometry=BinGeometry(
            length_m=6.0, height_m=2.5, mound_shape="mounded", mound_fill_fraction=0.45
        ),
        scenario=Scenario(
            wind_speed_m_s=2.0,
            wind_direction="left-to-right",
            ventilation_on=False,
            gas_sources={"CO": "auto"},
        ),
        sensors=[Sensor(sensor_id="S1", x=1.2, y=2.1)],
    )
    defaults.update(overrides)
    return Project(**defaults)


def _begin(tmp_path: Path, project: Project | None = None):
    return history.begin_run(
        tmp_path / "runs",
        project or _project(),
        mesh_size_m=0.25,
        end_iteration=500,
        started_at=STARTED,
    )


def _finish(record, **overrides):
    payload = dict(
        status="succeeded",
        case_dir=record.run_dir / "case",
        mesh_cells=7248,
        element_types={"Hexahedron 8": 7248},
        exit_code=0,
        failed_stage=None,
        error=None,
        readings_ppmv=[SensorReading(sensor_id="S1", x=1.2, y=2.1, values={"CO": 0.465})],
        finished_at=FINISHED,
    )
    payload.update(overrides)
    return history.finish_run(record, **payload)


def _manifest(record) -> dict:
    return json.loads((record.run_dir / history.MANIFEST_NAME).read_text(encoding="utf-8"))


def _rewrite(record, mutate) -> None:
    payload = _manifest(record)
    mutate(payload)
    (record.run_dir / history.MANIFEST_NAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


# 1 ---------------------------------------------------------------------------


def test_begin_run_reserves_run_001_and_round_trips_the_input_snapshot(tmp_path):
    project = _project()
    record = _begin(tmp_path, project)

    assert record.run_id == "run-001"
    assert record.execution_status == "incomplete"
    assert record.run_dir == tmp_path / "runs" / "run-001"
    assert (record.run_dir / history.MANIFEST_NAME).is_file()

    payload = _manifest(record)
    assert payload["format_version"] == 5
    assert payload["execution_status"] == "incomplete"
    assert payload["started_at_utc"] == "2026-09-19T12:34:56Z"
    assert payload["finished_at_utc"] is None
    assert payload["application"] == {"name": "scentinel", "version": __version__}

    geometry = payload["project"]["geometry"]
    assert geometry == {
        "length_m": 6.0,
        "height_m": 2.5,
        "mound_shape": "mounded",
        "mound_fill_fraction": 0.45,
    }
    scenario = payload["project"]["scenario"]
    assert scenario["wind_speed_m_s"] == 2.0
    assert scenario["wind_direction"] == "left-to-right"
    assert scenario["ventilation"] == {"requested_on": False, "modelled": False}
    assert scenario["waste_type"] == "mixed-msw"
    # The organic fraction is derived from the composition (degradable share),
    # not an independent input; the manifest records what the model used.
    assert scenario["organic_fraction"] == pytest.approx(
        WASTE_SPECS["mixed-msw"].composition.degradable_fraction()
    )
    assert scenario["moisture_fraction"] == pytest.approx(0.4)
    assert scenario["age_h"] == pytest.approx(8.0)
    assert scenario["tonnage_t"] == pytest.approx(10.0)
    assert payload["project"]["sensors"] == [{"sensor_id": "S1", "x_m": 1.2, "y_m": 2.1}]

    execution = payload["execution"]
    assert execution["mesh_size_m"] == 0.25
    assert execution["requested_end_iteration"] == 500
    assert execution["solver"] == casegen.SOLVER
    assert execution["container_image"] == casegen.IMAGE
    assert execution["case_dir"] is None
    assert execution["exit_code"] is None
    assert execution["solver_termination"] == "not_evaluated"

    assert payload["results"] == {"concentration_unit": "ppmv", "sensor_readings": []}
    assert payload["quality"]["classification"] == "screening_estimate"
    assert payload["quality"]["verification_metrics"] == []
    assert payload["quality"]["validation_metrics"] == []

    # The snapshot is a copy: editing the live project afterwards changes nothing.
    project.scenario.gas_sources["CO"] = 7.0
    assert history.load_run(record.run_dir) == record


def test_begin_run_does_not_mutate_the_project_scenario(tmp_path):
    project = _project(scenario=Scenario(gas_sources={"CO": "auto", "H2S": 36.0}))
    before = dict(project.scenario.gas_sources)
    _begin(tmp_path, project)
    assert project.scenario.gas_sources == before


def test_the_manifest_records_the_composition_and_its_derived_chemistry(tmp_path):
    """Version 4: a record must say which waste produced its concentrations.

    Version 3 stored the stream label and the age but not the fractions, so a
    user-edited composition could not be reconstructed from the manifest and a
    recommendation could not be tied to the run that produced it.
    """
    from scentinel.core.composition import WasteComposition

    composition = WasteComposition(
        food=0.5, garden=0.1, paper=0.1, wood=0.1, textile=0.1, diaper=0.05, inert=0.05
    )
    project = _project(
        scenario=Scenario(
            gas_sources={"CH4": "auto"},
            age_h=24.0 * 365 * 3,
            moisture_fraction=0.55,
            tonnage_t=7.5,
            composition_fractions=composition.as_dict(),
        )
    )
    record = _begin(tmp_path, project)
    payload = _manifest(record)

    scenario = payload["project"]["scenario"]
    assert scenario["tonnage_t"] == pytest.approx(7.5)
    fractions = scenario["composition"]
    assert fractions["food"] == pytest.approx(0.5)
    assert fractions["inert"] == pytest.approx(0.05)

    # The derived chemistry is persisted, so a reader does not have to re-run the
    # model to learn what the record actually solved.
    chemistry = scenario["generation"]
    assert chemistry["phase"] == "IV"
    assert chemistry["doc"] == pytest.approx(composition.weighted_doc())
    assert chemistry["k_per_year"] == pytest.approx(composition.weighted_decay(0.55))
    assert chemistry["methane_fraction"] == pytest.approx(0.5, abs=2e-3)
    assert chemistry["ch4_cumulative_kg"] > 0.0
    assert chemistry["ch4_rate_kg_per_h"] > 0.0

    # And it round-trips: load_run reconstructs the same typed record.
    assert history.load_run(record.run_dir).project.scenario.tonnage_t == pytest.approx(7.5)


def test_a_version_4_manifest_is_rejected_naming_both_versions(tmp_path):
    """A version 4 record cannot separate cumulative gas from the generation rate."""
    record = _begin(tmp_path)
    _rewrite(record, lambda payload: payload.__setitem__("format_version", 4))

    with pytest.raises(HistoryError, match="4"):
        history.load_run(record.run_dir)


# 2 ---------------------------------------------------------------------------


def test_restart_allocates_past_the_highest_existing_id(tmp_path):
    root = tmp_path / "runs"
    (root / "run-001").mkdir(parents=True)
    (root / "run-003").mkdir()

    record = history.begin_run(
        root, _project(), mesh_size_m=0.25, end_iteration=500, started_at=STARTED
    )

    assert record.run_id == "run-004"


# 3 ---------------------------------------------------------------------------


def test_a_matching_directory_without_a_manifest_is_never_reused(tmp_path):
    root = tmp_path / "runs"
    (root / "run-001").mkdir(parents=True)
    (root / "run-001" / "case").mkdir()

    record = history.begin_run(
        root, _project(), mesh_size_m=0.25, end_iteration=500, started_at=STARTED
    )

    assert record.run_id == "run-002"
    assert not (root / "run-001" / history.MANIFEST_NAME).exists()
    assert (root / "run-001" / "case").is_dir()


def test_unrelated_directory_names_are_ignored(tmp_path):
    root = tmp_path / "runs"
    (root / "notes").mkdir(parents=True)
    (root / "run-two").mkdir()
    (root / "run-2").mkdir()

    record = history.begin_run(
        root, _project(), mesh_size_m=0.25, end_iteration=500, started_at=STARTED
    )

    assert record.run_id == "run-001"


# 4 ---------------------------------------------------------------------------


def test_a_lost_allocation_race_retries_the_next_id(tmp_path, monkeypatch):
    root = tmp_path / "runs"
    (root / "run-001").mkdir(parents=True)

    # Simulate the race: the scan happened before another process claimed run-001.
    monkeypatch.setattr(history, "_next_index", lambda _root: 1)

    record = history.begin_run(
        root, _project(), mesh_size_m=0.25, end_iteration=500, started_at=STARTED
    )

    assert record.run_id == "run-002"
    assert not (root / "run-001" / history.MANIFEST_NAME).exists()


# 5 ---------------------------------------------------------------------------


def test_auto_and_manual_sources_keep_their_mode_and_provenance(tmp_path):
    project = _project(
        scenario=Scenario(
            gas_sources={"CO": "auto", "H2S": 36.0},
        )
    )
    record = _begin(tmp_path, project)

    sources = record.project.scenario.gas_sources
    assert list(sources) == ["CO", "H2S"]

    auto = sources["CO"]
    assert auto.mode == "auto"
    assert auto.requested_ppmv is None
    assert auto.resolved_ppmv == pytest.approx(105.0)
    assert auto.provenance == gas_data.citation("CO")
    assert "ppmv" in auto.provenance

    manual = sources["H2S"]
    assert manual.mode == "manual"
    assert manual.requested_ppmv == 36.0
    assert manual.resolved_ppmv == 36.0
    assert manual.provenance == "user input"

    assert _manifest(record)["project"]["scenario"]["gas_sources"]["CO"]["resolved_ppmv"] == 105.0


def test_a_generated_source_cites_the_model_that_produced_it(tmp_path):
    """A decomposition product must not be labelled with a static table value.

    The auto CH4 source is computed by the generation model (the regulation's
    F = 0.5 split, ~500 000 ppmv), but the manifest attached
    ``gas_data.citation("CH4")``, whose text still reads "500000 ppmv — EPA
    LMOP". The record then stated a value and a provenance that disagreed with
    each other.
    """
    project = _project(
        scenario=Scenario(
            waste_type="mixed-msw",
            age_h=24.0 * 365 * 3,
            moisture_fraction=0.4,
            gas_sources={"CH4": "auto"},
        )
    )
    record = _begin(tmp_path, project)

    source = record.project.scenario.gas_sources["CH4"]
    assert source.resolved_ppmv == pytest.approx(500_000.0, rel=2e-3)
    # The citation names the model and the resolved value; it cannot contradict
    # the number persisted beside it.
    assert "Equation HH-1" in source.provenance
    assert "F=0.5" in source.provenance
    # The provenance quotes the value it actually resolved, not a table number.
    assert f"{source.resolved_ppmv:.0f}" in source.provenance
    assert "550000" not in source.provenance


def test_an_unknown_auto_gas_aborts_without_reserving_a_directory(tmp_path):
    project = _project(scenario=Scenario(gas_sources={"NOX": "auto"}))

    with pytest.raises(KeyError):
        _begin(tmp_path, project)

    assert not (tmp_path / "runs" / "run-001").exists()


def test_a_manifest_that_cannot_be_written_removes_the_empty_reservation(tmp_path, monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(history, "_write_manifest", boom)

    with pytest.raises(OSError):
        _begin(tmp_path)

    assert not (tmp_path / "runs" / "run-001").exists()


# 6 ---------------------------------------------------------------------------


def test_finish_run_records_a_success(tmp_path):
    record = _begin(tmp_path)
    finished = _finish(record)

    assert finished.execution_status == "succeeded"
    assert finished.finished_at_utc == "2026-09-19T12:36:12Z"
    assert finished.execution.case_dir == "case"
    assert finished.execution.mesh_cells == 7248
    assert finished.execution.element_types == {"Hexahedron 8": 7248}
    assert finished.execution.exit_code == 0
    assert finished.execution.failed_stage is None
    assert finished.execution.error is None

    # Readings are taken as given: already ppmv, never converted a second time.
    reading = finished.results.sensor_readings[0]
    assert reading.sensor_id == "S1"
    assert reading.values_ppmv == {"CO": 0.465}
    assert finished.results.concentration_unit == "ppmv"

    assert history.load_run(record.run_dir) == finished


def test_finish_run_records_a_failure_with_the_metadata_it_has(tmp_path):
    record = _begin(tmp_path)
    finished = _finish(
        record,
        status="failed",
        case_dir=record.run_dir / "case",
        mesh_cells=7100,
        element_types={"Hexahedron 8": 7100},
        exit_code=1,
        failed_stage="solve",
        error="FOAM FATAL ERROR",
        readings_ppmv=[],
    )

    assert finished.execution_status == "failed"
    assert finished.execution.failed_stage == "solve"
    assert finished.execution.error == "FOAM FATAL ERROR"
    assert finished.execution.mesh_cells == 7100
    assert finished.results.sensor_readings == ()


def test_finish_run_records_a_cancellation_without_fabricating_outputs(tmp_path):
    record = _begin(tmp_path)
    finished = _finish(
        record,
        status="cancelled",
        case_dir=None,
        mesh_cells=3444,
        element_types={},
        exit_code=-2,
        failed_stage=None,
        error=None,
        readings_ppmv=[],
    )

    assert finished.execution_status == "cancelled"
    assert finished.execution.case_dir is None
    assert finished.execution.exit_code == -2
    assert finished.results.sensor_readings == ()


def test_finish_run_refuses_to_finalize_twice(tmp_path):
    record = _begin(tmp_path)
    _finish(record)

    with pytest.raises(HistoryError, match="already 'succeeded'"):
        _finish(record)


def test_finish_run_rejects_an_incomplete_status(tmp_path):
    record = _begin(tmp_path)

    with pytest.raises(HistoryError, match="terminal status"):
        _finish(record, status="incomplete")


def test_a_succeeded_status_requires_a_zero_exit_code(tmp_path):
    """The contract says succeeded means the pipeline exited 0.

    Nothing else in the module enforced that, so an API caller could persist a
    record that claims success while its own execution block says the solver
    died with exit 13.
    """
    record = _begin(tmp_path)

    with pytest.raises(HistoryError, match="exit code"):
        _finish(record, status="succeeded", exit_code=13, failed_stage="solver")


def test_a_succeeded_status_rejects_a_recorded_failure(tmp_path):
    record = _begin(tmp_path)

    with pytest.raises(HistoryError, match="error"):
        _finish(record, status="succeeded", exit_code=0, error="podman is not installed")


def test_load_run_rejects_a_success_with_a_nonzero_exit_code(tmp_path):
    """The same consistency rule must hold for a hand-edited manifest."""
    record = _begin(tmp_path)
    _finish(record)
    _rewrite(record, lambda payload: payload["execution"].update({"exit_code": 13}))

    with pytest.raises(HistoryError, match="exit code"):
        history.load_run(record.run_dir)


def test_a_success_with_sensors_but_no_readings_is_recorded_as_failed_with_a_reason(tmp_path):
    """A clean exit whose readings are missing is an auditable failure.

    The status flips to ``failed`` *and* the reason is persisted, so the record
    is not an opaque exit-0 failure that a reader has to reconstruct.
    """
    record = _begin(tmp_path)
    finished = _finish(record, readings_ppmv=[])

    assert finished.execution_status == "failed"
    assert finished.execution.exit_code == 0
    assert finished.execution.error == history.NO_READINGS_ERROR
    assert finished.results.sensor_readings == ()
    assert history.load_run(record.run_dir).execution.error == history.NO_READINGS_ERROR


def test_finish_run_accepts_a_project_without_sensors_and_no_readings(tmp_path):
    record = _begin(tmp_path, _project(sensors=[]))
    finished = _finish(record, readings_ppmv=[])

    assert finished.execution_status == "succeeded"
    assert finished.results.sensor_readings == ()


def test_an_absolute_case_dir_is_stored_relative_to_the_run(tmp_path):
    record = _begin(tmp_path)
    finished = _finish(record, case_dir=record.run_dir / "case")

    assert finished.execution.case_dir == "case"
    assert str(record.run_dir) not in (record.run_dir / history.MANIFEST_NAME).read_text()


def test_a_case_dir_outside_the_run_directory_is_rejected(tmp_path):
    record = _begin(tmp_path)

    with pytest.raises(HistoryError, match="not inside the run directory"):
        _finish(record, case_dir=tmp_path / "elsewhere" / "case")

    with pytest.raises(HistoryError, match="must not contain"):
        _finish(record, case_dir=Path("../case"))

    # The reservation is untouched by a rejected finalization.
    assert history.load_run(record.run_dir).execution_status == "incomplete"


# 7 ---------------------------------------------------------------------------


def test_list_runs_orders_numerically_and_get_run_looks_up_by_id(tmp_path):
    root = tmp_path / "runs"
    for _ in range(10):
        history.begin_run(root, _project(), mesh_size_m=0.25, end_iteration=500, started_at=STARTED)

    records = history.list_runs(root)
    assert [record.run_id for record in records] == [f"run-{index:03d}" for index in range(1, 11)]
    assert history.get_run(root, "run-010").run_id == "run-010"
    assert history.get_run(root, "run-002").run_dir.name == "run-002"


def test_list_runs_and_get_run_handle_a_missing_root(tmp_path):
    missing = tmp_path / "runs"
    assert history.list_runs(missing) == []
    assert history.get_run(missing, "run-001") is None


def test_get_run_returns_none_for_an_absent_id(tmp_path):
    _begin(tmp_path)
    assert history.get_run(tmp_path / "runs", "run-042") is None


def test_get_run_rejects_an_id_that_is_not_a_run_name(tmp_path):
    _begin(tmp_path)
    for bad in ("../run-001", "run-1", "run-", "run-001/../run-002", ""):
        with pytest.raises(HistoryError, match="invalid run id"):
            history.get_run(tmp_path / "runs", bad)


def test_list_runs_raises_on_the_first_invalid_manifest(tmp_path):
    root = tmp_path / "runs"
    _finish(_begin(tmp_path))
    second = history.begin_run(root, _project(), mesh_size_m=0.25, end_iteration=500, started_at=STARTED)
    (second.run_dir / history.MANIFEST_NAME).write_text("{not json", encoding="utf-8")

    with pytest.raises(HistoryError, match="not valid JSON"):
        history.list_runs(root)


# 8 ---------------------------------------------------------------------------


def test_an_unsupported_format_version_is_rejected(tmp_path):
    record = _begin(tmp_path)
    _rewrite(record, lambda payload: payload.__setitem__("format_version", 99))

    with pytest.raises(HistoryError, match="unsupported format_version 99"):
        history.load_run(record.run_dir)


def test_malformed_json_is_rejected(tmp_path):
    record = _begin(tmp_path)
    (record.run_dir / history.MANIFEST_NAME).write_text("{not json", encoding="utf-8")

    with pytest.raises(HistoryError, match="not valid JSON"):
        history.load_run(record.run_dir)


def test_a_missing_manifest_is_rejected(tmp_path):
    root = tmp_path / "runs"
    (root / "run-001").mkdir(parents=True)

    with pytest.raises(HistoryError, match="could not be read"):
        history.load_run(root / "run-001")


def test_an_invalid_execution_status_is_rejected(tmp_path):
    record = _begin(tmp_path)
    _rewrite(record, lambda payload: payload.__setitem__("execution_status", "ok"))

    with pytest.raises(HistoryError, match="execution_status 'ok'"):
        history.load_run(record.run_dir)


def test_a_run_id_that_does_not_match_its_directory_is_rejected(tmp_path):
    record = _begin(tmp_path)
    _rewrite(record, lambda payload: payload.__setitem__("run_id", "run-002"))

    with pytest.raises(HistoryError, match="does not match its directory"):
        history.load_run(record.run_dir)


def test_an_invalid_run_id_syntax_is_rejected(tmp_path):
    record = _begin(tmp_path)
    _rewrite(record, lambda payload: payload.__setitem__("run_id", "run-1"))

    with pytest.raises(HistoryError, match="three or more decimal digits"):
        history.load_run(record.run_dir)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_rejected(tmp_path, value):
    record = _begin(tmp_path)
    _rewrite(record, lambda payload: payload["execution"].__setitem__("mesh_size_m", value))

    with pytest.raises(HistoryError, match="must be finite"):
        history.load_run(record.run_dir)


def test_a_non_finite_reading_is_rejected(tmp_path):
    record = _begin(tmp_path)
    finished = _finish(record)
    _rewrite(
        finished,
        lambda payload: payload["results"]["sensor_readings"][0]["values_ppmv"].__setitem__(
            "CO", float("nan")
        ),
    )

    with pytest.raises(HistoryError, match="must be finite"):
        history.load_run(record.run_dir)


def test_missing_unit_bearing_fields_are_rejected(tmp_path):
    record = _begin(tmp_path)
    _rewrite(record, lambda payload: payload["execution"].pop("mesh_size_m"))

    with pytest.raises(HistoryError, match="missing mesh_size_m"):
        history.load_run(record.run_dir)


def test_an_absolute_case_path_in_a_manifest_is_rejected(tmp_path):
    record = _begin(tmp_path)
    _rewrite(
        record, lambda payload: payload["execution"].__setitem__("case_dir", "/home/someone/case")
    )

    with pytest.raises(HistoryError, match="relative path inside the run directory"):
        history.load_run(record.run_dir)


def test_an_escaping_case_path_in_a_manifest_is_rejected(tmp_path):
    record = _begin(tmp_path)
    _rewrite(record, lambda payload: payload["execution"].__setitem__("case_dir", "../case"))

    with pytest.raises(HistoryError, match="relative path inside the run directory"):
        history.load_run(record.run_dir)


def test_a_naive_timestamp_is_rejected_at_write_time(tmp_path):
    with pytest.raises(HistoryError, match="timezone-aware"):
        history.begin_run(
            tmp_path / "runs",
            _project(),
            mesh_size_m=0.25,
            end_iteration=500,
            started_at=datetime(2026, 9, 19, 12, 34, 56),
        )


def test_a_non_utc_timestamp_in_a_manifest_is_rejected(tmp_path):
    record = _begin(tmp_path)
    _rewrite(
        record, lambda payload: payload.__setitem__("started_at_utc", "2026-09-19T12:34:56+07:00")
    )

    with pytest.raises(HistoryError, match="ISO 8601 UTC timestamp"):
        history.load_run(record.run_dir)


def test_a_finished_manifest_must_carry_its_finish_time(tmp_path):
    record = _begin(tmp_path)
    _finish(record)
    _rewrite(record, lambda payload: payload.__setitem__("finished_at_utc", None))

    with pytest.raises(HistoryError, match="finished_at_utc is required"):
        history.load_run(record.run_dir)


def test_an_incomplete_manifest_must_not_carry_outcomes(tmp_path):
    record = _begin(tmp_path)
    _rewrite(record, lambda payload: payload["execution"].__setitem__("exit_code", 0))

    with pytest.raises(HistoryError, match="must not carry execution outcome fields"):
        history.load_run(record.run_dir)


def test_unknown_manifest_fields_are_rejected(tmp_path):
    record = _begin(tmp_path)
    _rewrite(record, lambda payload: payload.__setitem__("extra", 1))

    with pytest.raises(HistoryError, match="unknown fields extra"):
        history.load_run(record.run_dir)


def test_a_manual_source_cannot_be_recorded_with_a_fabricated_citation(tmp_path):
    record = _begin(tmp_path)
    _rewrite(
        record,
        lambda payload: payload["project"]["scenario"]["gas_sources"]["CO"].update(
            {"mode": "manual", "requested_ppmv": 105.0, "provenance": gas_data.citation("CO")}
        ),
    )

    with pytest.raises(HistoryError, match="provenance must be 'user input'"):
        history.load_run(record.run_dir)


def test_an_automatic_source_cannot_carry_a_requested_value(tmp_path):
    record = _begin(tmp_path)
    _rewrite(
        record,
        lambda payload: payload["project"]["scenario"]["gas_sources"]["CO"].__setitem__(
            "requested_ppmv", 105.0
        ),
    )

    with pytest.raises(HistoryError, match="requested_ppmv must be null"):
        history.load_run(record.run_dir)


# 9 ---------------------------------------------------------------------------


def test_a_failed_replacement_leaves_the_prior_incomplete_manifest_readable(tmp_path, monkeypatch):
    record = _begin(tmp_path)

    def boom(*_args, **_kwargs):
        raise OSError("interrupted")

    monkeypatch.setattr(history.os, "replace", boom)

    with pytest.raises(OSError):
        _finish(record)

    reloaded = history.load_run(record.run_dir)
    assert reloaded.execution_status == "incomplete"
    assert reloaded.finished_at_utc is None
    assert reloaded.results.sensor_readings == ()
    assert not (record.run_dir / f".{history.MANIFEST_NAME}.tmp").exists()


# 10 --------------------------------------------------------------------------


def test_verification_and_validation_metrics_stay_separate_and_empty(tmp_path):
    record = _begin(tmp_path)
    finished = _finish(record)

    payload = _manifest(finished)
    assert payload["quality"]["verification_metrics"] == []
    assert payload["quality"]["validation_metrics"] == []
    assert finished.quality.verification_metrics == ()
    assert finished.quality.validation_metrics == ()

    metrics = history.MetricRecord(
        name="mesh independence",
        value=0.765,
        unit="1",
        target="<0.10",
        status="failed",
        provenance="tests/verification/test_mesh_independence.py",
    )
    reloaded = history.load_run(record.run_dir)
    assert reloaded.quality.verification_metrics == ()
    assert reloaded.quality.validation_metrics == ()
    assert metrics.unit == "1"  # unit-bearing metric shape, not a pass


def test_quality_classification_cannot_be_promoted(tmp_path):
    record = _begin(tmp_path)
    _rewrite(record, lambda payload: payload["quality"].__setitem__("classification", "validated"))

    with pytest.raises(HistoryError, match="screening_estimate"):
        history.load_run(record.run_dir)


def test_the_manifest_ends_with_a_newline_and_has_no_nan_literals(tmp_path):
    record = _finish(_begin(tmp_path))
    text = (record.run_dir / history.MANIFEST_NAME).read_text(encoding="utf-8")

    assert text.endswith("\n")
    assert "NaN" not in text
    assert "Infinity" not in text


def test_load_run_rejects_a_directory_that_is_not_a_run(tmp_path):
    with pytest.raises(HistoryError, match="is not a run directory"):
        history.load_run(tmp_path / "nope")


# 11 -- applied physics (MB-1) -------------------------------------------------


def _write_case_into(record, project: Project | None = None) -> Path:
    """Write a real generated case into the run directory.

    Used to prove the digest is computed from the actual case files rather than
    from the requested inputs.
    """
    from scentinel.core.mesh import MeshResult

    project = project or _project()
    case_dir = record.run_dir / "case"
    msh = record.run_dir / "mesh.msh"
    msh.write_text("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n")
    mesh = MeshResult(msh_path=msh, patches={name: i for i, name in enumerate(PATCHES, 1)})
    casegen.write_case(
        project.scenario, mesh, case_dir, geom=project.geometry, end_time=500
    )
    return case_dir


def test_the_manifest_records_the_applied_experiment_not_only_the_request(tmp_path):
    """MB-1: requested wind speed and applied inlet speed are different numbers.

    The reported speed is scaled by the power-law profile before it reaches the
    inlet boundary, so persisting only the request would let two records with
    identical manifests describe different boundary conditions.
    """
    project = _project(
        geometry=BinGeometry(length_m=6.0, height_m=2.5),
        scenario=Scenario(wind_speed_m_s=2.0, gas_sources={"CO": "auto"}),
    )
    record = _begin(tmp_path, project)
    applied = record.applied_physics

    assert applied.wind_speed_reported_m_s == 2.0
    assert applied.inlet_speed_at_rim_m_s == pytest.approx(casegen.wind_speed_at(project.scenario, 2.5))
    assert applied.inlet_speed_at_rim_m_s != applied.wind_speed_reported_m_s
    assert applied.wind_profile == casegen.WIND_PROFILE
    assert applied.wind_profile_exponent == pytest.approx(casegen.WIND_PROFILE_EXPONENT)
    assert applied.wind_reference_height_m == casegen.WIND_REFERENCE_HEIGHT_M
    assert applied.nu_m2_s == casegen.NU_AIR

    # The case applies each gas's own diffusivity, so the persisted block must
    # carry the same per-gas value the case file renders — not one constant.
    assert applied.scalar_diffusivity_m2_s == {"CO": casegen.scalar_diffusivity("CO")}
    assert casegen.scalar_diffusivity("CO") != casegen.scalar_diffusivity("VOC")

    # An incomplete run has no case, so it cannot yet claim a digest.
    assert applied.case_input_digest is None


def test_the_case_digest_is_recorded_once_the_case_exists(tmp_path):
    record = _begin(tmp_path)
    case_dir = _write_case_into(record)
    finished = _finish(record, case_dir=case_dir)

    digest = finished.applied_physics.case_input_digest
    assert digest is not None and digest.startswith("sha256:")
    assert digest == casegen.case_input_digest(case_dir, ["CO"])
    assert _manifest(finished)["applied_physics"]["case_input_digest"] == digest


def test_an_incomplete_manifest_may_not_claim_a_case_digest(tmp_path):
    record = _begin(tmp_path)
    _rewrite(
        record,
        lambda payload: payload["applied_physics"].__setitem__(
            "case_input_digest", "sha256:" + "0" * 64
        ),
    )

    with pytest.raises(HistoryError, match="must not carry a case_input_digest"):
        history.load_run(record.run_dir)


def test_a_malformed_case_digest_is_rejected(tmp_path):
    record = _begin(tmp_path)
    _rewrite(
        record,
        lambda payload: payload["applied_physics"].__setitem__("case_input_digest", "deadbeef"),
    )

    with pytest.raises(HistoryError, match="must look like sha256"):
        history.load_run(record.run_dir)


def test_a_failed_run_without_a_case_records_no_digest(tmp_path):
    record = _begin(tmp_path)
    finished = _finish(record, status="failed", case_dir=None, exit_code=13, readings_ppmv=[])

    assert finished.applied_physics.case_input_digest is None


def test_a_partially_generated_case_records_no_digest(tmp_path):
    """A digest over a partial case would understate what was applied."""
    record = _begin(tmp_path)
    case_dir = record.run_dir / "case"
    (case_dir / "system").mkdir(parents=True)
    (case_dir / "system" / "controlDict").write_text("partial")

    finished = _finish(record, status="failed", case_dir=case_dir, exit_code=13, readings_ppmv=[])

    assert finished.applied_physics.case_input_digest is None


def test_the_case_digest_survives_solver_output_in_the_same_tree(tmp_path):
    """The container writes into the case tree; none of it may enter the digest.

    This is the reason the digest covers a *declared* input set rather than a
    directory walk. If solver output were included, an identical case would
    digest differently depending on whether it had been solved, and a run that
    failed before the solve could never match one that succeeded.
    """
    record = _begin(tmp_path)
    case_dir = _write_case_into(record)
    before = casegen.case_input_digest(case_dir, ["CO"])

    (case_dir / "constant" / "polyMesh").mkdir(parents=True)
    (case_dir / "constant" / "polyMesh" / "points").write_text("solver output")
    (case_dir / "VTK").mkdir()
    (case_dir / "VTK" / "internal.vtu").write_text("vtk")
    (case_dir / "log.simpleFoam").write_text("solver log")
    (case_dir / "500").mkdir()
    (case_dir / "500" / "CO").write_text("field output")

    assert casegen.case_input_digest(case_dir, ["CO"]) == before
    finished = _finish(record, case_dir=case_dir)
    assert finished.applied_physics.case_input_digest == before


def test_a_changed_applied_constant_changes_the_recorded_digest(tmp_path, monkeypatch):
    """Identical UI inputs plus a changed applied constant must not collide."""
    first = _begin(tmp_path)
    first_case = _write_case_into(first)
    first_done = _finish(first, case_dir=first_case)

    monkeypatch.setattr(casegen, "scalar_diffusivity", lambda gas: 3.0e-05)
    second = history.begin_run(
        tmp_path / "runs", _project(), mesh_size_m=0.25, end_iteration=500, started_at=STARTED
    )
    second_case = _write_case_into(second)
    second_done = _finish(second, case_dir=second_case)

    assert first_done.applied_physics.case_input_digest != second_done.applied_physics.case_input_digest


def test_missing_applied_physics_fields_are_rejected(tmp_path):
    record = _begin(tmp_path)
    _rewrite(record, lambda payload: payload["applied_physics"].pop("nu_m2_s"))

    with pytest.raises(HistoryError, match="missing nu_m2_s"):
        history.load_run(record.run_dir)


def test_the_requested_end_iteration_is_not_reported_as_achieved(tmp_path):
    """``endTime`` is a requested control index, never evidence of convergence."""
    finished = _finish(_begin(tmp_path))

    assert finished.execution.requested_end_iteration == 500
    assert finished.execution.solver_termination == "not_evaluated"
    assert finished.quality.convergence == "not_evaluated"


# 12 -- ventilation is a request, not modelled physics (MB-2) ------------------


def test_a_ventilation_request_is_preserved_but_recorded_as_unmodelled(tmp_path):
    """MB-2: the case ignores the flag, so no record may imply it was modelled."""
    project = _project(scenario=Scenario(ventilation_on=True, gas_sources={"CO": "auto"}))
    record = _begin(tmp_path, project)

    assert record.project.scenario.ventilation.requested_on is True
    assert record.project.scenario.ventilation.modelled is False
    assert _manifest(record)["project"]["scenario"]["ventilation"] == {
        "requested_on": True,
        "modelled": False,
    }


def test_ventilation_cannot_be_recorded_as_modelled(tmp_path):
    record = _begin(tmp_path)
    _rewrite(
        record,
        lambda payload: payload["project"]["scenario"]["ventilation"].__setitem__("modelled", True),
    )

    with pytest.raises(HistoryError, match="modelled must be false"):
        history.load_run(record.run_dir)


def test_ventilation_off_is_recorded_the_same_way(tmp_path):
    record = _begin(tmp_path, _project(scenario=Scenario(gas_sources={"CO": "auto"})))

    assert record.project.scenario.ventilation.requested_on is False
    assert record.project.scenario.ventilation.modelled is False


# 13 -- readings must match the frozen sensors (MB-3) --------------------------


def test_a_reading_for_a_different_sensor_is_rejected(tmp_path):
    """A record may not claim inputs for S1 while storing S2's result."""
    record = _begin(tmp_path)

    with pytest.raises(HistoryError, match=history.NO_READINGS_ERROR):
        _finish(record, readings_ppmv=[SensorReading(sensor_id="S2", x=1.2, y=2.1, values={"CO": 1.0})])

    assert history.load_run(record.run_dir).execution_status == "incomplete"


def test_a_reading_at_moved_coordinates_is_rejected(tmp_path):
    record = _begin(tmp_path)

    with pytest.raises(HistoryError, match="moved from"):
        _finish(record, readings_ppmv=[SensorReading(sensor_id="S1", x=4.0, y=1.0, values={"CO": 1.0})])


def test_a_reading_for_an_unselected_gas_is_rejected(tmp_path):
    record = _begin(tmp_path)

    with pytest.raises(HistoryError, match="carries gases"):
        _finish(record, readings_ppmv=[SensorReading(sensor_id="S1", x=1.2, y=2.1, values={"VOC": 1.0})])


def test_extra_readings_are_rejected(tmp_path):
    """More readings than frozen sensors is a mismatch, not a success."""
    record = _begin(tmp_path)
    extra = [
        SensorReading(sensor_id="S1", x=1.2, y=2.1, values={"CO": 1.0}),
        SensorReading(sensor_id="S2", x=2.0, y=2.0, values={"CO": 1.0}),
    ]

    with pytest.raises(HistoryError, match="expected 1 reading"):
        _finish(record, readings_ppmv=extra)

    # The rejected finalization left the reservation untouched.
    assert history.load_run(record.run_dir).execution_status == "incomplete"


def test_missing_readings_finalize_as_an_audited_failure(tmp_path):
    """Fewer readings than frozen sensors is recorded, with its reason."""
    record = _begin(tmp_path)
    finished = _finish(record, readings_ppmv=[])

    assert finished.execution_status == "failed"
    assert finished.execution.error == history.NO_READINGS_ERROR


def test_readings_for_a_project_without_sensors_are_rejected(tmp_path):
    record = _begin(tmp_path, _project(sensors=[]))

    with pytest.raises(HistoryError, match="captured without sensors"):
        _finish(record, readings_ppmv=[SensorReading(sensor_id="S1", x=1.0, y=1.0, values={"CO": 1.0})])


def test_a_manifest_with_readings_for_the_wrong_sensors_is_rejected_on_load(tmp_path):
    """A hand-edited or foreign manifest cannot smuggle in foreign readings."""
    record = _finish(_begin(tmp_path))
    _rewrite(
        record,
        lambda payload: payload["results"]["sensor_readings"][0].__setitem__("sensor_id", "S9"),
    )

    with pytest.raises(HistoryError, match=history.NO_READINGS_ERROR):
        history.load_run(record.run_dir)


def test_reading_gas_order_follows_the_frozen_scenario(tmp_path):
    """Gas *order* is a post-processor detail; the manifest must be deterministic.

    ``post.sample_sensors`` reads scalar names out of the VTK file, so the order
    it returns is whatever the writer emitted. Persisting that verbatim would
    make two identical runs differ textually and couple the manifest to a VTK
    implementation detail, so readings are re-keyed into scenario order.
    """
    project = _project(scenario=Scenario(gas_sources={"CO": "auto", "CH4": "auto", "VOC": 12.5}))
    record = _begin(tmp_path, project)
    finished = _finish(
        record,
        readings_ppmv=[
            SensorReading(
                sensor_id="S1",
                x=1.2,
                y=2.1,
                # Deliberately not the scenario order.
                values={"VOC": 0.05, "CO": 0.465, "CH4": 2217.75},
            )
        ],
    )

    assert list(finished.results.sensor_readings[0].values_ppmv) == ["CO", "CH4", "VOC"]
    assert list(history.load_run(record.run_dir).results.sensor_readings[0].values_ppmv) == [
        "CO",
        "CH4",
        "VOC",
    ]
    # The values themselves are untouched by the re-keying.
    assert finished.results.sensor_readings[0].values_ppmv["CH4"] == pytest.approx(2217.75)


def test_a_gas_subset_is_still_rejected_after_ordering(tmp_path):
    """Re-keying must not soften the membership check into a subset match."""
    record = _begin(tmp_path)

    with pytest.raises(HistoryError, match="carries gases"):
        _finish(
            record,
            readings_ppmv=[SensorReading(sensor_id="S1", x=1.2, y=2.1, values={"VOC": 1.0})],
        )


def test_multi_sensor_order_is_preserved_and_enforced(tmp_path):
    project = _project(
        sensors=[Sensor("S1", 1.2, 2.1), Sensor("S2", 3.0, 2.2), Sensor("S3", 5.5, 1.0)]
    )
    record = _begin(tmp_path, project)
    readings = [
        SensorReading(sensor_id="S1", x=1.2, y=2.1, values={"CO": 0.465}),
        SensorReading(sensor_id="S2", x=3.0, y=2.2, values={"CO": 0.310}),
        SensorReading(sensor_id="S3", x=5.5, y=1.0, values={"CO": 0.120}),
    ]
    finished = _finish(record, readings_ppmv=readings)

    assert [r.sensor_id for r in finished.results.sensor_readings] == ["S1", "S2", "S3"]
    assert [r.sensor_id for r in history.load_run(record.run_dir).results.sensor_readings] == [
        "S1",
        "S2",
        "S3",
    ]

    swapped = [
        SensorReading(sensor_id="S2", x=3.0, y=2.2, values={"CO": 0.310}),
        SensorReading(sensor_id="S1", x=1.2, y=2.1, values={"CO": 0.465}),
        SensorReading(sensor_id="S3", x=5.5, y=1.0, values={"CO": 0.120}),
    ]
    other = _begin(tmp_path, project)
    with pytest.raises(HistoryError, match=history.NO_READINGS_ERROR):
        _finish(other, readings_ppmv=swapped)


# 14 -- scientific gates are stated, never inferred (MB-4) --------------------


def test_a_clean_exit_leaves_every_scientific_gate_non_passing(tmp_path):
    """MB-4: process success must not read as convergence or verification."""
    finished = _finish(_begin(tmp_path))

    assert finished.execution_status == "succeeded"
    assert finished.execution.exit_code == 0
    assert finished.quality.convergence == "not_evaluated"
    assert finished.quality.mesh_independence == "not_run"
    assert finished.quality.mass_balance == "not_run"
    assert finished.quality.experimental_validation == "not_run"
    assert finished.quality.classification == "screening_estimate"
    assert finished.quality.verification_metrics == ()
    assert finished.quality.validation_metrics == ()

    payload = _manifest(finished)["quality"]
    assert payload["convergence"] == "not_evaluated"
    assert payload["mesh_independence"] == "not_run"
    assert payload["mass_balance"] == "not_run"
    assert payload["experimental_validation"] == "not_run"

    # The repository's documented 76.5% mesh-independence failure is a project
    # fact, not this run's measurement; it must not appear on an ordinary run.
    assert "0.765" not in (finished.run_dir / history.MANIFEST_NAME).read_text()
    assert "76.5" not in (finished.run_dir / history.MANIFEST_NAME).read_text()


@pytest.mark.parametrize(
    "field,value",
    [
        ("convergence", "converged"),
        ("mesh_independence", "probably fine"),
        ("mass_balance", "PASS"),
        ("experimental_validation", "yes"),
    ],
)
def test_a_gate_state_outside_its_closed_set_is_rejected(tmp_path, field, value):
    record = _begin(tmp_path)
    _rewrite(record, lambda payload: payload["quality"].__setitem__(field, value))

    with pytest.raises(HistoryError, match=f"quality.{field}"):
        history.load_run(record.run_dir)


def test_a_solver_termination_outside_its_closed_set_is_rejected(tmp_path):
    record = _begin(tmp_path)
    _rewrite(record, lambda payload: payload["execution"].__setitem__("solver_termination", "ok"))

    with pytest.raises(HistoryError, match="solver_termination"):
        history.load_run(record.run_dir)


def test_a_metric_entry_can_still_be_recorded_when_one_is_really_produced(tmp_path):
    """The gate states must not block a genuine, traceable metric."""
    record = _begin(tmp_path)
    finished = _finish(record)
    payload = _manifest(finished)
    payload["quality"]["verification_metrics"] = [
        {
            "name": "mesh independence",
            "value": 0.765,
            "unit": "1",
            "target": "<0.10",
            "status": "failed",
            "provenance": "tests/verification/test_mesh_independence.py",
        }
    ]
    (record.run_dir / history.MANIFEST_NAME).write_text(json.dumps(payload), encoding="utf-8")

    reloaded = history.load_run(record.run_dir)
    assert len(reloaded.quality.verification_metrics) == 1
    assert reloaded.quality.verification_metrics[0].value == pytest.approx(0.765)
    assert reloaded.quality.validation_metrics == ()


# 15 -- ppmv recipes (B1) ------------------------------------------------------


def test_source_and_probe_ppmv_values_follow_the_documented_recipe(tmp_path):
    """B1: auto uses the cited ppmv directly; manual is already ppmv; probes ×1e6.

    Pins the concrete numbers the review smoke inspection produced, so a future
    refactor of the conversion path cannot silently change what is persisted.
    """
    project = _project(
        scenario=Scenario(gas_sources={"CO": "auto", "CH4": "auto", "VOC": 12.5}),
    )
    record = _begin(tmp_path, project)

    sources = record.project.scenario.gas_sources
    assert sources["CO"].resolved_ppmv == pytest.approx(105.0)
    # The default project is a fresh load (8 h). The generated gas is the
    # regulation's F = 0.5 split at every age, so the fresh load's methane share
    # is ~50% by volume, not the 0 the phase switch used to force and not the
    # 550 000 ppmv of the old mature-landfill default.
    assert sources["CH4"].resolved_ppmv == pytest.approx(500_000.0, rel=2e-3)
    assert sources["VOC"].resolved_ppmv == pytest.approx(12.5)
    assert sources["VOC"].requested_ppmv == pytest.approx(12.5)
    assert sources["VOC"].provenance == "user input"

    # ``source_concentration`` is already ppmv, and equals the resolved volume
    # fraction scaled back up — the two paths must agree.
    assert sources["CO"].resolved_ppmv == pytest.approx(
        casegen.resolve_sources(project.scenario)["CO"] / casegen.PPM_SCALE
    )

    # A raw volume fraction becomes ppmv by exactly one ×1e6 — performed by the
    # caller, never here, so finish_run stores the ppmv value it is given.
    raw_volume_fraction = 0.465e-6
    assert raw_volume_fraction * (1.0 / casegen.PPM_SCALE) == pytest.approx(0.465)
    finished = _finish(
        record,
        readings_ppmv=[
            SensorReading(sensor_id="S1", x=1.2, y=2.1, values={"CO": 0.465, "CH4": 1.0, "VOC": 2.0})
        ],
    )
    assert finished.results.sensor_readings[0].values_ppmv["CO"] == pytest.approx(0.465)

    # Immutability: the project's own scenario is untouched by snapshotting.
    assert project.scenario.gas_sources == {"CO": "auto", "CH4": "auto", "VOC": 12.5}


def test_the_auto_source_value_does_not_follow_a_later_default_change(tmp_path, monkeypatch):
    """A resolved value is frozen; editing the cited default cannot rewrite it.

    The patch must target the name ``scenario`` actually calls, otherwise it
    intercepts nothing and the assertion below would hold for the wrong reason.
    """
    record = _begin(tmp_path)
    assert record.project.scenario.gas_sources["CO"].resolved_ppmv == pytest.approx(105.0)

    monkeypatch.setattr(
        "scentinel.core.scenario.regime_concentration",
        lambda gas, regime="msw-only": 999.0,
    )

    # The patch is live: a new run picks the changed default up.
    fresh = _begin(tmp_path, _project(name="AfterChange"))
    assert fresh.project.scenario.gas_sources["CO"].resolved_ppmv == pytest.approx(999.0)

    # The already-frozen record still reports the value it resolved with.
    reloaded = history.load_run(record.run_dir)
    assert reloaded.project.scenario.gas_sources["CO"].resolved_ppmv == pytest.approx(105.0)


def test_importing_the_history_module_does_not_pull_in_qt():
    """The core history API must stay usable without a GUI toolkit."""
    import subprocess
    import sys

    probe = (
        "import sys; import scentinel.core.history; "
        "print('PySide6' in sys.modules, 'scentinel.ui' in sys.modules)"
    )
    src_root = Path(history.__file__).parents[2]  # .../<worktree>/src
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": str(src_root)},
    )

    assert result.stdout.strip() == "False False"


def test_importing_the_history_module_does_not_require_the_cfd_extra():
    """The history read API must work without the optional ``cfd`` extra.

    ``history`` imports ``casegen``, which used to import ``mesh`` and therefore
    ``gmsh``. README advertises ``list_runs()``/``get_run()`` as a read API, and
    history performs no meshing, so a machine without gmsh must still be able to
    read a manifest. Both optional imports are blocked here.
    """
    import subprocess
    import sys

    probe = (
        "import sys, builtins\n"
        "real = builtins.__import__\n"
        "def blocked(name, *args, **kwargs):\n"
        "    if name.split('.')[0] in ('gmsh', 'PySide6'):\n"
        "        raise ImportError(f'blocked: {name}')\n"
        "    return real(name, *args, **kwargs)\n"
        "builtins.__import__ = blocked\n"
        "import scentinel.core.history as h\n"
        "print(h.RUN_FORMAT_VERSION)\n"
    )
    src_root = Path(history.__file__).parents[2]
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": str(src_root)},
    )

    assert result.stdout.strip() == str(history.RUN_FORMAT_VERSION)


def test_a_history_read_api_call_works_without_the_cfd_extra(tmp_path):
    """The documented read path, not just the import, survives a gmsh-free env."""
    import subprocess
    import sys

    record = _finish(_begin(tmp_path))
    probe = (
        "import sys, builtins\n"
        "real = builtins.__import__\n"
        "def blocked(name, *args, **kwargs):\n"
        "    if name.split('.')[0] in ('gmsh', 'PySide6'):\n"
        "        raise ImportError(f'blocked: {name}')\n"
        "    return real(name, *args, **kwargs)\n"
        "builtins.__import__ = blocked\n"
        "from scentinel.core.history import get_run\n"
        f"run = get_run({str(tmp_path / 'runs')!r}, 'run-001')\n"
        "print(run.run_id, run.execution_status)\n"
    )
    src_root = Path(history.__file__).parents[2]
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": str(src_root)},
    )

    assert result.stdout.strip() == f"{record.run_id} succeeded"
