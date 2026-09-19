# Scentinel — Roadmap

**Version:** 0.1.0 · **Last updated:** 2026-09-19

Phase plan, current position, and what each remaining phase has to prove. Task
detail lives in [TASKS.md](TASKS.md); design rationale in
[ARCHITECTURE.md](ARCHITECTURE.md).

---

## Current position

```
F0  Foundation & OpenFOAM integration    ████████████████████░░  done (cavity superseded)
F1  2D geometry, mesh, sensor placement  ████████████████████░░  done
F2  Multi-gas, visualisation, probes     ██████████████████░░░░  probes done, verification failing
F3  Comparison and reporting             ████████░░░░░░░░░░░░░░  history done, no comparison UI
F4  3D and transient                     ░░░░░░░░░░░░░░░░░░░░░░  not started
```

**What works today:** set geometry and scenario in the UI → place sensors by
clicking → press Run → the app reserves a persistent run id, meshes, writes an
OpenFOAM case, solves it in the container, and fills the results table with
per-sensor ppmv for every selected gas. Each attempt leaves a never-reused
`runs/run-NNN/run.json` manifest recording its exact inputs, resolved source
provenance, execution settings, terminal status, and results, so runs survive a
restart and can be listed or looked up. Projects save and load; the UI switches
language at runtime; results export to CSV.

**What does not work:** absolute concentrations are not mesh-converged (see
below); nothing reads the run history back into the UI, so there is still no
scenario comparison view and no PDF reporting; and the ventilation flag is
stored but has no effect on the case.

---

## Phase status

### F0 — Foundation & OpenFOAM integration

**Exit criterion:** solver runs from the app, results render.

| Task | Status | Note |
|---|---|---|
| 0.1 Project scaffolding | Done | Package, `.gitignore`, pytest config |
| 0.2 Container setup script | Done | `scripts/setup_container.sh`; verifies all four tools |
| 0.3 Podman runner | Done | `core/runner.py`; log streaming, per-stage exit codes, process-group cancel |
| 0.4 Lid-driven cavity benchmark | Superseded | The e2e waste-bin case is a stricter test; cavity adds a second case format for no new coverage |
| 0.5 Main window and i18n | Done | Bilingual runtime switching, project lifecycle |

### F1 — 2D geometry, mesh, sensor placement

**Exit criterion:** one scenario runs end to end.

| Task | Status | Note |
|---|---|---|
| 1.1 2D geometry builder | Done | `mound_surface` split from `mound_polygon` — the plan's version failed its own tests |
| 1.2 gmsh meshing with boundary tagging | Done | Air region only, 1-cell extrusion, hexahedral |
| 1.3 OpenFOAM case writer | Done | ESI-targeted; `changeDictionary` for patch types |
| 1.4 Viewport with sensor placement | Done | Click to place, right-click to remove, eviction when the mound rises |
| 1.5 Project save/load | Done | `.scentinel` JSON, version-checked |
| 1.6 End-to-end single-gas scenario | Done | `tests/integration/test_e2e_scenario.py` |

### F2 — Multi-gas, visualisation, probes

**Exit criterion:** CO/CH₄/VOC visible and probed; all verification gates pass.

| Task | Status | Note |
|---|---|---|
| 2.1 Gas data loader | Done | Cited AP-42 defaults, `auto` resolution, per-gas tooltips |
| 2.2 Multi-gas case generation | Done | One `scalarTransport` object and one `0/<gas>` field per selected gas |
| 2.3 Post-processing and probes | Done | VTK cell sampling, `SensorReading` |
| 2.4 Results panel | Done | Table in ppmv, log pane, CSV export |
| 2.5 Physics verification | **Blocked** | Mesh independence fails at 76.5%; see below |
| 2.6 Field visualisation (cut planes, streamlines) | Not started | pyvista is installed and `foamToVTK` already emits the data |

### F3 — Comparison and reporting

**Exit criterion:** compare ≥2 runs, export CSV/PDF. Persistence is in place;
the comparison view and PDF export are not, so the criterion is not met yet.
Every recorded run is classified `screening_estimate` — persisting a run does
not make its absolute concentrations calibrated or validated.

| Task | Status |
|---|---|
| 3.1 Run history manager | Done — `core/history.py`; persistent `run-NNN/run.json` manifests, `list_runs()` / `get_run()` |
| 3.2 Comparison view | Not started — nothing reads the history back into the UI yet |
| 3.3 CSV export | Done (from the results panel) |
| 3.4 PDF report | Not started |

### F4 — 3D and transient

Not started. 3D geometry and meshing, transient solver settings, and
response-delay analysis. The 2D pipeline should be trustworthy first.

---

## Blocking issue: mesh independence

The design spec requires probe values to change by less than 10% when the mesh
is refined 2×. Measured on the current pipeline:

| Mesh size | Cells | S1 (ppmv) | S3 (ppmv) |
|---|---|---|---|
| 0.50 m | 3 444 | 0.342 | 4.340 |
| 0.25 m | 7 248 | 0.465 | 3.363 |
| 0.125 m | 28 016 | 0.887 | 6.358 |

Deviation is 76.5% at the first refinement, and the sequence is not converging —
refining further moves the values more, not less.

**Cause.** The source is a `fixedValue` concentration on a diffusive patch. The
flux entering the domain is `D · ∂C/∂n` at the wall, and the near-wall gradient
scales as `1/Δy` for a fixed concentration difference. Uniform refinement of the
mound profile refines the surface *tangentially* but not the first cell height
*normal* to it, so the computed flux drifts.

**Fix options, in order of preference:**

1. **Mass-flux source.** Switch to a `fixedFluxPressure`-style or
   `externalWallHeatFluxTemperature`-equivalent scalar flux boundary so the
   emission rate (kg/m²/s) is imposed rather than the surface concentration.
   This is also what the design spec originally described (§4.2, §4.3) before
   the plan changed it to a concentration.
2. **Near-wall refinement.** Add boundary-layer grading normal to the waste
   surface so the first cell height is resolved, then demonstrate convergence.
3. **Accept and document.** Keep the concentration boundary and state clearly
   that values are relative screening estimates. This is the current position.

Option 1 is the real fix and unblocks the gate. It changes the units shown in
the UI (a source strength in kg/m²/s rather than a surface concentration) and
needs a conversion using molecular weight: `C_surface` from `S / (h_m · MW)`
with `h_m` a mass-transfer coefficient, or the flux directly.

---

## Sequencing

```
        ┌──────────────────────────────────────────┐
        │ 1. Fix the source term (mass flux)       │
        │    unblocks the F2 verification gate     │
        └──────────────────┬───────────────────────┘
                           │
        ┌──────────────────▼───────────────────────┐
        │ 2. Field visualisation (2.6)             │
        │    makes results inspectable, not just a │
        │    table of numbers                      │
        └──────────────────┬───────────────────────┘
                           │
        ┌──────────────────▼───────────────────────┐
        │ 3. F3: comparison UI, PDF                │
        │    run history (3.1) already landed      │
        └──────────────────┬───────────────────────┘
                           │
        ┌──────────────────▼───────────────────────┐
        │ 4. Supervisor review, then F4            │
        └──────────────────────────────────────────┘
```

Steps 1 and 2 are independent of each other and can be done in either order.
Step 3 depends on step 1 only for credibility, not technically.

---

## Milestones

| Milestone | Definition of done |
|---|---|
| **M1 — Trustworthy numbers** | Mesh independence <10%; mass balance automated and <5% |
| **M2 — Inspectable results** | Concentration field and streamlines render in the app for a solved run |
| **M3 — Comparison** | Two runs side by side with a difference column; PDF report with cited defaults (run history landed; the view does not exist yet) |
| **M4 — Supervisor review** | Results reviewed and signed off before any hardware decision |
| **M5 — 3D** | 3D mesh runs; response delay measured |

M1 is the gate for using the tool to make a placement decision. Until it passes,
treat output as relative comparison between scenarios only.

---

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Source term remains unresolved | Absolute values stay unreliable | Planned work above; M1 gates it |
| 2D idealisation misses 3D effects | Placement advice may not transfer | State the limitation; F4 covers 3D |
| Solver runtime grows with mesh | Long waits in the UI | Runs are cancellable; mesh size is a parameter |
| OpenFOAM image tag moves | Pipeline breaks on a fresh machine | Image tag pinned in `casegen.IMAGE`; `setup_container.sh` verifies tools |
| Scope creep back to the AI/fleet layer | The simulation layer never finishes | F3 exit criterion is explicit; F4 is the only sanctioned extension |
