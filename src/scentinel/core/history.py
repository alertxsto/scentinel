"""Persistent run history: one immutable, provenance-bearing manifest per attempt.

Every simulation attempt reserves its own ``run-NNN`` directory under the runs
root and writes exactly one ``run.json`` into it — first in ``incomplete`` state
before any meshing work, then atomically replaced once the attempt reaches a
terminal status. A crash therefore leaves an honest ``incomplete`` record rather
than no record or a false success.

There is deliberately no central index: the immutable per-run manifests are the
history, so an index can never diverge from them and every run stays portable
with its case. Allocation uses the filesystem as the concurrency authority — a
directory is claimed with ``mkdir(exist_ok=False)`` and never deleted, cleared,
or reused, so an id is durable across application restarts.

The module is pure core: it must not import ``PySide6``, ``MainWindow``,
``SolverWorker``, or ``RunOutcome``.

Units are explicit in every field name that carries a physical quantity:
metres, metres per second, and ppmv. Scenario gas inputs entered in the UI are
ppmv; the OpenFOAM scalar fields and :attr:`post.SensorReading.values` are
dimensionless volume fractions. ``finish_run()`` takes readings that have
*already* been converted to ppmv, exactly once, by the caller.

A manifest separates four things that are easy to conflate:

* **requested inputs** (``project``) — what the user asked for;
* **applied physics** (``applied_physics``) — the numerical settings the
  generated case actually used, read from the same constants the case writer
  renders into the OpenFOAM dictionaries, plus a SHA-256 digest of the
  generated case inputs;
* **execution outcome** (``execution_status`` and ``execution``) — whether the
  container pipeline exited cleanly. ``succeeded`` means the process exited 0
  and the probes were sampled; it is **not** a claim of convergence,
  verification, or validation; and
* **evidence quality** (``quality``) — the screening classification plus
  closed-enum gate states and the separate verification/validation metric
  arrays.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from scentinel import __version__
from scentinel.core import casegen, gas_data
from scentinel.core.geometry import MOUND_SHAPES, BinGeometry
from scentinel.core.project import Project, Sensor
from scentinel.core.scenario import (
    WASTE_SPECS,
    WASTE_TYPES,
    WIND_DIRECTIONS,
    Scenario,
    auto_concentration_ppmv,
)

#: Version of the manifest schema. Any change to the serialized shape or its
#: meaning bumps this and is rejected by older readers.
#:
#: 1 — initial schema: requested inputs, execution outcome, results, quality.
#: 2 — adds ``applied_physics`` (applied constants and the case-input digest),
#:     qualifies ventilation as request-plus-modelled, renames the outcome to
#:     ``execution_status``, names the requested iteration count explicitly,
#:     and adds closed-enum scientific gate states. Version 1 manifests are
#:     rejected rather than misread: they cannot describe what they applied.
#: 3 — records the waste stream (type, organic and moisture fraction) in the
#:     scenario block, because it selects the AP-42 regime and scales the auto
#:     source strengths. A version 2 manifest cannot say which stream produced
#:     its resolved concentrations.
RUN_FORMAT_VERSION = 3

#: File name of the per-run manifest, inside its ``run-NNN`` directory.
MANIFEST_NAME = "run.json"

#: A run directory name: ``run-`` plus three or more decimal digits. Matching
#: names participate in allocation even when their manifest is missing or
#: corrupt, so an id is never handed out twice.
RUN_DIR_PATTERN = re.compile(r"^run-(?P<index>\d{3,})$")

#: Lifecycle/execution states a manifest can carry. ``succeeded`` is strictly a
#: process outcome: the container pipeline exited 0 and every frozen sensor was
#: sampled. It says nothing about convergence, mesh independence, mass balance,
#: or experimental validation — those live in ``quality`` as their own gates.
ExecutionStatus = Literal["incomplete", "succeeded", "failed", "cancelled"]

EXECUTION_STATUSES: tuple[str, ...] = ("incomplete", "succeeded", "failed", "cancelled")

#: The application that wrote the manifest.
APPLICATION_NAME = "scentinel"

#: Unit of every persisted concentration. ``post.SensorReading.values`` are
#: volume fractions; callers convert with ``casegen.PPM_SCALE`` (dividing by
#: ``1e-6``) before calling :func:`finish_run`.
CONCENTRATION_UNIT = "ppmv"

#: Source modes. ``auto`` means "the cited AP-42 default, resolved at run
#: start"; ``manual`` means "the number the user typed".
AUTO_MODE = "auto"
MANUAL_MODE = "manual"

#: Provenance recorded for a manual source. No citation may be fabricated for a
#: user-entered value.
MANUAL_PROVENANCE = "user input"

#: Every ordinary run is a screening estimate: absolute concentrations are not
#: mesh-converged (see ``docs/ROADMAP.md``), so nothing here may be presented as
#: calibrated. Verification and validation metrics are separate, empty arrays
#: unless a real metric was produced for that run — empty never means "passed".
QUALITY_CLASSIFICATION = "screening_estimate"
QUALITY_UNCERTAINTY = (
    "Absolute concentrations are not mesh-converged; use results for relative screening only."
)

#: Closed value sets for the per-run scientific gates. Absence of evidence must
#: be *stated*, not inferred from a successful process exit: a consumer that
#: filters on ``execution_status == "succeeded"`` and nothing else would
#: otherwise render an unverified run as if the gates had passed.
GATE_NOT_EVALUATED = "not_evaluated"
GATE_NOT_RUN = "not_run"

#: ``quality.convergence``. ``endTime`` is reached by counting iterations, so
#: reaching it proves nothing about the residual targets in ``fvSolution``.
#: Nothing in an ordinary run parses the achieved residuals, so an ordinary run
#: records ``not_evaluated`` and never ``converged``.
CONVERGENCE_STATES: tuple[str, ...] = (
    GATE_NOT_EVALUATED,
    "residual_targets_met",
    "residual_targets_not_met",
)

#: ``quality.mesh_independence``. The repository's own verification gate fails
#: today (see ``docs/ROADMAP.md``); an ordinary run never measures it.
MESH_INDEPENDENCE_STATES: tuple[str, ...] = (GATE_NOT_RUN, "passed", "failed")

#: ``quality.mass_balance``. ``post.mass_balance_error()`` exists but is not
#: wired into the run pipeline, so an ordinary run records ``not_run``.
MASS_BALANCE_STATES: tuple[str, ...] = (GATE_NOT_RUN, "passed", "failed")

#: ``quality.experimental_validation``. No measurement set exists.
VALIDATION_STATES: tuple[str, ...] = (GATE_NOT_RUN, "passed", "failed")

#: ``execution.solver_termination``. ``stopAt endTime`` is a requested control
#: action, not a termination reason the pipeline parses. ``not_evaluated`` is
#: the honest record until residual/termination parsing exists; inferring
#: "converged" from exit code 0 would be a fabricated scientific claim.
SOLVER_TERMINATION_STATES: tuple[str, ...] = (
    GATE_NOT_EVALUATED,
    "end_time_reached",
    "residual_targets_met",
    "solver_error",
)

#: Why a run that exited cleanly is nonetheless recorded as failed.
NO_READINGS_ERROR = "sensor readings do not match captured run inputs"

#: Name of the temporary sibling used to replace a manifest atomically.
_TEMP_MANIFEST_NAME = f".{MANIFEST_NAME}.tmp"

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

_TOP_LEVEL_KEYS = (
    "format_version",
    "run_id",
    "execution_status",
    "started_at_utc",
    "finished_at_utc",
    "application",
    "project",
    "applied_physics",
    "execution",
    "results",
    "quality",
)
_APPLICATION_KEYS = ("name", "version")
_PROJECT_KEYS = ("name", "geometry", "scenario", "sensors")
_GEOMETRY_KEYS = ("length_m", "height_m", "mound_shape", "mound_fill_fraction")
_SCENARIO_KEYS = (
    "wind_speed_m_s",
    "wind_direction",
    "ventilation",
    "gas_sources",
    "waste_type",
    "age_h",
    "organic_fraction",
    "moisture_fraction",
)
_VENTILATION_KEYS = ("requested_on", "modelled")
_GAS_SOURCE_KEYS = ("mode", "requested_ppmv", "resolved_ppmv", "provenance")
_SENSOR_KEYS = ("sensor_id", "x_m", "y_m")
_APPLIED_PHYSICS_KEYS = (
    "wind_speed_reported_m_s",
    "inlet_speed_at_rim_m_s",
    "wind_profile",
    "wind_profile_exponent",
    "wind_reference_height_m",
    "nu_m2_s",
    "scalar_diffusivity_m2_s",
    "linear_solver_settings",
    "residual_targets",
    "relaxation_factors",
    "non_orthogonal_correctors",
    "case_input_digest",
)
_LINEAR_SOLVER_KEYS = (
    "fields",
    "solver",
    "tolerance",
    "relTol",
    "smoother",
    "preconditioner",
)
_EXECUTION_KEYS = (
    "mesh_size_m",
    "requested_end_iteration",
    "solver",
    "container_image",
    "case_dir",
    "mesh_cells",
    "element_types",
    "exit_code",
    "failed_stage",
    "error",
    "solver_termination",
)
_RESULTS_KEYS = ("concentration_unit", "sensor_readings")
_READING_KEYS = ("sensor_id", "x_m", "y_m", "values_ppmv")
_QUALITY_KEYS = (
    "classification",
    "uncertainty",
    "convergence",
    "mesh_independence",
    "mass_balance",
    "experimental_validation",
    "verification_metrics",
    "validation_metrics",
)
_METRIC_KEYS = ("name", "value", "unit", "target", "status", "provenance")


class HistoryError(ValueError):
    """A manifest is invalid, or a run cannot be snapshotted or persisted."""


@dataclass(frozen=True)
class ApplicationRecord:
    """Application identity that wrote the manifest."""

    name: str
    version: str


@dataclass(frozen=True)
class GeometryRecord:
    """Bin cross-section as captured at run start (metres, dimensionless)."""

    length_m: float
    height_m: float
    mound_shape: str
    mound_fill_fraction: float


@dataclass(frozen=True)
class GasSourceRecord:
    """One gas source, with the requested mode and the resolved ppmv value.

    ``resolved_ppmv`` is frozen at run start so a later change to the cited
    AP-42 defaults cannot rewrite what this run actually solved.
    """

    key: str
    mode: str
    requested_ppmv: float | None
    resolved_ppmv: float
    provenance: str


@dataclass(frozen=True)
class VentilationRecord:
    """Ventilation as requested by the user and as actually modelled.

    ``modelled`` is ``False`` until the case generator reads the flag: today
    ``casegen.write_case()`` ignores it entirely. Recording a bare ``True``
    would let a comparison consumer group runs by ventilation and conclude the
    factor has no effect, when in fact it was never simulated. No comparison
    consumer may group or difference by an unmodelled factor.
    """

    requested_on: bool
    modelled: bool


@dataclass(frozen=True)
class ScenarioRecord:
    """Wind, the waste stream, the qualified ventilation request, and sources."""

    wind_speed_m_s: float
    wind_direction: str
    ventilation: VentilationRecord
    gas_sources: dict[str, GasSourceRecord]
    waste_type: str
    age_h: float
    organic_fraction: float
    moisture_fraction: float


@dataclass(frozen=True)
class SensorRecord:
    """A sensor inlet position in bin coordinates (metres)."""

    sensor_id: str
    x_m: float
    y_m: float


@dataclass(frozen=True)
class ProjectRecord:
    """Immutable input snapshot of the project that was run."""

    name: str
    geometry: GeometryRecord
    scenario: ScenarioRecord
    sensors: tuple[SensorRecord, ...]


@dataclass(frozen=True)
class AppliedPhysicsRecord:
    """The numerical experiment the generated case actually ran.

    Distinct from :class:`ProjectRecord`, which holds the *requested* inputs. A
    reported wind speed of 2 m/s becomes a different inlet velocity after the
    power-law scaling, and the case applies a single hard-coded scalar
    diffusivity rather than the per-gas table in ``gas_data``. Recording only
    the request would let two manifests look identical while the generated
    cases differ.

    ``case_input_digest`` is the authoritative guard: it is a SHA-256 over the
    generated case inputs (see :func:`casegen.case_input_digest`), so any change
    to an applied constant changes the digest even when every UI input matches.
    """

    wind_speed_reported_m_s: float
    inlet_speed_at_rim_m_s: float
    wind_profile: str
    wind_profile_exponent: float
    wind_reference_height_m: float
    nu_m2_s: float
    scalar_diffusivity_m2_s: dict[str, float]
    linear_solver_settings: tuple[dict[str, object], ...]
    residual_targets: dict[str, float]
    relaxation_factors: dict[str, float]
    non_orthogonal_correctors: int
    case_input_digest: str | None


@dataclass(frozen=True)
class ExecutionRecord:
    """Requested numerical controls, solver identity, and produced metadata.

    ``requested_end_iteration`` is the ``controlDict.endTime`` the case asked
    for — an iteration index, not elapsed physical seconds, and not evidence
    that the run stopped there or that ``residualControl`` was satisfied.
    ``solver_termination`` records how the run actually ended, from a closed
    set; ``not_evaluated`` is the honest value until the pipeline parses it.
    """

    mesh_size_m: float
    requested_end_iteration: int
    solver: str
    container_image: str
    case_dir: str | None
    mesh_cells: int | None
    element_types: dict[str, int]
    exit_code: int | None
    failed_stage: str | None
    error: str | None
    solver_termination: str


@dataclass(frozen=True)
class ReadingRecord:
    """One sensor and its persisted concentrations, in ppmv."""

    sensor_id: str
    x_m: float
    y_m: float
    values_ppmv: dict[str, float]


@dataclass(frozen=True)
class ResultsRecord:
    """Persisted results and their explicit unit."""

    concentration_unit: str
    sensor_readings: tuple[ReadingRecord, ...]


@dataclass(frozen=True)
class MetricRecord:
    """One verification or validation metric.

    Nothing in the ordinary run pipeline produces these; the shape exists so a
    future workflow can record a real metric with its unit, target, status, and
    provenance instead of inventing a pass.
    """

    name: str
    value: float
    unit: str
    target: str | None
    status: str
    provenance: str


@dataclass(frozen=True)
class QualityRecord:
    """Result-quality classification, closed-enum gate states, and metrics.

    The gate states are separate from the execution outcome on purpose. A run
    can exit 0 and still have ``mesh_independence == "not_run"``; the manifest
    states that rather than leaving a consumer to infer it from absence. Every
    state is drawn from a closed set, so no free-text value can imply a pass.
    """

    classification: str
    uncertainty: str
    convergence: str
    mesh_independence: str
    mass_balance: str
    experimental_validation: str
    verification_metrics: tuple[MetricRecord, ...]
    validation_metrics: tuple[MetricRecord, ...]


@dataclass(frozen=True)
class RunRecord:
    """One validated manifest.

    ``run_dir`` is the convenience of the directory the manifest lives in; it is
    not serialized, because the manifest must stay portable with its run.
    """

    format_version: int
    run_id: str
    execution_status: ExecutionStatus
    started_at_utc: str
    finished_at_utc: str | None
    application: ApplicationRecord
    project: ProjectRecord
    applied_physics: AppliedPhysicsRecord
    execution: ExecutionRecord
    results: ResultsRecord
    quality: QualityRecord
    run_dir: Path


# -- public API --------------------------------------------------------------


def snapshot_project(project: Project) -> Project:
    """A deep, independent copy of ``project`` suitable for handing to a worker.

    The manifest's immutable-input promise only holds if the pipeline samples
    the *same* sensors the record froze. Passing the live editor model to the
    worker leaves a window — viewport clicks are not disabled by every path —
    in which the sensor list changes between reservation and sampling, and a
    succeeded record would then claim inputs it never used.

    Callers take one snapshot, pass it to :func:`begin_run` and to the worker,
    and keep editing their own model. Disabling the editing surface while a run
    is in flight is good UX defence but is not the correctness mechanism.
    """
    return Project(
        name=project.name,
        geometry=replace(project.geometry),
        scenario=Scenario(
            wind_speed_m_s=project.scenario.wind_speed_m_s,
            wind_direction=project.scenario.wind_direction,
            ventilation_on=project.scenario.ventilation_on,
            waste_type=project.scenario.waste_type,
            age_h=project.scenario.age_h,
            moisture_fraction=project.scenario.moisture_fraction,
            gas_sources=dict(project.scenario.gas_sources),
        ),
        sensors=[
            Sensor(sensor_id=sensor.sensor_id, x=sensor.x, y=sensor.y)
            for sensor in project.sensors
        ],
        sensor_lab=replace(project.sensor_lab),
    )


def begin_run(
    runs_root: Path,
    project: Project,
    *,
    mesh_size_m: float,
    end_iteration: int,
    started_at: datetime | None = None,
) -> RunRecord:
    """Reserve the next free run directory and write its incomplete manifest.

    ``project`` is snapshotted before anything is created, so an unknown gas key
    or an unresolved ``auto`` source aborts through the existing gas-data error
    without leaving a directory behind. If the manifest itself cannot be
    written, the just-reserved directory is removed again only if it is still
    empty, and the error propagates: no run may start without a durable record.

    ``applied_physics`` is captured here, from the same constants the case
    writer will render, and carries no digest yet: the digest can only be
    computed once the case exists, and :func:`finish_run` fills it in.
    """
    root = Path(runs_root)
    started_text = _format_timestamp(started_at or datetime.now(timezone.utc))
    snapshot = _snapshot_project(project)
    applied = _applied_physics(project.scenario, project.geometry, digest=None)
    execution = _execution_settings(mesh_size_m, end_iteration)

    run_dir = _reserve_run_dir(root)
    try:
        record = RunRecord(
            format_version=RUN_FORMAT_VERSION,
            run_id=run_dir.name,
            execution_status="incomplete",
            started_at_utc=started_text,
            finished_at_utc=None,
            application=ApplicationRecord(name=APPLICATION_NAME, version=__version__),
            project=snapshot,
            applied_physics=applied,
            execution=execution,
            results=ResultsRecord(concentration_unit=CONCENTRATION_UNIT, sensor_readings=()),
            quality=_screening_quality(),
            run_dir=run_dir,
        )
        payload = _payload(record)
        validated = _decode_manifest(payload, run_dir)
        _write_manifest(run_dir, payload)
    except Exception:
        _remove_if_empty(run_dir)
        raise
    return validated


def finish_run(
    record: RunRecord,
    *,
    status: ExecutionStatus,
    case_dir: Path | str | None,
    mesh_cells: int | None,
    element_types: dict[str, int],
    exit_code: int | None,
    failed_stage: str | None,
    error: str | None,
    readings_ppmv: object,
    finished_at: datetime | None = None,
    solver_termination: str = GATE_NOT_EVALUATED,
) -> RunRecord:
    """Atomically replace an incomplete manifest with its terminal outcome.

    ``readings_ppmv`` is an ordered sequence of reading-like objects carrying
    ``sensor_id``, ``x``, ``y``, and a ``values`` mapping of gas to ppmv — the
    shape :func:`scentinel.core.post.sample_sensors` returns, already converted.
    Values are stored as given: there is no second conversion here.

    Readings are checked against the *frozen* sensor snapshot, not the live
    project: ids, coordinates, order, and gas keys must match exactly. A clean
    process exit whose readings do not match did not succeed, so it is recorded
    as ``failed`` with :data:`NO_READINGS_ERROR` rather than as an opaque
    exit-0 failure. Readings that do not match are never persisted, for any
    status, so a stored reading always describes the sensors the manifest froze.

    ``case_dir`` may be absolute (the pipeline's own path) or relative; either
    way only the validated path relative to the run directory is persisted, so a
    manifest never carries a workstation path. When the case exists, its
    generated inputs are digested and stored, which is the authoritative record
    of the applied numerical experiment. ``record`` must still be ``incomplete``
    on disk, which makes finalization single-shot: an already terminal manifest
    is never rewritten.
    """
    where = str(Path(record.run_dir) / MANIFEST_NAME)
    terminal = _execution_status(status, where)
    if terminal == "incomplete":
        raise HistoryError("finish_run() requires a terminal status, not 'incomplete'")
    termination = _closed_enum(
        solver_termination, SOLVER_TERMINATION_STATES, "solver_termination", where
    )

    persisted = load_run(record.run_dir)
    where = str(persisted.run_dir / MANIFEST_NAME)
    if persisted.run_id != record.run_id:
        raise HistoryError(f"{where}: run id {record.run_id!r} does not match the persisted run")
    if persisted.execution_status != "incomplete":
        raise HistoryError(
            f"{where}: run {persisted.run_id} is already "
            f"{persisted.execution_status!r} and cannot be finalized again"
        )

    portable_case = _portable_case_dir(persisted.run_dir, case_dir)
    readings = tuple(_reading_records(readings_ppmv))
    if readings:
        # Supplied readings must describe the frozen sensors. This is a hard
        # error, not a status change: persisting foreign numbers under this
        # run's inputs would break the manifest's central promise, so nothing
        # is written and the caller sees why.
        problem = _readings_problem(persisted.project, readings)
        if problem is not None:
            raise HistoryError(f"{where}: {problem}")
        readings = _ordered_readings(readings, persisted.project)
    elif persisted.project.sensors and exit_code == 0:
        # A clean process exit that produced no readings for the sensors this
        # run froze did not succeed. This is decided here, not left to the
        # caller's status mapping, so the record always explains itself rather
        # than being an opaque exit-0 failure.
        if terminal == "succeeded":
            terminal = "failed"
        if not error:
            error = NO_READINGS_ERROR

    finished = RunRecord(
        format_version=persisted.format_version,
        run_id=persisted.run_id,
        execution_status=terminal,
        started_at_utc=persisted.started_at_utc,
        finished_at_utc=_format_timestamp(finished_at or datetime.now(timezone.utc)),
        application=persisted.application,
        project=persisted.project,
        applied_physics=replace(
            persisted.applied_physics,
            case_input_digest=_case_digest(persisted.run_dir, portable_case, persisted.project),
        ),
        execution=ExecutionRecord(
            mesh_size_m=persisted.execution.mesh_size_m,
            requested_end_iteration=persisted.execution.requested_end_iteration,
            solver=persisted.execution.solver,
            container_image=persisted.execution.container_image,
            case_dir=portable_case,
            mesh_cells=mesh_cells,
            element_types=dict(element_types or {}),
            exit_code=exit_code,
            failed_stage=failed_stage,
            error=error,
            solver_termination=termination,
        ),
        results=ResultsRecord(
            concentration_unit=CONCENTRATION_UNIT,
            sensor_readings=readings,
        ),
        quality=persisted.quality,
        run_dir=persisted.run_dir,
    )
    payload = _payload(finished)
    validated = _decode_manifest(payload, persisted.run_dir)
    _write_manifest(persisted.run_dir, payload)
    return validated


def load_run(run_dir: Path) -> RunRecord:
    """Read and strictly validate one manifest.

    Any problem — missing or unreadable manifest, malformed JSON, unsupported
    version, invalid status/id, missing field, non-finite number, non-portable
    case path — raises :class:`HistoryError` naming the manifest and the
    problem. A bad record is never silently accepted.
    """
    run_dir = Path(run_dir)
    manifest = run_dir / MANIFEST_NAME
    if not run_dir.is_dir():
        raise HistoryError(f"{manifest}: {run_dir} is not a run directory")
    try:
        text = manifest.read_text(encoding="utf-8")
    except OSError as error:
        raise HistoryError(f"{manifest}: could not be read: {error}") from error
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise HistoryError(f"{manifest}: is not valid JSON: {error}") from error
    return _decode_manifest(payload, run_dir)


def list_runs(runs_root: Path) -> list[RunRecord]:
    """Every manifest under ``runs_root``, in ascending numeric run-id order.

    A missing history root is an empty collection. A malformed manifest is not
    skipped: the first invalid one, in numeric order, raises.
    """
    root = Path(runs_root)
    if not root.is_dir():
        return []
    matched = [child for child in root.iterdir() if RUN_DIR_PATTERN.match(child.name)]
    matched.sort(key=lambda child: int(RUN_DIR_PATTERN.match(child.name).group("index")))
    return [load_run(child) for child in matched]


def get_run(runs_root: Path, run_id: str) -> RunRecord | None:
    """Look up one run by exact id, or ``None`` when the root or id is absent.

    Invalid id syntax raises instead of being joined into a path, so a lookup
    cannot escape the runs root.
    """
    if not isinstance(run_id, str) or not RUN_DIR_PATTERN.match(run_id):
        raise HistoryError(
            f"invalid run id {run_id!r}; expected run- followed by three or more decimal digits"
        )
    root = Path(runs_root)
    if not root.is_dir():
        return None
    run_dir = root / run_id
    if not run_dir.exists():
        return None
    return load_run(run_dir)


# -- allocation --------------------------------------------------------------


def _reserve_run_dir(runs_root: Path) -> Path:
    """Claim the next free ``run-NNN`` directory; never reuse an existing one."""
    runs_root.mkdir(parents=True, exist_ok=True)
    index = _next_index(runs_root)
    while True:
        candidate = runs_root / f"run-{index:03d}"
        try:
            candidate.mkdir(exist_ok=False)
        except FileExistsError:
            # Another allocator won this id between the scan and the mkdir.
            index += 1
            continue
        return candidate


def _next_index(runs_root: Path) -> int:
    """One greater than the highest matching run directory, or 1."""
    highest = 0
    for child in runs_root.iterdir():
        match = RUN_DIR_PATTERN.match(child.name)
        if match is not None:
            highest = max(highest, int(match.group("index")))
    return highest + 1


def _remove_if_empty(run_dir: Path) -> None:
    """Best-effort removal of a just-reserved directory that is still empty."""
    try:
        run_dir.rmdir()
    except OSError:
        pass


# -- snapshot ----------------------------------------------------------------


def _snapshot_project(project: Project) -> ProjectRecord:
    """Freeze the project inputs, resolving every gas source exactly once.

    ``casegen.resolve_sources()`` runs first so an unknown gas key or an
    unresolved ``"auto"`` aborts through the existing gas-data error before any
    directory is created. The project itself is never mutated.
    """
    scenario = project.scenario
    casegen.resolve_sources(scenario)

    sources: dict[str, GasSourceRecord] = {}
    for gas, value in scenario.gas_sources.items():
        if isinstance(value, str):
            sources[gas] = GasSourceRecord(
                key=gas,
                mode=AUTO_MODE,
                requested_ppmv=None,
                resolved_ppmv=auto_concentration_ppmv(scenario, gas),
                provenance=gas_data.citation(gas),
            )
        else:
            entered = float(value)
            sources[gas] = GasSourceRecord(
                key=gas,
                mode=MANUAL_MODE,
                requested_ppmv=entered,
                resolved_ppmv=entered,
                provenance=MANUAL_PROVENANCE,
            )

    geometry = project.geometry
    return ProjectRecord(
        name=project.name,
        geometry=GeometryRecord(
            length_m=geometry.length_m,
            height_m=geometry.height_m,
            mound_shape=geometry.mound_shape,
            mound_fill_fraction=geometry.mound_fill_fraction,
        ),
        scenario=ScenarioRecord(
            wind_speed_m_s=scenario.wind_speed_m_s,
            wind_direction=scenario.wind_direction,
            ventilation=VentilationRecord(
                requested_on=scenario.ventilation_on,
                # T-030 does not model ventilation and must not pretend to:
                # ``casegen.write_case()`` never reads the flag. This stays
                # False until the case generator changes, and no consumer may
                # group or difference by an unmodelled factor.
                modelled=False,
            ),
            gas_sources=sources,
            waste_type=scenario.waste_type,
            age_h=scenario.age_h,
            organic_fraction=scenario.organic_fraction,
            moisture_fraction=scenario.moisture_fraction,
        ),
        sensors=tuple(
            SensorRecord(sensor_id=sensor.sensor_id, x_m=sensor.x, y_m=sensor.y)
            for sensor in project.sensors
        ),
    )


def _applied_physics(
    scenario: Scenario, geometry: BinGeometry, *, digest: str | None
) -> AppliedPhysicsRecord:
    """Freeze the numerical settings the generated case will apply.

    The values come from :func:`casegen.applied_physics`, which reads the same
    module constants the case writer renders into the OpenFOAM dictionaries, so
    this block cannot drift from the generated case. ``digest`` is ``None``
    until the case exists.
    """
    applied = casegen.applied_physics(scenario, geometry)
    return AppliedPhysicsRecord(
        wind_speed_reported_m_s=float(applied["wind_speed_reported_m_s"]),
        inlet_speed_at_rim_m_s=float(applied["inlet_speed_at_rim_m_s"]),
        wind_profile=str(applied["wind_profile"]),
        wind_profile_exponent=float(applied["wind_profile_exponent"]),
        wind_reference_height_m=float(applied["wind_reference_height_m"]),
        nu_m2_s=float(applied["nu_m2_s"]),
        scalar_diffusivity_m2_s={
            gas: float(value)
            for gas, value in dict(applied["scalar_diffusivity_m2_s"]).items()
        },
        linear_solver_settings=tuple(
            dict(entry) for entry in applied["linear_solver_settings"]  # type: ignore[union-attr]
        ),
        residual_targets={
            key: float(value) for key, value in dict(applied["residual_targets"]).items()
        },
        relaxation_factors={
            key: float(value) for key, value in dict(applied["relaxation_factors"]).items()
        },
        non_orthogonal_correctors=int(applied["non_orthogonal_correctors"]),  # type: ignore[arg-type]
        case_input_digest=digest,
    )


def _case_digest(
    run_dir: Path, portable_case: str | None, project: ProjectRecord
) -> str | None:
    """SHA-256 of the generated case inputs, or ``None`` when there is no case.

    ``None`` covers both "no case was generated" and "the case is incomplete":
    a run cancelled or failed partway through case generation has no complete
    input set to digest, and a digest over a partial case would understate what
    was applied. A declared input that exists but cannot be read is a real
    error and propagates — only *absence* is treated as incompleteness.

    The gas names come from the frozen snapshot, not from the directory, so the
    digest covers exactly the scalar fields this run declared.
    """
    if portable_case is None:
        return None
    case_dir = Path(run_dir) / portable_case
    if not case_dir.is_dir():
        return None
    gases = list(project.scenario.gas_sources)
    declared = [case_dir / relative for relative in casegen.case_input_paths(gases)]
    if not all(path.is_file() for path in declared):
        return None
    return casegen.case_input_digest(case_dir, gases)


def _execution_settings(mesh_size_m: float, end_iteration: int) -> ExecutionRecord:
    """The execution block of a run that has not produced anything yet.

    ``requested_end_iteration`` is the steady ``simpleFoam`` control index the
    case will ask for, not elapsed physical seconds. ``solver_termination``
    stays ``not_evaluated``: exit code 0 means the process finished, not that
    the residual targets were met.
    """
    return ExecutionRecord(
        mesh_size_m=mesh_size_m,
        requested_end_iteration=end_iteration,
        solver=casegen.SOLVER,
        container_image=casegen.IMAGE,
        case_dir=None,
        mesh_cells=None,
        element_types={},
        exit_code=None,
        failed_stage=None,
        error=None,
        solver_termination=GATE_NOT_EVALUATED,
    )


def _screening_quality() -> QualityRecord:
    """Quality for a run whose scientific gates have not been evaluated.

    Every gate is stated explicitly rather than left to inference, so a
    successful process exit cannot be read as convergence, verification, or
    validation. Nothing here copies the repository's documented 76.5%
    mesh-independence failure onto an individual run.
    """
    return QualityRecord(
        classification=QUALITY_CLASSIFICATION,
        uncertainty=QUALITY_UNCERTAINTY,
        convergence=GATE_NOT_EVALUATED,
        mesh_independence=GATE_NOT_RUN,
        mass_balance=GATE_NOT_RUN,
        experimental_validation=GATE_NOT_RUN,
        verification_metrics=(),
        validation_metrics=(),
    )


def _readings_problem(
    project: ProjectRecord, readings: tuple[ReadingRecord, ...]
) -> str | None:
    """Why these supplied readings cannot describe this run, or ``None``.

    The manifest's central promise is that the sensors it froze are the sensors
    that were sampled. Checking only "some readings exist" would let a run that
    sampled a different sensor set, moved coordinates, or a different gas
    selection be stored as a success. This validates against the frozen
    snapshot, so a later mutation of the live project cannot launder a record.

    Every rejection carries :data:`NO_READINGS_ERROR` as its prefix, so a
    mismatch is auditable rather than an unexplained failure. Absence is not
    judged here — a run may legitimately have no readings, and
    :func:`finish_run` decides what a reading-less clean exit means.
    """
    frozen = project.sensors
    if not frozen:
        return f"{NO_READINGS_ERROR}: a project captured without sensors produced readings"

    expected_gases = list(project.scenario.gas_sources)
    if len(readings) != len(frozen):
        return (
            f"{NO_READINGS_ERROR}: expected {len(frozen)} reading(s) for the captured sensors, "
            f"got {len(readings)}"
        )
    for expected, actual in zip(frozen, readings):
        if actual.sensor_id != expected.sensor_id:
            return (
                f"{NO_READINGS_ERROR}: expected {expected.sensor_id!r}, got {actual.sensor_id!r}"
            )
        if actual.x_m != expected.x_m or actual.y_m != expected.y_m:
            return (
                f"{NO_READINGS_ERROR}: {expected.sensor_id} moved from "
                f"({expected.x_m}, {expected.y_m}) to ({actual.x_m}, {actual.y_m})"
            )
        if set(actual.values_ppmv) != set(expected_gases):
            return (
                f"{NO_READINGS_ERROR}: {expected.sensor_id} carries gases "
                f"{sorted(actual.values_ppmv)}, expected {sorted(expected_gases)}"
            )
    return None


def _ordered_readings(
    readings: tuple[ReadingRecord, ...], project: ProjectRecord
) -> tuple[ReadingRecord, ...]:
    """Re-key each reading's gases into the frozen scenario order.

    The pipeline reads scalar fields out of the VTK file, so their order is
    whatever the writer emitted — a property of the post-processor, not of the
    run. Persisting that order verbatim would make two identical runs differ
    textually and would couple the manifest to a VTK implementation detail.
    Sorting by the frozen scenario order keeps the manifest deterministic and
    reviewable while the gas *set* stays the thing that is validated.
    """
    order = list(project.scenario.gas_sources)
    ordered: list[ReadingRecord] = []
    for reading in readings:
        values = reading.values_ppmv
        ordered.append(
            replace(
                reading,
                values_ppmv={gas: values[gas] for gas in order if gas in values},
            )
        )
    return tuple(ordered)


def _reading_records(readings_ppmv: object) -> list[ReadingRecord]:
    """Convert reading-like objects (already ppmv) into persisted records."""
    records: list[ReadingRecord] = []
    for reading in readings_ppmv or ():
        records.append(
            ReadingRecord(
                sensor_id=getattr(reading, "sensor_id"),
                x_m=getattr(reading, "x"),
                y_m=getattr(reading, "y"),
                values_ppmv=dict(getattr(reading, "values")),
            )
        )
    return records


def _portable_case_dir(run_dir: Path, case_dir: Path | str | None) -> str | None:
    """Reduce a case directory to its portable path inside the run directory."""
    if case_dir is None:
        return None
    where = str(Path(run_dir) / MANIFEST_NAME)
    candidate = Path(case_dir)
    if not candidate.is_absolute():
        if ".." in candidate.parts:
            raise HistoryError(
                f"{where}: case_dir {str(case_dir)!r} must not contain '..'"
            )
        candidate = Path(run_dir) / candidate
    root = Path(os.path.abspath(run_dir))
    absolute = Path(os.path.abspath(candidate))
    if absolute == root or not absolute.is_relative_to(root):
        raise HistoryError(
            f"{where}: case_dir {str(case_dir)!r} is not inside the run directory"
        )
    return absolute.relative_to(root).as_posix()


# -- persistence -------------------------------------------------------------


def _write_manifest(run_dir: Path, payload: dict[str, object]) -> None:
    """Write the manifest atomically: temporary sibling, then ``os.replace``.

    A failed replacement leaves the previous valid manifest untouched; the
    leftover temporary file is cleaned up on a best-effort basis.
    """
    text = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    temporary = run_dir / _TEMP_MANIFEST_NAME
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, run_dir / MANIFEST_NAME)
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


def _format_timestamp(moment: datetime) -> str:
    """Render an aware datetime as ISO 8601 UTC with a ``Z`` suffix."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise HistoryError("timestamps must be timezone-aware; naive datetimes are rejected")
    return moment.astimezone(timezone.utc).strftime(_TIMESTAMP_FORMAT)


# -- encoding ----------------------------------------------------------------


def _payload(record: RunRecord) -> dict[str, object]:
    """Serialize a record into the exact, stably ordered manifest schema."""
    project = record.project
    scenario = project.scenario
    applied = record.applied_physics
    execution = record.execution
    return {
        "format_version": record.format_version,
        "run_id": record.run_id,
        "execution_status": record.execution_status,
        "started_at_utc": record.started_at_utc,
        "finished_at_utc": record.finished_at_utc,
        "application": {
            "name": record.application.name,
            "version": record.application.version,
        },
        "project": {
            "name": project.name,
            "geometry": {
                "length_m": project.geometry.length_m,
                "height_m": project.geometry.height_m,
                "mound_shape": project.geometry.mound_shape,
                "mound_fill_fraction": project.geometry.mound_fill_fraction,
            },
            "scenario": {
                "wind_speed_m_s": scenario.wind_speed_m_s,
                "wind_direction": scenario.wind_direction,
                "ventilation": {
                    "requested_on": scenario.ventilation.requested_on,
                    "modelled": scenario.ventilation.modelled,
                },
                "gas_sources": {
                    key: {
                        "mode": source.mode,
                        "requested_ppmv": source.requested_ppmv,
                        "resolved_ppmv": source.resolved_ppmv,
                        "provenance": source.provenance,
                    }
                    for key, source in scenario.gas_sources.items()
                },
                "waste_type": scenario.waste_type,
                "age_h": scenario.age_h,
                "organic_fraction": scenario.organic_fraction,
                "moisture_fraction": scenario.moisture_fraction,
            },
            "sensors": [
                {"sensor_id": sensor.sensor_id, "x_m": sensor.x_m, "y_m": sensor.y_m}
                for sensor in project.sensors
            ],
        },
        "applied_physics": {
            "wind_speed_reported_m_s": applied.wind_speed_reported_m_s,
            "inlet_speed_at_rim_m_s": applied.inlet_speed_at_rim_m_s,
            "wind_profile": applied.wind_profile,
            "wind_profile_exponent": applied.wind_profile_exponent,
            "wind_reference_height_m": applied.wind_reference_height_m,
            "nu_m2_s": applied.nu_m2_s,
            "scalar_diffusivity_m2_s": dict(applied.scalar_diffusivity_m2_s),
            "linear_solver_settings": [
                dict(entry) for entry in applied.linear_solver_settings
            ],
            "residual_targets": dict(applied.residual_targets),
            "relaxation_factors": dict(applied.relaxation_factors),
            "non_orthogonal_correctors": applied.non_orthogonal_correctors,
            "case_input_digest": applied.case_input_digest,
        },
        "execution": {
            "mesh_size_m": execution.mesh_size_m,
            "requested_end_iteration": execution.requested_end_iteration,
            "solver": execution.solver,
            "container_image": execution.container_image,
            "case_dir": execution.case_dir,
            "mesh_cells": execution.mesh_cells,
            "element_types": dict(execution.element_types),
            "exit_code": execution.exit_code,
            "failed_stage": execution.failed_stage,
            "error": execution.error,
            "solver_termination": execution.solver_termination,
        },
        "results": {
            "concentration_unit": record.results.concentration_unit,
            "sensor_readings": [
                {
                    "sensor_id": reading.sensor_id,
                    "x_m": reading.x_m,
                    "y_m": reading.y_m,
                    "values_ppmv": dict(reading.values_ppmv),
                }
                for reading in record.results.sensor_readings
            ],
        },
        "quality": {
            "classification": record.quality.classification,
            "uncertainty": record.quality.uncertainty,
            "convergence": record.quality.convergence,
            "mesh_independence": record.quality.mesh_independence,
            "mass_balance": record.quality.mass_balance,
            "experimental_validation": record.quality.experimental_validation,
            "verification_metrics": [
                _metric_payload(metric) for metric in record.quality.verification_metrics
            ],
            "validation_metrics": [
                _metric_payload(metric) for metric in record.quality.validation_metrics
            ],
        },
    }


def _metric_payload(metric: MetricRecord) -> dict[str, object]:
    return {
        "name": metric.name,
        "value": metric.value,
        "unit": metric.unit,
        "target": metric.target,
        "status": metric.status,
        "provenance": metric.provenance,
    }


# -- decoding and validation -------------------------------------------------


def _decode_manifest(payload: object, run_dir: Path) -> RunRecord:
    """Validate a manifest payload and rebuild the typed record."""
    run_dir = Path(run_dir)
    where = str(run_dir / MANIFEST_NAME)
    root = _mapping(payload, "manifest", where)
    _exact_keys(root, _TOP_LEVEL_KEYS, "manifest", where)

    version = _integer(root["format_version"], "format_version", where)
    if version != RUN_FORMAT_VERSION:
        raise HistoryError(
            f"{where}: unsupported format_version {version!r}, expected {RUN_FORMAT_VERSION}"
        )

    run_id = _text(root["run_id"], "run_id", where)
    if not RUN_DIR_PATTERN.match(run_id):
        raise HistoryError(
            f"{where}: run_id {run_id!r} must be run- followed by three or more decimal digits"
        )
    if run_id != run_dir.name:
        raise HistoryError(
            f"{where}: run_id {run_id!r} does not match its directory {run_dir.name!r}"
        )

    execution_status = _execution_status(root["execution_status"], where)
    started_at = _timestamp(root["started_at_utc"], "started_at_utc", where)
    finished_at = _finished_timestamp(root["finished_at_utc"], execution_status, where)

    application = _decode_application(root["application"], where)
    project = _decode_project(root["project"], where)
    applied_physics = _decode_applied_physics(root["applied_physics"], where)
    execution = _decode_execution(root["execution"], where)
    results = _decode_results(root["results"], where)
    quality = _decode_quality(root["quality"], where)

    if execution_status == "incomplete":
        if finished_at is not None:
            raise HistoryError(f"{where}: an incomplete run must not have a finished_at_utc")
        if (
            execution.case_dir is not None
            or execution.mesh_cells is not None
            or execution.element_types
            or execution.exit_code is not None
            or execution.failed_stage is not None
            or execution.error is not None
        ):
            raise HistoryError(f"{where}: an incomplete run must not carry execution outcome fields")
        if results.sensor_readings:
            raise HistoryError(f"{where}: an incomplete run must not carry results")
        if applied_physics.case_input_digest is not None:
            raise HistoryError(
                f"{where}: an incomplete run must not carry a case_input_digest; "
                "the digest is computed once the case exists"
            )
    elif project.sensors and execution_status == "succeeded" and not results.sensor_readings:
        # A project with sensors that produced no readings did not succeed; an
        # empty table must never be recorded as a successful empty result.
        raise HistoryError(
            f"{where}: a succeeded run for a project with sensors must carry its readings"
        )

    # Readings must describe the frozen sensors. This is re-checked on load, not
    # only at finalization, so a hand-edited or foreign manifest cannot smuggle
    # in readings for sensors it never captured.
    if results.sensor_readings:
        problem = _readings_problem(project, results.sensor_readings)
        if problem is not None:
            raise HistoryError(f"{where}: {problem}")

    return RunRecord(
        format_version=version,
        run_id=run_id,
        execution_status=execution_status,
        started_at_utc=started_at,
        finished_at_utc=finished_at,
        application=application,
        project=project,
        applied_physics=applied_physics,
        execution=execution,
        results=results,
        quality=quality,
        run_dir=run_dir,
    )


def _decode_application(payload: object, where: str) -> ApplicationRecord:
    mapping = _mapping(payload, "application", where)
    _exact_keys(mapping, _APPLICATION_KEYS, "application", where)
    return ApplicationRecord(
        name=_text(mapping["name"], "application.name", where),
        version=_text(mapping["version"], "application.version", where),
    )


def _decode_project(payload: object, where: str) -> ProjectRecord:
    mapping = _mapping(payload, "project", where)
    _exact_keys(mapping, _PROJECT_KEYS, "project", where)
    return ProjectRecord(
        name=_string(mapping["name"], "project.name", where),
        geometry=_decode_geometry(mapping["geometry"], where),
        scenario=_decode_scenario(mapping["scenario"], where),
        sensors=tuple(
            _decode_sensor(item, where)
            for item in _list(mapping["sensors"], "project.sensors", where)
        ),
    )


def _decode_geometry(payload: object, where: str) -> GeometryRecord:
    mapping = _mapping(payload, "project.geometry", where)
    _exact_keys(mapping, _GEOMETRY_KEYS, "project.geometry", where)
    shape = _text(mapping["mound_shape"], "project.geometry.mound_shape", where)
    if shape not in MOUND_SHAPES:
        raise HistoryError(
            f"{where}: project.geometry.mound_shape {shape!r} must be one of {MOUND_SHAPES}"
        )
    fill = _number(
        mapping["mound_fill_fraction"], "project.geometry.mound_fill_fraction", where
    )
    if not 0.0 < fill <= 1.0:
        raise HistoryError(
            f"{where}: project.geometry.mound_fill_fraction must be in (0, 1]"
        )
    return GeometryRecord(
        length_m=_number(mapping["length_m"], "project.geometry.length_m", where, minimum=0.0),
        height_m=_number(mapping["height_m"], "project.geometry.height_m", where, minimum=0.0),
        mound_shape=shape,
        mound_fill_fraction=fill,
    )


def _decode_scenario(payload: object, where: str) -> ScenarioRecord:
    mapping = _mapping(payload, "project.scenario", where)
    _exact_keys(mapping, _SCENARIO_KEYS, "project.scenario", where)
    direction = _text(mapping["wind_direction"], "project.scenario.wind_direction", where)
    if direction not in WIND_DIRECTIONS:
        raise HistoryError(
            f"{where}: project.scenario.wind_direction {direction!r} "
            f"must be one of {WIND_DIRECTIONS}"
        )
    ventilation = _decode_ventilation(mapping["ventilation"], where)
    sources_payload = _mapping(
        mapping["gas_sources"], "project.scenario.gas_sources", where
    )
    sources: dict[str, GasSourceRecord] = {}
    for key, source in sources_payload.items():
        gas = _text(key, "project.scenario.gas_sources key", where)
        sources[gas] = _decode_gas_source(gas, source, where)
    return ScenarioRecord(
        wind_speed_m_s=_number(
            mapping["wind_speed_m_s"], "project.scenario.wind_speed_m_s", where, minimum=0.0
        ),
        wind_direction=direction,
        ventilation=ventilation,
        gas_sources=sources,
        waste_type=_waste_type(mapping["waste_type"], where),
        age_h=_number(
            mapping["age_h"], "project.scenario.age_h", where, minimum=0.0
        ),
        organic_fraction=_number(
            mapping["organic_fraction"],
            "project.scenario.organic_fraction",
            where,
            minimum=0.0,
            maximum=1.0,
        ),
        moisture_fraction=_number(
            mapping["moisture_fraction"],
            "project.scenario.moisture_fraction",
            where,
            minimum=0.0,
            maximum=1.0,
        ),
    )


def _waste_type(value: object, where: str) -> str:
    """Decode the waste stream, refusing one this build cannot reproduce."""
    field = "project.scenario.waste_type"
    text = _text(value, field, where)
    if text not in WASTE_SPECS:
        raise HistoryError(
            f"{where}: {field} {text!r} is not a known waste stream; "
            f"expected one of {WASTE_TYPES}"
        )
    return text


def _decode_ventilation(payload: object, where: str) -> VentilationRecord:
    """Decode the ventilation request, enforcing that it is not modelled yet.

    ``modelled`` may only be ``False`` while the case generator ignores the
    flag. If a future task models ventilation it must also change this
    invariant deliberately, rather than letting a manifest imply physics that
    was never solved.
    """
    field = "project.scenario.ventilation"
    mapping = _mapping(payload, field, where)
    _exact_keys(mapping, _VENTILATION_KEYS, field, where)
    requested = _boolean(mapping["requested_on"], f"{field}.requested_on", where)
    modelled = _boolean(mapping["modelled"], f"{field}.modelled", where)
    if modelled:
        raise HistoryError(
            f"{where}: {field}.modelled must be false; casegen.write_case() does not model "
            "ventilation, so no run may record it as applied physics"
        )
    return VentilationRecord(requested_on=requested, modelled=modelled)


def _decode_gas_source(key: str, payload: object, where: str) -> GasSourceRecord:
    field = f"project.scenario.gas_sources[{key}]"
    mapping = _mapping(payload, field, where)
    _exact_keys(mapping, _GAS_SOURCE_KEYS, field, where)

    mode = _text(mapping["mode"], f"{field}.mode", where)
    if mode not in (AUTO_MODE, MANUAL_MODE):
        raise HistoryError(f"{where}: {field}.mode {mode!r} must be {AUTO_MODE!r} or {MANUAL_MODE!r}")
    requested = _optional_number(mapping["requested_ppmv"], f"{field}.requested_ppmv", where)
    resolved = _number(mapping["resolved_ppmv"], f"{field}.resolved_ppmv", where)
    provenance = _text(mapping["provenance"], f"{field}.provenance", where)

    if mode == AUTO_MODE:
        if requested is not None:
            raise HistoryError(f"{where}: {field} is automatic, so requested_ppmv must be null")
    else:
        if requested is None:
            raise HistoryError(f"{where}: {field} is manual, so requested_ppmv is required")
        if requested != resolved:
            raise HistoryError(
                f"{where}: {field} manual requested_ppmv and resolved_ppmv must match"
            )
        if provenance != MANUAL_PROVENANCE:
            raise HistoryError(
                f"{where}: {field} manual provenance must be {MANUAL_PROVENANCE!r}"
            )
    return GasSourceRecord(
        key=key,
        mode=mode,
        requested_ppmv=requested,
        resolved_ppmv=resolved,
        provenance=provenance,
    )


def _decode_sensor(payload: object, where: str) -> SensorRecord:
    mapping = _mapping(payload, "project.sensors[]", where)
    _exact_keys(mapping, _SENSOR_KEYS, "project.sensors[]", where)
    return SensorRecord(
        sensor_id=_text(mapping["sensor_id"], "project.sensors[].sensor_id", where),
        x_m=_number(mapping["x_m"], "project.sensors[].x_m", where),
        y_m=_number(mapping["y_m"], "project.sensors[].y_m", where),
    )


def _decode_applied_physics(payload: object, where: str) -> AppliedPhysicsRecord:
    field = "applied_physics"
    mapping = _mapping(payload, field, where)
    _exact_keys(mapping, _APPLIED_PHYSICS_KEYS, field, where)

    digest = mapping["case_input_digest"]
    if digest is not None:
        text = _text(digest, f"{field}.case_input_digest", where)
        if not _DIGEST_RE.match(text):
            raise HistoryError(
                f"{where}: {field}.case_input_digest {text!r} must look like sha256:<64 hex digits>"
            )
        digest = text

    exponent = _number(mapping["wind_profile_exponent"], f"{field}.wind_profile_exponent", where)
    return AppliedPhysicsRecord(
        wind_speed_reported_m_s=_number(
            mapping["wind_speed_reported_m_s"], f"{field}.wind_speed_reported_m_s", where, minimum=0.0
        ),
        inlet_speed_at_rim_m_s=_number(
            mapping["inlet_speed_at_rim_m_s"], f"{field}.inlet_speed_at_rim_m_s", where, minimum=0.0
        ),
        wind_profile=_text(mapping["wind_profile"], f"{field}.wind_profile", where),
        wind_profile_exponent=exponent,
        wind_reference_height_m=_number(
            mapping["wind_reference_height_m"], f"{field}.wind_reference_height_m", where
        ),
        nu_m2_s=_number(mapping["nu_m2_s"], f"{field}.nu_m2_s", where, minimum=0.0),
        scalar_diffusivity_m2_s=_number_mapping(
            mapping["scalar_diffusivity_m2_s"], f"{field}.scalar_diffusivity_m2_s", where
        ),
        linear_solver_settings=tuple(
            _decode_linear_solver(entry, where)
            for entry in _list(
                mapping["linear_solver_settings"], f"{field}.linear_solver_settings", where
            )
        ),
        residual_targets=_number_mapping(
            mapping["residual_targets"], f"{field}.residual_targets", where
        ),
        relaxation_factors=_number_mapping(
            mapping["relaxation_factors"], f"{field}.relaxation_factors", where
        ),
        non_orthogonal_correctors=_integer(
            mapping["non_orthogonal_correctors"], f"{field}.non_orthogonal_correctors", where, minimum=0
        ),
        case_input_digest=digest,
    )


def _decode_linear_solver(payload: object, where: str) -> dict[str, object]:
    """One ``solvers`` entry: a field pattern plus its scalar settings."""
    field = "applied_physics.linear_solver_settings[]"
    mapping = _mapping(payload, field, where)
    missing = [key for key in ("fields", "solver") if key not in mapping]
    if missing:
        raise HistoryError(f"{where}: {field} is missing {', '.join(missing)}")
    unexpected = sorted(key for key in mapping if key not in _LINEAR_SOLVER_KEYS)
    if unexpected:
        raise HistoryError(f"{where}: {field} has unknown fields {', '.join(unexpected)}")

    entry: dict[str, object] = {
        "fields": _text(mapping["fields"], f"{field}.fields", where),
        "solver": _text(mapping["solver"], f"{field}.solver", where),
    }
    for key in ("tolerance", "relTol"):
        if key in mapping:
            entry[key] = _number(mapping[key], f"{field}.{key}", where)
    for key in ("smoother", "preconditioner"):
        if key in mapping:
            entry[key] = _text(mapping[key], f"{field}.{key}", where)
    return entry


def _decode_execution(payload: object, where: str) -> ExecutionRecord:
    mapping = _mapping(payload, "execution", where)
    _exact_keys(mapping, _EXECUTION_KEYS, "execution", where)

    mesh_size_m = _number(mapping["mesh_size_m"], "execution.mesh_size_m", where)
    if mesh_size_m <= 0.0:
        raise HistoryError(f"{where}: execution.mesh_size_m must be greater than zero")
    requested_end_iteration = _integer(
        mapping["requested_end_iteration"], "execution.requested_end_iteration", where, minimum=1
    )

    return ExecutionRecord(
        mesh_size_m=mesh_size_m,
        requested_end_iteration=requested_end_iteration,
        solver=_text(mapping["solver"], "execution.solver", where),
        container_image=_text(mapping["container_image"], "execution.container_image", where),
        case_dir=_case_dir(mapping["case_dir"], where),
        mesh_cells=_optional_integer(
            mapping["mesh_cells"], "execution.mesh_cells", where, minimum=0
        ),
        element_types=_integer_mapping(
            mapping["element_types"], "execution.element_types", where, minimum=0
        ),
        exit_code=_optional_integer(mapping["exit_code"], "execution.exit_code", where),
        failed_stage=_optional_text(mapping["failed_stage"], "execution.failed_stage", where),
        error=_optional_text(mapping["error"], "execution.error", where),
        solver_termination=_closed_enum(
            mapping["solver_termination"],
            SOLVER_TERMINATION_STATES,
            "execution.solver_termination",
            where,
        ),
    )


def _case_dir(value: object, where: str) -> str | None:
    if value is None:
        return None
    text = _text(value, "execution.case_dir", where)
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        raise HistoryError(
            f"{where}: execution.case_dir {text!r} must be a relative path inside the run directory"
        )
    return path.as_posix()


def _decode_results(payload: object, where: str) -> ResultsRecord:
    mapping = _mapping(payload, "results", where)
    _exact_keys(mapping, _RESULTS_KEYS, "results", where)
    unit = _text(mapping["concentration_unit"], "results.concentration_unit", where)
    if unit != CONCENTRATION_UNIT:
        raise HistoryError(
            f"{where}: results.concentration_unit {unit!r} must be {CONCENTRATION_UNIT!r}"
        )
    readings = tuple(
        _decode_reading(item, where)
        for item in _list(mapping["sensor_readings"], "results.sensor_readings", where)
    )
    return ResultsRecord(concentration_unit=unit, sensor_readings=readings)


def _decode_reading(payload: object, where: str) -> ReadingRecord:
    field = "results.sensor_readings[]"
    mapping = _mapping(payload, field, where)
    _exact_keys(mapping, _READING_KEYS, field, where)
    return ReadingRecord(
        sensor_id=_text(mapping["sensor_id"], f"{field}.sensor_id", where),
        x_m=_number(mapping["x_m"], f"{field}.x_m", where),
        y_m=_number(mapping["y_m"], f"{field}.y_m", where),
        values_ppmv=_number_mapping(mapping["values_ppmv"], f"{field}.values_ppmv", where),
    )


def _decode_quality(payload: object, where: str) -> QualityRecord:
    mapping = _mapping(payload, "quality", where)
    _exact_keys(mapping, _QUALITY_KEYS, "quality", where)
    classification = _text(mapping["classification"], "quality.classification", where)
    if classification != QUALITY_CLASSIFICATION:
        # No run may be recorded as anything but a screening estimate; that
        # would present verification evidence as validation.
        raise HistoryError(
            f"{where}: quality.classification {classification!r} must be {QUALITY_CLASSIFICATION!r}"
        )
    return QualityRecord(
        classification=classification,
        uncertainty=_text(mapping["uncertainty"], "quality.uncertainty", where),
        convergence=_closed_enum(
            mapping["convergence"], CONVERGENCE_STATES, "quality.convergence", where
        ),
        mesh_independence=_closed_enum(
            mapping["mesh_independence"], MESH_INDEPENDENCE_STATES, "quality.mesh_independence", where
        ),
        mass_balance=_closed_enum(
            mapping["mass_balance"], MASS_BALANCE_STATES, "quality.mass_balance", where
        ),
        experimental_validation=_closed_enum(
            mapping["experimental_validation"],
            VALIDATION_STATES,
            "quality.experimental_validation",
            where,
        ),
        verification_metrics=tuple(
            _decode_metric(item, "quality.verification_metrics", where)
            for item in _list(
                mapping["verification_metrics"], "quality.verification_metrics", where
            )
        ),
        validation_metrics=tuple(
            _decode_metric(item, "quality.validation_metrics", where)
            for item in _list(mapping["validation_metrics"], "quality.validation_metrics", where)
        ),
    )


def _decode_metric(payload: object, field: str, where: str) -> MetricRecord:
    mapping = _mapping(payload, f"{field}[]", where)
    _exact_keys(mapping, _METRIC_KEYS, f"{field}[]", where)
    return MetricRecord(
        name=_text(mapping["name"], f"{field}[].name", where),
        value=_number(mapping["value"], f"{field}[].value", where),
        unit=_text(mapping["unit"], f"{field}[].unit", where),
        target=_optional_text(mapping["target"], f"{field}[].target", where),
        status=_text(mapping["status"], f"{field}[].status", where),
        provenance=_text(mapping["provenance"], f"{field}[].provenance", where),
    )


# -- primitive validation ----------------------------------------------------


def _mapping(value: object, field: str, where: str) -> dict:
    if not isinstance(value, dict):
        raise HistoryError(f"{where}: {field} must be an object")
    return value


def _list(value: object, field: str, where: str) -> list:
    if not isinstance(value, list):
        raise HistoryError(f"{where}: {field} must be an array")
    return value


def _exact_keys(mapping: dict, expected: tuple[str, ...], field: str, where: str) -> None:
    missing = [key for key in expected if key not in mapping]
    if missing:
        raise HistoryError(f"{where}: {field} is missing {', '.join(missing)}")
    unexpected = sorted(key for key in mapping if key not in expected)
    if unexpected:
        raise HistoryError(f"{where}: {field} has unknown fields {', '.join(unexpected)}")


def _string(value: object, field: str, where: str) -> str:
    if not isinstance(value, str):
        raise HistoryError(f"{where}: {field} must be a string")
    return value


def _text(value: object, field: str, where: str) -> str:
    text = _string(value, field, where)
    if not text.strip():
        raise HistoryError(f"{where}: {field} must not be empty")
    return text


def _optional_text(value: object, field: str, where: str) -> str | None:
    return None if value is None else _text(value, field, where)


def _boolean(value: object, field: str, where: str) -> bool:
    if not isinstance(value, bool):
        raise HistoryError(f"{where}: {field} must be true or false")
    return value


def _integer(value: object, field: str, where: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HistoryError(f"{where}: {field} must be an integer")
    if minimum is not None and value < minimum:
        raise HistoryError(f"{where}: {field} must be at least {minimum}")
    return value


def _optional_integer(
    value: object, field: str, where: str, *, minimum: int | None = None
) -> int | None:
    return None if value is None else _integer(value, field, where, minimum=minimum)


def _number(
    value: object,
    field: str,
    where: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoryError(f"{where}: {field} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise HistoryError(f"{where}: {field} must be finite, got {value!r}")
    if minimum is not None and number < minimum:
        raise HistoryError(f"{where}: {field} must be at least {minimum}")
    if maximum is not None and number > maximum:
        raise HistoryError(f"{where}: {field} must be at most {maximum}")
    return number


def _optional_number(value: object, field: str, where: str) -> float | None:
    return None if value is None else _number(value, field, where)


def _integer_mapping(
    value: object, field: str, where: str, *, minimum: int | None = None
) -> dict[str, int]:
    mapping = _mapping(value, field, where)
    return {
        _text(key, f"{field} key", where): _integer(item, f"{field}[{key}]", where, minimum=minimum)
        for key, item in mapping.items()
    }


def _number_mapping(value: object, field: str, where: str) -> dict[str, float]:
    mapping = _mapping(value, field, where)
    return {
        _text(key, f"{field} key", where): _number(item, f"{field}[{key}]", where)
        for key, item in mapping.items()
    }


def _execution_status(value: object, where: str) -> ExecutionStatus:
    if value not in EXECUTION_STATUSES:
        raise HistoryError(f"{where}: execution_status {value!r} must be one of {EXECUTION_STATUSES}")
    return value  # type: ignore[return-value]


def _closed_enum(value: object, allowed: tuple[str, ...], field: str, where: str) -> str:
    """A gate state drawn from its closed set; free text can never imply a pass."""
    text = _text(value, field, where)
    if text not in allowed:
        raise HistoryError(f"{where}: {field} {text!r} must be one of {allowed}")
    return text


def _timestamp(value: object, field: str, where: str) -> str:
    text = _text(value, field, where)
    if not _TIMESTAMP_RE.match(text):
        raise HistoryError(
            f"{where}: {field} {text!r} must be an ISO 8601 UTC timestamp like 2026-09-19T12:34:56Z"
        )
    try:
        datetime.strptime(text, _TIMESTAMP_FORMAT)
    except ValueError as error:
        raise HistoryError(f"{where}: {field} {text!r} is not a real UTC timestamp: {error}") from error
    return text


def _finished_timestamp(value: object, status: str, where: str) -> str | None:
    if value is None:
        if status != "incomplete":
            raise HistoryError(f"{where}: finished_at_utc is required once status is {status!r}")
        return None
    if status == "incomplete":
        raise HistoryError(f"{where}: finished_at_utc must be null while status is 'incomplete'")
    return _timestamp(value, "finished_at_utc", where)
