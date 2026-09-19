# GOAL

Implement the next smallest meaningful engineering feature: **persistent run history with an immutable, provenance-bearing manifest for every simulation attempt** (T-030).

A run must remain identifiable and inspectable after Scentinel restarts. Starting a run reserves a non-colliding `run-NNN` directory and writes its exact inputs; completion atomically adds outcome and probe results. The manifest is the stable input to later comparison and reporting work. This feature does not add a history browser, comparison view, PDF generation, or new CFD physics.

# CURRENT STATE

- `README.md` states that geometry, meshing, case generation, solving, probe sampling, and CSV export work end to end; scenario comparison is absent because runs are not collected into history.
- `docs/ROADMAP.md` marks F3.1, the run history manager, not started. `docs/TASKS.md` defines T-030 as persistence of run id, project name, timestamp, case directory, and probe summary next to the project.
- `src/scentinel/ui/main_window.py:296-325` increments the process-local `_run_counter`, chooses `runs/run-NNN`, and launches `SolverWorker`. `_run_counter` resets to zero on every application start, so an existing directory can be reused and its generated files overwritten.
- `_runs_root()` places saved-project runs in `<project-parent>/runs`; unsaved-project runs go in `<cwd>/runs`.
- `src/scentinel/ui/solver_worker.py` already exposes the needed terminal outcome in `RunOutcome`: `case_dir`, raw scalar readings, mesh cell count, element types, process exit code, failed stage, and error text. Worker defaults are mesh size `0.25 m` and OpenFOAM end iteration `500`.
- `src/scentinel/core/project.py` serializes reproducible geometry, scenario, and sensor inputs. `Scenario.gas_sources` preserves whether each source was manual or `"auto"`.
- `casegen.resolve_sources()` converts source values from ppmv to dimensionless volume fraction. `gas_data.citation()` exposes the provenance of each cited automatic gas default.
- `post.SensorReading.values` are dimensionless volume fractions. `MainWindow._on_run_finished()` multiplies them by `1e6` before presenting ppmv in the results panel.
- Run directories and CFD artefacts are intentionally ignored by git. There is no history module, manifest schema, persistent run-id allocator, or history test.
- Repository history has three commits: `82b1e00` initial scaffold, `34d5300` end-to-end CFD pipeline, and `099e74e` architecture/roadmap/task documentation. The architect branch was clean before this contract was created.
- Verification is not validation. The repository currently documents a failed mesh-independence verification gate (documented worst deviation `76.5%` against a `<10%` target), an unautomated mass-balance gate, and no empirical validation against measurements. Ordinary simulation results therefore remain screening estimates.

# PROBLEM

The current directory name is not a durable run identity. Restarting the application resets numbering, and running again can target `run-001` even when it already exists. Nothing records the exact project snapshot, resolved automatic gas values, numerical settings, solver identity, outcome, units, or known uncertainty beside the generated case. Consequently:

- previous runs cannot be reliably discovered or looked up by id;
- a run cannot be audited without reconstructing state from mutable project/UI data;
- automatic source values lose their citation and resolved numeric value;
- downstream comparison or reporting would have to guess units and result quality;
- failed and cancelled attempts disappear from history; and
- verification evidence could be incorrectly presented as validation.

The fix is an append-only run-directory protocol with one versioned JSON manifest per run. A central mutable index is explicitly rejected: scanning immutable per-run manifests avoids index/manifest divergence and keeps each run portable with its case.

# SCIENTIFIC ASSUMPTIONS

- This feature does not change geometry, meshing, boundary conditions, turbulence, scalar transport, sampling, or solver convergence behaviour.
- Coordinates and bin dimensions are metres. Wind speed is metres per second. `mound_fill_fraction` is dimensionless.
- Scenario gas inputs entered in the UI are ppmv. OpenFOAM scalar fields and `post.SensorReading.values` are dimensionless volume fractions. Persisted human-facing source and probe values are ppmv and must be converted exactly once using the existing factor `1e6`.
- An `"auto"` source is resolved with the existing `casegen.resolve_sources()`/`gas_data` path at run start. The manifest stores both the requested mode and the resolved ppmv value so later changes to defaults cannot rewrite history.
- Manual source values are user inputs. Their provenance is the single literal `"user input"`; no citation may be fabricated.
- `end_time=500` in the steady `simpleFoam` case is an iteration/control index, not elapsed physical seconds, and not evidence that `residualControl` was satisfied. The manifest field is therefore named `requested_end_iteration`, with unit `iteration`, even though the existing worker argument remains named `end_time` internally. Nothing parses the achieved residuals, so `solver_termination` and `quality.convergence` record `not_evaluated`; exit code 0 is never convergence.
- A normal production run does not calculate a mesh-independence, mass-balance, analytical benchmark, or empirical validation metric. Its `verification_metrics` and `validation_metrics` are separate arrays and are empty unless a real metric was produced for that run.
- The reported wind speed is not the applied inlet speed: `casegen.wind_speed_at()` scales it to the bin rim by a power law before writing the inlet boundary. The manifest records both, plus the profile type, exponent, and reference height.
- The case applies each gas's own Fuller-Schettler-Giddings scalar diffusivity (`casegen.scalar_diffusivity(gas)`, sourced from `gas_data`), and `applied_physics.scalar_diffusivity_m2_s` persists exactly that per-gas mapping.
- Every manifest carries the known qualitative uncertainty: `screening_estimate`; absolute concentrations are not mesh-converged and must not be represented as calibrated predictions.
- No new emission rate, molecular weight conversion, mass-transfer coefficient, uncertainty percentage, or other scientific constant is introduced by this feature.

# INPUTS

`begin_run()` receives:

- `runs_root: Path`, from the existing `_runs_root(project_path)` policy;
- a snapshot of `Project` containing project name, `BinGeometry`, `Scenario`, and ordered sensors;
- `mesh_size_m: float`, currently `0.25`;
- `end_iteration: int`, currently `500` (persisted as `requested_end_iteration`);
- application version from `scentinel.__version__`;
- solver name and fully qualified container image from `casegen.SOLVER` and `casegen.IMAGE`.

`finish_run()` receives primitive/core values only, not a Qt or UI type:

- reserved run id and run directory;
- one terminal execution status: `succeeded`, `failed`, or `cancelled`;
- `solver_termination`, from a closed set, defaulting to `not_evaluated`;
- `case_dir`, if created;
- mesh cell count and element-type counts;
- exit code, failed stage, and error text;
- ordered sensor readings converted to ppmv before persistence, which must match the frozen sensor snapshot in ids, coordinates, order, and gas keys; and
- completion time from an injectable/default UTC clock.

The history module must not import `PySide6`, `MainWindow`, `SolverWorker`, or `RunOutcome`. It also must not require the optional `cfd` extra: `history` imports `casegen`, which imports `mesh` (and therefore `gmsh`) only under `TYPE_CHECKING`, because the documented read API performs no meshing.

`history.snapshot_project(project)` returns a deep, independent copy of a `Project`. The UI takes exactly one such copy per run and gives it to both `begin_run()` and `SolverWorker`, so the sensors the record freezes are the sensors the pipeline samples.

# OUTPUTS

Each attempt creates:

- `<runs_root>/run-NNN/`, reserved atomically and never reused;
- `<runs_root>/run-NNN/run.json`, UTF-8 JSON with a trailing newline; and
- the existing `mesh/` and `case/` children produced by the current pipeline.

`run.json` is written once in `incomplete` state before the solver starts, then atomically replaced at terminal completion. A process crash leaves an honest `incomplete` record rather than no record or a false success.

The core history API returns typed records in ascending numeric run-id order and supports lookup by exact id. Missing history roots produce an empty collection, not an exception. A malformed manifest is an explicit error from strict load/lookup; it must not be silently accepted as a valid run.

No new visible history screen is produced. Existing results-table and CSV behaviour remains unchanged. The solver log records the reserved run id and manifest path for auditability.

# DATA STRUCTURES

Add `src/scentinel/core/history.py` with these public constants and types:

- `RUN_FORMAT_VERSION = 2` (version 1 manifests are rejected, not migrated)
- `MANIFEST_NAME = "run.json"`
- `RUN_DIR_PATTERN`, matching only `run-` plus three or more decimal digits
- `ExecutionStatus = Literal["incomplete", "succeeded", "failed", "cancelled"]`
- closed-enum gate state tuples: `CONVERGENCE_STATES`, `MESH_INDEPENDENCE_STATES`, `MASS_BALANCE_STATES`, `VALIDATION_STATES`, `SOLVER_TERMINATION_STATES`
- `NO_READINGS_ERROR`, the audit reason for a clean exit with missing readings
- frozen `RunRecord`, containing the validated manifest fields below plus `run_dir: Path` as a non-serialized convenience
- `HistoryError(ValueError)` for invalid schema/version/status/id/unit-bearing fields

Public functions:

- `begin_run(runs_root, project, *, mesh_size_m, end_iteration, started_at=None) -> RunRecord`
- `finish_run(record, *, status, case_dir, mesh_cells, element_types, exit_code, failed_stage, error, readings_ppmv, finished_at=None, solver_termination="not_evaluated") -> RunRecord`
- `load_run(run_dir: Path) -> RunRecord`
- `list_runs(runs_root: Path) -> list[RunRecord]`
- `get_run(runs_root: Path, run_id: str) -> RunRecord | None`
- `snapshot_project(project: Project) -> Project`

The serialized top-level schema is exact; names carrying physical quantities include their units.

**Amendment (integration, post-final-review):** the schema below is now version
2. The review accepted four merge blockers against version 1, and the accepted
fixes are folded in here: `applied_physics` (MB-1), the qualified `ventilation`
structure (MB-2), the renamed `execution_status` plus closed-enum gate states
(MB-4), and `requested_end_iteration`/`solver_termination`. Version 1 manifests
are rejected rather than misread, because they cannot describe what they
applied. Reading validation against the frozen sensor snapshot (MB-3) is a rule
below rather than a new field.

```json
{
  "format_version": 2,
  "run_id": "run-001",
  "execution_status": "succeeded",
  "started_at_utc": "2026-09-19T12:34:56Z",
  "finished_at_utc": "2026-09-19T12:36:12Z",
  "application": {
    "name": "scentinel",
    "version": "0.1.0"
  },
  "project": {
    "name": "Example",
    "geometry": {
      "length_m": 6.0,
      "height_m": 2.5,
      "mound_shape": "mounded",
      "mound_fill_fraction": 0.45
    },
    "scenario": {
      "wind_speed_m_s": 2.0,
      "wind_direction": "left-to-right",
      "ventilation": {"requested_on": false, "modelled": false},
      "gas_sources": {
        "CO": {
          "mode": "auto",
          "requested_ppmv": null,
          "resolved_ppmv": 105.0,
          "provenance": "<existing gas_data.citation('CO') result>"
        }
      }
    },
    "sensors": [
      {"sensor_id": "S1", "x_m": 1.2, "y_m": 2.1}
    ]
  },
  "applied_physics": {
    "wind_speed_reported_m_s": 2.0,
    "inlet_speed_at_rim_m_s": 1.640670712015276,
    "wind_profile": "power-law",
    "wind_profile_exponent": 0.14285714285714285,
    "wind_reference_height_m": 10.0,
    "nu_m2_s": 1.5e-05,
    "scalar_diffusivity_m2_s": {"CO": 2e-05},
    "linear_solver_settings": [
      {"fields": "p", "solver": "GAMG", "tolerance": 1e-06, "relTol": 0.1, "smoother": "GaussSeidel"},
      {"fields": "\"(CO)\"", "solver": "PBiCGStab", "preconditioner": "DILU", "tolerance": 1e-08, "relTol": 0.1}
    ],
    "residual_targets": {"p": 0.001, "U": 0.0001, "\"(k|epsilon)\"": 0.0001, "\"(CO)\"": 1e-05},
    "relaxation_factors": {"U": 0.9, "\".*\"": 0.9},
    "non_orthogonal_correctors": 0,
    "case_input_digest": "sha256:<64 lowercase hex digits>"
  },
  "execution": {
    "mesh_size_m": 0.25,
    "requested_end_iteration": 500,
    "solver": "simpleFoam",
    "container_image": "docker.io/opencfd/openfoam-default:2512",
    "case_dir": "case",
    "mesh_cells": 7248,
    "element_types": {"Hexahedron 8": 7248},
    "exit_code": 0,
    "failed_stage": null,
    "error": null,
    "solver_termination": "not_evaluated"
  },
  "results": {
    "concentration_unit": "ppmv",
    "sensor_readings": [
      {"sensor_id": "S1", "x_m": 1.2, "y_m": 2.1, "values_ppmv": {"CO": 0.465}}
    ]
  },
  "quality": {
    "classification": "screening_estimate",
    "uncertainty": "Absolute concentrations are not mesh-converged; use results for relative screening only.",
    "convergence": "not_evaluated",
    "mesh_independence": "not_run",
    "mass_balance": "not_run",
    "experimental_validation": "not_run",
    "verification_metrics": [],
    "validation_metrics": []
  }
}
```

Schema rules:

- `finished_at_utc` is `null`, execution outcome fields are `null`/empty, results are empty, and `applied_physics.case_input_digest` is `null` while `execution_status` is `incomplete`.
- UTC timestamps use ISO 8601 with `Z`; naive datetimes are rejected.
- `case_dir` is `"case"` relative to the run directory, never an absolute workstation path. It is `null` if case generation never completed.
- Gas and sensor order follows the captured project/readings order. JSON output uses stable indentation and key ordering for reviewability.
- Manual gas input uses `mode: "manual"`, the entered number in both `requested_ppmv` and `resolved_ppmv`, and `provenance: "user input"`. (The review's m1 finding: the literal is `"user input"`, not `user`.)
- Automatic input uses `mode: "auto"`, `requested_ppmv: null`, resolved existing-data value in `resolved_ppmv`, and the exact existing citation string. Auto ppmv comes from `gas_data.source_concentration(gas)` directly and equals `casegen.resolve_sources()[gas] / casegen.PPM_SCALE`.
- `ventilation` is a request-plus-effect pair (MB-2). `modelled` is `false` and `load_run()` rejects `true`: `casegen.write_case()` does not read the flag. No consumer may group or difference by an unmodelled factor. T-030 does not model ventilation.
- `applied_physics` records the experiment, not the request (MB-1). Every value is read from the same `casegen` constant or helper that renders the case files, so the block cannot claim a setting the case does not use. `scalar_diffusivity_m2_s` is the per-gas mapping actually written into each `scalarTransport` object (`casegen.scalar_diffusivity(gas)`).
- `case_input_digest` is SHA-256 over the *declared* generated case inputs (`casegen.case_input_paths`), sorted by relative POSIX path, feeding path + `NUL` + decimal byte size + `NUL` + bytes per file. It covers only what `write_case()` generated, never the solver's own output into the same tree, so it stays valid after a solve. It is the authoritative guard for "same applied experiment": a changed applied constant changes it at identical UI inputs.
- `requested_end_iteration` is the requested `controlDict.endTime` — an iteration index, not elapsed seconds and not evidence the targets were met. `solver_termination` and `quality.convergence` stay `not_evaluated` because nothing parses the achieved residuals; exit code 0 must never be recorded as convergence.
- `execution_status: "succeeded"` is a process outcome only: the container pipeline exited 0 and every frozen sensor was sampled. Convergence, mesh independence, mass balance, and experimental validation are separate closed-enum gate states in `quality`, all non-passing for an ordinary run.
- Supplied readings must match the frozen sensor snapshot in ids, coordinates, order, and gas keys. A mismatch is a `HistoryError` — nothing is persisted. *Absent* readings after a clean exit are recorded as `failed` with `NO_READINGS_ERROR` as `execution.error`, so an exit-0 failure is auditable. `load_run()` re-applies the same check.
- Failed/cancelled records preserve available mesh/case/output metadata but never fabricate absent readings.
- Verification metric entries, when future workflows add them, use `{name, value, unit, target, status, provenance}`. Validation metric entries use the same shape but remain in the separate `validation_metrics` array.

# ARCHITECTURE

`core.history` owns allocation, schema validation, serialization, atomic replacement, discovery, and lookup. It may import the existing core project, case-generation, gas-data, and package-version modules. It has no Qt dependency.

Run allocation uses the filesystem as the concurrency authority:

1. Ensure `runs_root` exists.
2. Scan directory names matching `RUN_DIR_PATTERN` and choose one greater than the current maximum, starting at `run-001`.
3. Reserve with `mkdir(exist_ok=False)`.
4. If another process wins that id, increment and retry; never delete, clear, or reuse a directory.
5. Build a deep input snapshot, resolve gas sources, capture the applied-physics block (digest still `null`), write `run.json` atomically, and return the incomplete `RunRecord`.

The digest cannot be computed at reservation time because the case does not exist yet. `finish_run()` fills it in from `casegen.case_input_digest()` when the case is complete, and leaves it `null` when it is not.

Atomic manifest writes use a temporary sibling file followed by `os.replace()`. Cleanup of a leftover temporary file is best-effort; the previous valid manifest must survive a failed replacement.

`MainWindow` owns orchestration only:

- remove `_run_counter`;
- take exactly one `history.snapshot_project()` copy after the existing sensor/gas/solver preconditions, and pass that same copy to `begin_run()` and to `SolverWorker` — never the live editor model, so a mid-run edit cannot change what the record claims to have measured;
- disable the viewport as well as the setup panel and run action while a run is in flight, as UX defence only, not as the correctness mechanism;
- pass the reserved directory and the same explicit mesh size/end iteration to the worker;
- retain the active `RunRecord` until `_on_run_finished()`;
- map `RunOutcome` to `finish_run()` primitives and convert raw reading volume fractions to ppmv exactly once;
- finalize cancelled and failed attempts as well as successful attempts; and
- continue displaying successful readings through the current `ResultsPanel` path.

The conversion factor comes from `casegen.PPM_SCALE` rather than a literal `1e6`, so the case writer's ppm-to-fraction convention and the persisted ppmv conversion cannot drift apart.

If `begin_run()` fails, no worker starts and the UI reports a localized history-write error. If finalization fails, the solver outcome and table remain available, but the UI must report that the run was not durably recorded; it must not claim normal completion. Add equivalent English and Indonesian locale keys.

Do not add a repository/database abstraction, SQLite, a mutable index file, migrations framework, background history thread, or UI model. JSON manifests are small and all history I/O occurs only at run boundaries.

# FILES AFFECTED

Planned implementation files:

- `src/scentinel/core/history.py` — new run schema, allocation, atomic persistence, load/list/lookup.
- `src/scentinel/ui/main_window.py` — replace process-local numbering; begin and finalize records around the existing worker.
- `src/scentinel/ui/solver_worker.py` — expose named default mesh/end-iteration constants if needed so UI and persisted execution settings cannot diverge; no history import.
- `src/scentinel/core/casegen.py` — own the applied-physics constants and the case-input digest; `write_case()` takes a required `geom` so the inlet speed and the persisted reference height cannot diverge; keep the `mesh` import behind `TYPE_CHECKING`.
- `src/scentinel/resources/locales/en.json` — history persistence status/error text.
- `src/scentinel/resources/locales/id.json` — equivalent Indonesian keys.
- `tests/unit/test_history.py` — new core behavioural tests.
- `tests/ui/test_main_window.py` — orchestration regression tests with the worker/history boundary stubbed, not the CFD pipeline.
- `README.md`, `docs/ROADMAP.md`, and `docs/TASKS.md` — after implementation, update status from “history absent” to persisted history available; do not claim comparison UI exists.

This architecture task itself modifies only `docs/orchestration/current-contract.md`.

# UX FLOW

1. The user configures the current project, places at least one sensor, and selects at least one gas as today.
2. The user presses **Run Simulation**.
3. Existing precondition checks run. If they pass, Scentinel reserves the next unused run id and writes an incomplete manifest before any meshing work.
4. The solver log shows the run id and manifest path, then the existing mesh/case/solve/sample progress.
5. On success, Scentinel shows the same ppmv results table and atomically finalizes the manifest with `succeeded`, exact inputs, execution metadata, provenance, quality classification, and readings.
6. On cancellation or failure, Scentinel keeps the existing status behaviour and finalizes the same record with `cancelled` or `failed` plus all metadata available at that point.
7. Closing and reopening Scentinel does not reset identity. The next run uses an id greater than every existing matching run directory, including incomplete or malformed runs.
8. No history-selection UI is introduced. A later comparison view consumes `list_runs()`/`get_run()`.

# FAILURE MODES

- **Existing run directories:** never overwrite. Exact matching names participate in allocation even when their manifest is missing or corrupt. Unrelated directory names are ignored.
- **Concurrent Scentinel processes:** `mkdir(exist_ok=False)` is the lock; losing allocation retries the next id.
- **Manifest cannot be written at start:** remove only the just-reserved empty directory if it is still empty; do not start CFD; show a localized error.
- **Manifest finalization fails:** preserve the last valid incomplete manifest, retain/display solver results, log the exception, and show completion-with-history-error rather than normal success.
- **Application/process crash:** the pre-run manifest remains `incomplete`; no startup code silently changes it to another status.
- **Malformed JSON, unsupported version, invalid run id/status, missing required fields, or non-finite numeric values:** `load_run()` raises `HistoryError` naming the manifest and problem. `list_runs()` must not silently omit the bad record; it raises at the first invalid manifest in numeric order.
- **Missing history root:** `list_runs()` returns `[]`; `get_run()` returns `None`.
- **Missing requested id:** `get_run()` returns `None`. Invalid id syntax raises `HistoryError` rather than allowing path traversal.
- **Case path portability:** only a validated relative child path is stored; absolute paths and paths containing `..` are rejected.
- **Unknown gas key or unresolved `auto` value:** abort before solver start through the existing gas-data error; do not write a misleading resolved source.
- **NaN or infinity:** reject before JSON serialization; JSON must use standard finite numbers only (`allow_nan=False`).
- **No probe readings after a successful solve:** a clean exit with no readings for a project whose snapshot has sensors is recorded as `failed` with `NO_READINGS_ERROR` as `execution.error`, never as a successful empty result and never as an opaque exit-0 failure. A project snapshot with no sensors legitimately records `succeeded` with an empty array.
- **Readings that do not match the frozen sensors:** ids, coordinates, order, or gas keys differing from the snapshot is a `HistoryError`; nothing is persisted, and `load_run()` raises on such a manifest too.
- **Scientific-quality misuse:** manifest classification remains `screening_estimate`; every gate state is drawn from a closed set; empty verification/validation arrays never imply a passed gate. `execution_status` is a process outcome and must never be read as convergence or validation.
- **Unmodelled factor presented as physics:** `ventilation.modelled` may only be `false` while `casegen.write_case()` ignores the flag; `load_run()` rejects `true`, and no consumer may group or difference by `ventilation.requested_on` while it is `false`.
- **Optional dependency leak:** importing `scentinel.core.history` without `gmsh` or `PySide6` installed must succeed, and the documented read API must work there.

# TEST PLAN

Core tests in `tests/unit/test_history.py`:

1. `begin_run()` on an empty root creates `run-001/run.json` in incomplete state and round-trips exact geometry, scenario, ordered sensors, execution settings, app/solver identity, and explicit units.
2. Restart simulation by calling allocation with pre-existing `run-001` and `run-003`; it reserves `run-004`, proving ids are persistent and based on the maximum rather than count.
3. A pre-existing matching directory without a manifest is never reused.
4. Simulated `FileExistsError` during reservation retries the next id, covering concurrent allocators.
5. Auto and manual sources preserve distinct modes, existing citation/user provenance, and correctly resolved ppmv without changing `Scenario`.
6. `finish_run()` atomically produces success, failure, and cancellation records with the correct nullable fields; raw input to this function is already ppmv, so there is no second conversion.
7. `list_runs()` orders `run-002` before `run-010`; `get_run()` returns the requested record; a missing root/id has the documented empty result.
8. Unsupported version, malformed JSON, invalid status/id, non-finite numbers, absolute/escaping case paths, and missing unit-bearing fields raise `HistoryError`.
9. A forced replacement failure leaves the prior valid incomplete manifest readable.
10. Verification and validation arrays remain distinct through serialization; an empty array is not rewritten as a pass.
11. Applied physics: each persisted applied value is compared against the generated case source; a changed applied constant changes the recorded digest at identical UI inputs; the requested wind speed and the applied inlet speed differ; the applied per-gas diffusivity is the written constant, not `gas_data`'s unused table.
12. The digest covers only declared case inputs: solver output written into the same tree (`constant/polyMesh`, `VTK/`, `log.*`) does not change it, and a missing declared input raises.
13. Ventilation: `requested_on` is preserved, `modelled` is `false`, and a manifest claiming `modelled: true` is rejected.
14. Readings identity: a reading for a different sensor, at moved coordinates, for an unselected gas, or in the wrong order/count is rejected at finalization and on load; a reading-less clean exit is `failed` with `NO_READINGS_ERROR`.
15. Gates: a clean exit leaves `convergence`, `mesh_independence`, `mass_balance`, and `experimental_validation` non-passing; a state outside its closed set is rejected; the documented `76.5%` mesh-independence failure does not appear on an ordinary run.
16. ppmv recipes: CO auto `105.0`, CH₄ auto `500000.0`, manual VOC `12.5`, and a probe volume fraction converted exactly once; `Scenario` is not mutated.
17. The module imports, and the documented read API runs, with `gmsh` and `PySide6` both unavailable.

UI tests in `tests/ui/test_main_window.py`:

1. Starting a valid run calls `begin_run()` before constructing the worker and passes the reserved directory plus the exact persisted mesh size/end iteration.
2. Successful worker completion finalizes once, converts each raw volume fraction to ppmv once, and keeps the displayed table equal to persisted readings.
3. Failed and cancelled outcomes finalize with their respective statuses.
4. Start-persistence failure does not launch a worker and shows the localized error state.
5. Finalization failure preserves the result table but shows/logs the history-recording failure.
6. The worker receives a frozen snapshot, not the live project: mutating the project mid-run does not change what the worker samples or what the record stores.
7. The editing surfaces (viewport, setup panel) are disabled while a run is in flight and restored afterwards.
8. A successful run still reports every scientific gate as non-passing.

Verification commands:

- `pytest tests/unit/test_history.py tests/ui/test_main_window.py`
- `pytest -m "not integration and not verification"`
- Headless UI remains covered by the existing `QT_QPA_PLATFORM=offscreen` setup.
- No CFD integration or physics verification run is required because this feature does not change generated cases or numerical behaviour.

# ACCEPTANCE CRITERIA

- Every simulation attempt that passes existing UI preconditions reserves a unique, never-reused `run-NNN` directory before work starts.
- Existing run data survives application restart and subsequent runs; no in-memory counter determines identity.
- Every reserved run has a versioned `run.json` containing its immutable input snapshot, automatic/manual source provenance, explicit units, the applied numerical experiment with a case-input digest, the requested iteration count, solver/container identity, terminal execution status, available output metadata, results in ppmv, and screening uncertainty.
- Requested inputs and applied physics are recorded separately: the manifest states the inlet speed actually applied and the constants actually written, not just the controls the user chose.
- Execution success is separate from convergence, mesh independence, mass balance, and experimental validation; each has its own closed-enum state, non-passing for an ordinary run.
- A run's readings provably describe the sensors the record froze; a mismatch is rejected rather than persisted.
- Successful, failed, cancelled, and crash-interrupted attempts are distinguishable without inspecting logs.
- `list_runs()` and `get_run()` can discover and retrieve records after a fresh process starts.
- Manifest updates are atomic; a failed final write does not destroy the valid incomplete record.
- Verification metrics and validation metrics are represented separately. No ordinary run is marked verified or validated merely because the solver exited successfully.
- The history read API works without the optional `cfd` extra or a GUI toolkit.
- Existing results-table and CSV values remain unchanged and equal the persisted ppmv values.
- Both locale files contain any new user-visible status/error strings.
- The focused core/UI tests and the existing non-integration, non-verification suite pass.
- Documentation says run persistence exists but continues to state that comparison UI and PDF reporting do not exist and that absolute concentrations are screening estimates.

# OUT OF SCOPE

- Scenario comparison UI, plots, difference columns, ranking, or recommendation logic.
- PDF or additional CSV report formats.
- Field visualisation, cut planes, or streamlines.
- Changes to the mass-flux source, mesh refinement, mass balance, analytical benchmarks, solver settings, or any scientific constant. (The integration fixes *record* the applied constants; they change none of them, and they do not add a molecular weight, mass-transfer coefficient, emission rate, or uncertainty percentage.)
- Modelling ventilation (T-025). T-030 records it as requested-but-unmodelled; implementing it is separate work.
- Parsing solver residuals or a termination reason beyond recording `not_evaluated`. Residual/termination parsing is deferred until it is actually implemented.
- Reproducible Scrapling acquisition manifests, first-cell-height verification records, and probe containment diagnostics. Each is valid future architecture, not T-030 scope.
- Claiming mesh independence, calibration, empirical validation, or suitability for hardware-placement decisions.
- Editing the project-file format or embedding history inside `.scentinel`.
- Importing old unmanifested run directories as if their inputs were known.
- Deleting/pruning runs, renaming run ids, mutable history metadata, tags, notes, or search.
- SQLite, a central index, cloud sync, locking beyond atomic directory reservation, or multi-host coordination.
- Expanding Scentinel beyond the CFD sensor-placement studio.

# IMPLEMENTATION ORDER

1. Add `core.history` data model, strict validation, stable JSON encode/decode, and atomic write helper.
2. Implement filesystem-backed run reservation with collision retry, then `load_run()`, `list_runs()`, and `get_run()`.
3. Implement gas-source snapshot/provenance and `begin_run()`; confirm all physical values have unit-bearing field names.
4. Implement terminal `finish_run()` for success, failure, and cancellation while preserving incomplete manifests on write failure.
5. Add focused core tests, including restart/collision, malformed data, atomic failure, units/provenance, and verification-versus-validation separation.
6. Replace `MainWindow._run_counter` with `begin_run()` orchestration; pass one explicit set of execution parameters to both manifest and worker.
7. Finalize the active record in `_on_run_finished()`, sharing the same one-time ppmv conversion used by the table.
8. Add bilingual persistence failure/status messages and UI orchestration tests.
9. Run the focused tests, then the full non-integration/non-verification suite.
10. Update README/roadmap/task status without claiming comparison or scientific validation, and manually inspect a generated manifest from a stubbed/real run for portability and readable provenance.

## POST-REVIEW INTEGRATION FIXES (applied)

The final review accepted four merge blockers and several required fixes. The
integration pass applied them in this order, each with its own tests:

1. **MB-1 applied physics.** `casegen` gained named constants for the wind
   profile, viscosity, scalar diffusivity, linear-solver tolerances, residual
   targets, and relaxation factors, and renders both the case files and the
   persisted `applied_physics` block from them. Added
   `casegen.case_input_paths()` / `casegen.case_input_digest()` and the
   `applied_physics.case_input_digest` field. `write_case()` now requires
   `geom`, so the inlet speed and the persisted reference height cannot diverge.
2. **MB-2 ventilation.** `ScenarioRecord.ventilation_on` became
   `VentilationRecord(requested_on, modelled)`; `load_run()` rejects
   `modelled: true`.
3. **MB-3 frozen sensors.** Added `history.snapshot_project()`; `MainWindow`
   passes one snapshot to both `begin_run()` and the worker; the viewport is
   disabled while running; `finish_run()` and `load_run()` both validate
   readings against the frozen snapshot.
4. **MB-4 execution versus evidence.** The top-level field is
   `execution_status`; `quality` gained `convergence`, `mesh_independence`,
   `mass_balance`, and `experimental_validation` as closed-enum states;
   `requested_end_iteration` and `solver_termination` replaced the unqualified
   `end_iteration`.
5. **Required fixes.** `"user input"` is the single documented manual
   provenance literal; a reading-less clean exit persists `NO_READINGS_ERROR`;
   the `mesh`/`gmsh` import moved behind `TYPE_CHECKING` so the read API works
   without the `cfd` extra; and one manifest generated without module stubs was
   inspected (see the integration record).

Deferred, deliberately not implemented: ventilation physics (T-025), residual
and termination parsing, Scrapling acquisition manifests, first-cell-height
verification records, and probe containment diagnostics.
