# Scentinel — Architecture

**Version:** 0.1.0 · **Last updated:** 2026-09-19

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
reserves the run directory through `core.history` before the worker is
constructed and finalizes the same record afterwards, so the run identity never
depends on process-local state.

## 2. Module map

### Core (`src/scentinel/core/`)

| Module | Lines | Owns |
|---|---|---|
| `geometry.py` | 148 | `BinGeometry`; mound surface, polygon, height, area, fill fraction |
| `scenario.py` | 45 | `Scenario`: wind, ventilation flag, per-gas sources (ppmv or `"auto"`) |
| `project.py` | 59 | `Project`, `Sensor`; `.scentinel` JSON round-trip |
| `gas_data.py` | 84 | AP-42 loader: `GasSpec`, `source_concentration`, `default_sources`, `citation` |
| `gas_defaults.py` | 338 | Generated data — do not edit by hand (see `scripts/build_gas_data.py`) |
| `mesh.py` | 234 | gmsh: air-region outline, 1-cell extrusion, physical groups → `MeshResult` |
| `casegen.py` | 488 | OpenFOAM case writer: fields, dictionaries, patch roles, wind profile |
| `runner.py` | 194 | Podman invocation, log streaming, cancellation, per-stage logs |
| `post.py` | 170 | VTK reading, sensor sampling, concentration fields, mass-balance helper |
| `history.py` | 1144 | Run allocation, `run.json` schema/validation, atomic writes, `load_run`/`list_runs`/`get_run` |

### UI (`src/scentinel/ui/`)

| Module | Lines | Owns |
|---|---|---|
| `main_window.py` | 620 | Menus, project lifecycle, dirty tracking, run orchestration |
| `setup_panel.py` | 285 | Geometry/scenario/gas forms; emits `changed(geom, scenario)` |
| `viewport.py` | 268 | `QGraphicsView`: bin + mound drawing, sensor placement |
| `results_panel.py` | 201 | Probe table, log pane, Run/Cancel/Export buttons |
| `solver_worker.py` | 283 | Background pipeline: mesh → case → solve → sample |
| `i18n.py` | 53 | `Translator`, runtime language switch |

### Tests (`tests/`)

164 collected: 156 unit + UI, 7 integration (6 in the e2e scenario plus the
podman-availability check in `test_runner.py`), 1 verification.

## 3. Data flow

```
user edits form / clicks viewport
        │
        ▼
MainWindow.Project  ──save──►  <name>.scentinel  (JSON, format_version 1)
        │
        │  Run Simulation (F5)
        ▼
MainWindow.start_run ──► core.history.begin_run
        │                    → runs/run-NNN/run.json  (status: incomplete)
        ▼
SolverWorker._run_pipeline
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
        ├─ ppmv conversion (×1e6), once
        │     ├─► ResultsPanel.set_results   →  table (ppmv)  →  CSV export
        │     └─► core.history.finish_run    →  run.json (terminal status)
        │            atomic replace of the incomplete manifest
```

## 4. Physics setup

| Item | Choice | Notes |
|---|---|---|
| Dimensionality | 2D as 3D one cell thick | OpenFOAM has no 2D solver; front/back are `empty` |
| Solver | `simpleFoam` | Steady SIMPLE, incompressible, isothermal |
| Turbulence | k-epsilon RAS | `k`, `epsilon`, `nut` written per case |
| Scalar transport | `scalarTransport` function object | One per selected gas, `diffusivity constant; D 2e-05` |
| Waste mound | Not meshed | Solid, no flow; contributes only the `source` patch |
| Source term | `fixedValue` concentration | 105 ppmv CO etc., as volume fraction |

### Boundary conditions

Patch roles are assigned from the geometry, not hard-coded, so wind direction
only changes which open side is the inlet.

| Patch | Velocity | Pressure | k | epsilon | nut | Scalar |
|---|---|---|---|---|---|---|
| `source` (waste) | noSlip | zeroGradient | zeroGradient | zeroGradient | calculated | **fixedValue (ppmv)** |
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
23. **`end_iteration` is a control index, not elapsed time.** The steady
    `simpleFoam` run has no physical duration, so the manifest names the field
    for what it is even though the worker argument is still `end_time`.

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
| Mesh independence | <10% deviation under 2× refinement | 76.5% worst, not convergent | **FAIL** |
| Mass balance | <5% | ~8% by a hand-rolled diffusive-flux estimate | not automated |
| Analytical 1D diffusion | R² > 0.99 | not written | — |
| Cavity benchmark | runs, no `FOAM FATAL` | superseded by the real e2e case | — |

`checkMesh` passes on the generated meshes (non-orthogonality 32.6° max, skewness
0.77, no illegal faces).

### Why mesh independence fails

The source is a `fixedValue` concentration on a diffusive patch. The near-surface
gradient — and therefore the sampled value — scales with the first cell height,
which uniform refinement of the mound profile does not resolve. Measured:

| Mesh size | Cells | S1 (ppmv) | S3 (ppmv) |
|---|---|---|---|
| 0.50 m | 3 444 | 0.342 | 4.340 |
| 0.25 m | 7 248 | 0.465 | 3.363 |
| 0.125 m | 28 016 | 0.887 | 6.358 |

Treat absolute concentrations as screening estimates. The fix is a mass-flux
source term (kg/m²/s) with a resolved near-wall cell, which is planned work —
see [ROADMAP.md](ROADMAP.md).

## 8. Conventions

- Python 3.12+ syntax; `from __future__ import annotations` everywhere.
- Line length 100 (ruff config in `pyproject.toml`).
- Core modules import no Qt. UI modules import no gmsh, podman, or pyvista at
  module scope (pyvista is imported inside `post` functions to keep startup
  cheap).
- Every user-visible string goes through `Translator.t`, with keys in both
  `resources/locales/en.json` and `id.json`.
- Gas defaults cite their source in the generated data and in `gas_data.citation`.
