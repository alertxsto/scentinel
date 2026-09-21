# Scentinel — Architecture

**Version:** 0.2.3 · **Last updated:** 2026-09-21

How the application is put together: what each module owns, how data flows from
a click in the viewport to a concentration in the results table, and which
decisions are load-bearing.

Related documents: [ROADMAP.md](ROADMAP.md) for phases and open tasks,
[TASKS.md](TASKS.md) for the work breakdown, [references.md](references.md) for
data provenance.

---

## 1. Layers

```
┌──────────────────────────────────────────────────────────────────┐
│  PySide6 desktop app                                             │
│                                                                  │
│  SetupPanel ─────┐                                               │
│  (geometry,      │  changed(BinGeometry, Scenario)               │
│   scenario,      ├──────────────────────────────► MainWindow     │
│   gas sources)   │                                (owns Project) │
│                  │                                     │         │
│  ViewportWidget ─┘  sensors_changed()                   │ Project │
│  (click to place,                                       │         │
│   right-click to remove)                                ▼         │
│                                              SolverWorker        │
│  ResultsPanel ◄──── log / progress / readings                 │  │
│  (probe table, log pane, export)                              │  │
└───────────────────────────────────────────────────────────────┼──┘
                                                                │
   runs/run-NNN/                                                │
     run.json             ◄── core.history  (reserved, then atomically
     mesh/  case.msh      ◄── core.mesh    (gmsh, child process) ─┘
     case/  0/ constant/ system/  ◄── core.casegen
     case/VTK/…           ◄── core.runner  (podman) + core.post
```

The UI never calls gmsh, podman, or pyvista directly. `SolverWorker` runs the
whole pipeline off the GUI thread and reports back with signals. `MainWindow`
snapshots the project, reserves the run directory through `core.history` before
the worker is constructed, and finalizes the same record afterwards, so the run
identity never depends on process-local state and the sensors a record claims
are the sensors the pipeline sampled. `core.casegen` owns the applied numerical
constants and the case-input digest; `core.history` persists what `casegen`
reports rather than restating it.

## 2. Module map

### Core (`src/scentinel/core/`)

| Module | Lines | Owns |
|---|---|---|
| `geometry.py` | 187 | `BinGeometry` (incl. `width_m`); mound surface, polygon, height, area, emitting area |
| `scenario.py` | 255 | `Scenario`: wind, ventilation flag, waste stream, composition/tonnage overrides, per-gas sources (ppmv or `"auto"`) |
| `composition.py` | 300 | `WasteComposition`, Table HH-1 `DOC`/`k`, `PhaseModel`, `interpret_phase` |
| `generation.py` | 280 | 40 CFR 98.343(a)(1) Equation HH-1: ultimate, cumulative, and rate; measurement-replaceable CH₄ default `F = 0.5`, with CO₂ closure labelled as a model assumption |
| `massbalance.py` | 188 | Per-stream tonnage; every split carries its provenance |
| `suitability.py` | 284 | Route scores, fuel-quality inputs and their missing set |
| `recommend.py` | 174 | One recommendation with reasons, caveats, and a runner-up margin |
| `pipeline.py` | 108 | Composition → generation → balance → suitability → recommendation in one call |
| `project.py` | 75 | `Project`, `Sensor`; `.scentinel` JSON round-trip |
| `gas_data.py` | 378 | AP-42 loader: `GasSpec`, `GasApplicability`, `offered_gases(age_h)`, `citation` |
| `gas_defaults.py` | 780 | Generated data — do not edit by hand (see `scripts/build_gas_data.py`) |
| `mesh.py` | 238 | gmsh: air-region outline, 1-cell extrusion, physical groups → `MeshResult` |
| `casegen.py` | 836 | OpenFOAM case writer: fields, dictionaries, patch roles, wind profile, emission rate/flux, applied-physics constants, case-input digest |
| `runner.py` | 273 | Podman invocation, log streaming, cancellation/timeout, per-stage logs |
| `container.py` | 268 | Isolated Podman storage, image pull and tool verification |
| `assessment.py` | 315 | Exposure thresholds, peak-to-mean coverage, gas-phase Cl/S loading |
| `post.py` | 265 | VTK reading, sensor sampling, concentration fields, mass-balance helper |
| `virtual_sensor.py` | 80 | Deterministic device response models (PID/MOX/electrochemical/NDIR/pellistor) |
| `history.py` | 1938 | Run allocation, `run.json` schema/validation, atomic writes, `load_run`/`list_runs`/`get_run` |

### UI (`src/scentinel/ui/`)

| Module | Lines | Owns |
|---|---|---|
| `home_window.py` | 346 | Start screen and the one dock-based workspace |
| `main_window.py` | 949 | Menus, project lifecycle, dirty tracking, run orchestration |
| `setup_panel.py` | 499 | Geometry/scenario/gas forms; emits `changed(geom, scenario)` |
| `batch_panel.py` | 383 | Composition/age/tonnage/moisture inputs and the live assessment |
| `viewport.py` | 268 | `QGraphicsView`: bin + mound drawing, sensor placement |
| `results_panel.py` | 526 | Probe table, summary, field tab, log pane, Run/Cancel/Export |
| `field_view.py` | 128 | Rendered OpenFOAM concentration field with sensor overlays |
| `sensor_lab.py` | 401 | Virtual-sensor replay, telemetry, and device evaluation |
| `solver_worker.py` | 286 | Background pipeline: mesh → case → solve → sample |
| `workspace.py` | 248 | Dock layout and per-workspace layout persistence |
| `theme.py` | — | Application stylesheet |
| `i18n.py` | 53 | `Translator`, runtime language switch |

### Tests (`tests/`)

566 collected: 553 unit + UI, 8 integration (7 in the e2e scenario plus the
podman-availability check in `test_runner.py`), 4 verification (analytical
benchmarks and the mesh-independence record), plus the deselection overlap.

## 3. Data flow

```
user edits form / clicks viewport
        │
        ▼
MainWindow.Project  ──save──►  <name>.scentinel  (JSON, format_version 1)
        │
        │  Run Simulation (F5)
        ▼
MainWindow.start_run
        │  1. history.snapshot_project(project)  →  one frozen deep copy
        │     the copy, not the live model, is what the run may sample
        ▼
   core.history.begin_run(frozen)
        │                    → runs/run-NNN/run.json  (execution_status: incomplete)
        │                      requested inputs + applied_physics (no digest yet)
        ▼
SolverWorker._run_pipeline(frozen)
        │
        ├─ 1. mesh.generate_mesh        → runs/run-NNN/mesh/case.msh
        │      (child process; see §5)
        │
        ├─ 2. casegen.write_case        → runs/run-NNN/case/
        │      copies case.msh in; writes 0/, constant/, system/
        │
        ├─ 3. runner.run_case           → podman, one shell pipeline
        │      gmshToFoam → changeDictionary → simpleFoam → foamToVTK
        │
        └─ 4. post.sample_sensors       → list[SensorReading]
               reads VTK/<case>_<time>/internal.vtu
        │
        ▼
MainWindow._on_run_finished
        │
        ├─ ppmv conversion (÷ casegen.PPM_SCALE), once
        │     ├─► ResultsPanel.set_results   →  table (ppmv)  →  CSV export
        │     └─► core.history.finish_run    →  run.json (terminal execution_status)
        │            validates readings against the frozen sensors,
        │            digests the generated case inputs, atomic replace
```

## 4. Physics setup

| Item | Choice | Notes |
|---|---|---|
| Dimensionality | 2D as 3D one cell thick | OpenFOAM has no 2D solver; front/back are `empty` |
| Solver | `simpleFoam` | Steady SIMPLE, incompressible, isothermal |
| Turbulence | k-epsilon RAS | `k`, `epsilon`, `nut` written per case |
| Scalar transport | `scalarTransport` function object | One per selected gas, `alphaD*nu + alphaDt*nut` with `alphaD = D_gas/nu` (per gas) and `alphaDt = 1/Sc_t` — the turbulent effective diffusivity; `Sc_t = 0.7` is a model assumption |
| Waste mound | Not meshed | Solid, no flow; contributes only the `source` patch |
| Source term | Emission mass flux | kg/m²/s over the emitting area, imposed as a `fixedGradient` on the scalar in volume-fraction units (`J*(Vm/MW)/D`; no `1e6`) |

### Boundary conditions

Patch roles are assigned from the geometry, not hard-coded, so wind direction
only changes which open side is the inlet.

| Patch | Velocity | Pressure | k | epsilon | nut | Scalar |
|---|---|---|---|---|---|---|
| `source` (waste) | noSlip | zeroGradient | zeroGradient | zeroGradient | calculated | **fixedGradient (flux/D)** |
| `wallLeft`, `wallRight` (bin) | noSlip | zeroGradient | kqRWallFunction | epsilonWallFunction | nutkWallFunction | zeroGradient |
| `openLeft`, `openRight` | inlet: fixedValue / outlet: zeroGradient | outlet: fixedValue 0 | inlet: fixedValue | inlet: fixedValue | calculated | inlet: 0 / outlet: zeroGradient |
| `top` | slip | zeroGradient | zeroGradient | zeroGradient | calculated | zeroGradient |
| `frontAndBack` | empty | empty | empty | empty | empty | empty |

### Wind profile

AP-42 wind speeds are reported at 10 m; the bin sits far lower. `wind_speed_at`
applies a 1/7 power law, so a reported 2.0 m/s becomes ~1.64 m/s at the 2.5 m
bin rim and 0 at ground level.

## 5. Load-bearing implementation details

These are the decisions that took empirical work to find. Each is commented in
the source; they are collected here because breaking any one of them fails
silently or with a misleading error.

### Mesh

1. **MSH 2.2, not the gmsh default 4.1.** `gmshToFoam` reads the v2 sections
   (`$NOD`, `$ELM`) and the v2 element line format. With 4.1 it reports
   "No cells read from file".
2. **`Mesh.RecombineAll = 1`.** Without it the extrusion produces ~17k
   tetrahedra instead of ~5k hexahedra.
3. **A volume physical group is required.** Once any physical group exists,
   gmsh writes *only tagged* elements. Without a group on the volume the hexes
   are dropped and the file arrives 2D — the exact failure `gmshToFoam`
   complains about, caused by a missing tag rather than a missing extrusion.
4. **Extruded side surfaces carry the curve groups.** `gmshToFoam` maps
   boundary faces to patches by physical tag; an untagged side becomes an
   unusable `defaultFaces` patch and the solver dies reading the first field.
5. **`mound_surface` is separate from `mound_polygon`.** A flat mound's polygon
   is a rectangle, and feeding that into the air outline makes the loop
   self-touch at x=0 — gmsh then meshes nothing at all.
6. **The mound is not meshed.** It is a boundary, not a region.
7. **Wall and open patches are separate.** The outline splits each side at the
   bin rim so the solid wall and the open sky above it are different patches.

### Case

8. **The image is ESI, not the Foundation line.** `opencfd/openfoam-default:2512`
   ships `simpleFoam`; it has no `foamRun` and no `incompressibleFluid` module.
   It also reads `constant/transportProperties` + `turbulenceProperties`, not
   `physicalProperties` + `momentumTransport`.
9. **`changeDictionary` is mandatory.** `gmshToFoam` writes every boundary as a
   generic `patch`; wall functions reject that, and `empty` cannot be applied
   without it.
10. **The waste surface is a `wall`,** not a generic patch, because
    `kqRWallFunction` requires a wall patch type.
11. **`nut` must be written.** k-epsilon reads it from `0/nut` at startup.
12. **`0/<gas>` needs `inlet { fixedValue 0 }`.** A `zeroGradient` inlet lets
    the scalar drift.

### Runner

13. **The OpenFOAM environment must be sourced.** The image's entrypoint leaves
    a non-interactive shell without the binaries on `PATH`; `foamRun` appears
    "not found" for that reason alone.
14. **`cd /case` is required inside the script.** The same entrypoint lands the
    shell in `/home/openfoam`, so `-w` on `podman run` does not survive.
15. **Cancellation kills the process group** (`start_new_session=True` +
    `killpg`). Terminating the direct child leaves the container running.

### UI

16. **Meshing runs in a child process.** gmsh installs a `SIGINT` handler in
    `initialize()`, and Python only permits that on the main thread of the main
    interpreter. `_start_method()` prefers `spawn` but falls back to `fork`
    when `__main__` has no file (a stream or embedded interpreter).
17. **The viewport fits to the geometry, not `itemsBoundingRect()`.** Sensor
    labels ignore view transforms, so their scene bounding box is in pixels and
    inflates the fitted area by the zoom factor.
18. **Loading a project must not mark it dirty.** `_loading` suppresses the
    panel signals that `_apply_project` triggers.
19. **Run identity comes from the filesystem, not memory.** `history.begin_run()`
    scans the highest existing `run-NNN` name and claims the next id with
    `mkdir(exist_ok=False)`; a lost race retries the following id. A matching
    directory participates even when its manifest is missing or corrupt, so an
    id is never handed out twice and a restart cannot reuse one.
20. **The manifest is written twice, atomically.** `run.json` is written in
    `incomplete` state before the solver starts, then replaced through a
    temporary sibling and `os.replace()`. A crash leaves the honest incomplete
    record; a failed replacement leaves the previous valid manifest intact and
    the UI reports completion-with-history-error rather than success.
21. **`finish_run()` takes ppmv, already converted.** The UI performs the single
    volume-fraction-to-ppmv conversion and feeds the same values to the results
    table and the manifest, so displayed and persisted readings cannot drift.
22. **Only the path relative to the run directory is stored.** `case_dir` is
    validated as a relative child, so a manifest never carries a workstation
    path and stays portable with its case.
23. **`requested_end_iteration` is a control index, not elapsed time.** The
    steady `simpleFoam` run has no physical duration. Scentinel parses the
    numerically latest solver-time residuals and compares every configured
    field against the targets written for that case. A missing field is
    `not_evaluated`, not a pass; a solver-stage failure remains
    `solver_error`. Exit code 0 alone is never evidence of convergence.
24. **The run samples a frozen snapshot, not the live model.** `start_run()`
    takes one `history.snapshot_project()` copy and gives it to both
    `begin_run()` and `SolverWorker`. Disabling the editing surfaces while a
    run is in flight is UX defence; correctness comes from the copy, so a
    viewport click mid-run cannot change what a record claims to have measured.
25. **`finish_run()` re-checks readings against the frozen sensors.** Ids,
    coordinates, order, and gas keys must match exactly. Supplied readings that
    do not match are a hard `HistoryError` — persisting foreign numbers under
    this run's inputs would break the manifest's central promise. *Absent*
    readings after a clean exit are recorded as `failed` with
    `NO_READINGS_ERROR`, so an exit-0 failure is auditable rather than opaque.
    `load_run()` applies the same check, so a hand-edited manifest cannot
    smuggle in foreign readings.
26. **`applied_physics` and the case digest separate request from experiment.**
    The reported wind speed becomes a different inlet velocity after power-law
    scaling. Each scalar uses `alphaD*nu + alphaDt*nut`, with per-gas
    `alphaD = D_gas/nu` and `alphaDt = 1/Sc_t`; `Sc_t = 0.7` is a labelled
    model assumption. `casegen.scalar_diffusivity()` reads each gas's
    FSG-computed molecular value from `gas_data`.
    `casegen` owns those constants and renders both the case files
    and the persisted block from the same source, so a manifest cannot claim a
    setting the case does not use. The SHA-256 digest
    over the declared case inputs (`casegen.case_input_paths`) is the
    authoritative guard: it covers only what `write_case` generated, never the
    solver's own output into the same tree, so the digest stays valid after a
    solve and a changed applied constant changes it at identical UI inputs.
27. **Scientific gates are stated, never inferred.** `quality` carries
    `convergence`, `mesh_independence`, `mass_balance`, and
    `experimental_validation`, each from a closed set, all non-passing for an
    ordinary run. `execution_status: "succeeded"` is only a process outcome.
    Consumers that filter on it alone would render an unverified run as
    verified; the gate fields exist so they cannot.
28. **Ventilation is recorded as a request, not as physics.**
    `casegen.write_case()` ignores the flag, so the manifest stores
    `{"requested_on": …, "modelled": false}` and `load_run()` rejects
    `modelled: true`. No comparison consumer may group or difference by an
    unmodelled factor, or it would conclude ventilation has no effect.
29. **`core.history` imports without the `cfd` extra.** `history` imports
    `casegen`, which imports `mesh` (and therefore `gmsh`) only under
    `TYPE_CHECKING`. The documented read API (`list_runs()` / `get_run()`)
    performs no meshing, so a machine without gmsh can still read a manifest.

## 6. Container contract

| Item | Value |
|---|---|
| Image | `docker.io/opencfd/openfoam-default:2512` |
| Environment | `source /usr/lib/openfoam/openfoam2512/etc/bashrc` |
| Working dir | `cd /case` (mounted from `runs/run-NNN/case`) |
| Pipeline | `gmshToFoam case.msh` → `changeDictionary -constant` → `simpleFoam` → `foamToVTK -latestTime` |
| Exit codes | 9 source, 10 cd, 11 gmshToFoam, 12 changeDictionary, 13 solver, 14 foamToVTK |

The image is pulled by `scripts/setup_container.sh`, which also verifies all
four tools exist. Fully qualified image names are required: podman refuses to
guess a registry when it cannot prompt.

## 7. Verification status

| Gate (design spec) | Target | Measured | Status |
|---|---|---|---|
| Mesh independence | <10% deviation under 2× refinement | 266.29% worst containing-cell deviation | **FAIL** |
| Mass balance | <5% | 1.4245% integrated closure | **PASS** |
| Analytical transport | advection exact; axial diffusion within benchmark tolerance | 0% advection error; 5.5% axial-diffusion error at Pe=5 | **PASS** |
| Cavity benchmark | runs, no `FOAM FATAL` | superseded by the real e2e case | — |

`checkMesh` passes on the generated meshes (non-orthogonality 32.6° max, skewness
0.77, no illegal faces).

### Why mesh independence fails

The source is an emission mass flux (`fixedGradient`), so the imposed flux is
independent of the first cell height, and the scalar is carried with turbulent
diffusivity (`D + ν_t/Sc_t`). The old nearest-cell metric fell from ~87% to
~19%, but that sampler silently snapped probes. Containing-cell sampling after
the source audit measures 266.29%, and the *velocity field* is also not
mesh-converged at these cell counts. Measured 2026-09-20:

| Stage | Worst-probe deviation |
|---|---|
| pre-Phase-5 `fixedValue` concentration | ~87% |
| Phase 5 mass-flux boundary | ~63% |
| Phase 6 turbulent transport, nearest-cell sampling | ~19% |
| Phase 7 corrected source + containing-cell sampling | 266.29% |

S3 changes sign at the trace-scalar noise floor; velocity magnitude changes by
up to 30.84% between 0.50 and 0.25 m. Treat absolute concentrations and sensor
rankings as screening estimates. The remaining fix is a mesh-converged velocity
field plus near-wall refinement (T-021) — see [ROADMAP.md](ROADMAP.md).

## 8. Conventions

- Python 3.12+ syntax; `from __future__ import annotations` everywhere.
- Line length 100 (ruff config in `pyproject.toml`).
- Core modules import no Qt. UI modules import no gmsh, podman, or pyvista at
  module scope (pyvista is imported inside `post` functions to keep startup
  cheap). Optional-dependency imports anywhere in core that only serve type
  annotations belong behind `TYPE_CHECKING`.
- Every user-visible string goes through `Translator.t`, with keys in both
  `resources/locales/en.json` and `id.json`.
- Gas defaults cite their source in the generated data and in `gas_data.citation`.
- A field that carries a physical quantity names its unit (`_m`, `_m_s`,
  `_ppmv`, `_m2_s`), and the schema rejects unknown keys so a rename cannot be
  silently ignored.
- Persisted scientific evidence is never inferred from a process outcome:
  convergence, verification, and validation are separate, closed-enum gates.
