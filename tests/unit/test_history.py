from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scentinel.core import casegen, gas_data, history
from scentinel.core.geometry import BinGeometry
from scentinel.core.history import HistoryError
from scentinel.core.post import SensorReading
from scentinel.core.project import Project, Sensor
from scentinel.core.scenario import Scenario

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
    assert record.status == "incomplete"
    assert record.run_dir == tmp_path / "runs" / "run-001"
    assert (record.run_dir / history.MANIFEST_NAME).is_file()

    payload = _manifest(record)
    assert payload["format_version"] == 1
    assert payload["status"] == "incomplete"
    assert payload["started_at_utc"] == "2026-09-19T12:34:56Z"
    assert payload["finished_at_utc"] is None
    assert payload["application"] == {"name": "scentinel", "version": "0.1.0"}

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
    assert scenario["ventilation_on"] is False
    assert payload["project"]["sensors"] == [{"sensor_id": "S1", "x_m": 1.2, "y_m": 2.1}]

    execution = payload["execution"]
    assert execution["mesh_size_m"] == 0.25
    assert execution["end_iteration"] == 500
    assert execution["solver"] == casegen.SOLVER
    assert execution["container_image"] == casegen.IMAGE
    assert execution["case_dir"] is None
    assert execution["exit_code"] is None

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

    assert finished.status == "succeeded"
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

    assert finished.status == "failed"
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

    assert finished.status == "cancelled"
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


def test_a_success_with_sensors_but_no_readings_is_not_a_success(tmp_path):
    record = _begin(tmp_path)

    with pytest.raises(HistoryError, match="must carry its readings"):
        _finish(record, readings_ppmv=[])


def test_finish_run_accepts_a_project_without_sensors_and_no_readings(tmp_path):
    record = _begin(tmp_path, _project(sensors=[]))
    finished = _finish(record, readings_ppmv=[])

    assert finished.status == "succeeded"
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
    assert history.load_run(record.run_dir).status == "incomplete"


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


def test_an_invalid_status_is_rejected(tmp_path):
    record = _begin(tmp_path)
    _rewrite(record, lambda payload: payload.__setitem__("status", "ok"))

    with pytest.raises(HistoryError, match="status 'ok'"):
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
    assert reloaded.status == "incomplete"
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
