# Scentinel — Roadmap

**Version:** 0.2.2 · **Last updated:** 2026-09-19

Phase plan, current position, and what each remaining phase has to prove. Task
detail lives in [TASKS.md](TASKS.md); design rationale in
[ARCHITECTURE.md](ARCHITECTURE.md).

> **Active program (2026-09-19):** [superpowers/plans/2026-09-19-hardening-program.md](superpowers/plans/2026-09-19-hardening-program.md)
> — 20 phases, T-200…T-294, that harden the chain *waste → gas → CFD → sensor →
> quality → recommendation* before any 3D, transient, or UI-redesign work.
> Scope is frozen at baseline tag `v0.2.2-audit`; the phase table below remains
> the long-range view. Each phase gets its own bite-sized execution plan at
> kickoff.

---

## Current position

```
F0  Foundation & OpenFOAM integration    ████████████████████░░  done (cavity superseded)
F1  2D geometry, mesh, sensor placement  ████████████████████░░  done
F2  Multi-gas, visualisation, probes     ███████████████████░░░  probes + field view done, verification failing
F3  Comparison and reporting             ████████░░░░░░░░░░░░░░  history done, no comparison UI
F4  3D and transient                     ░░░░░░░░░░░░░░░░░░░░░░  not started
W   Waste intelligence (characterization ░░░░░░░░░░░░░░░░░░░░░░  W0 done; W1–W3 engine done, UI partial
    → suitability → yield → decision)
```

**What works today:** set geometry and scenario in the UI → place sensors by
clicking → press Run → the app reserves a persistent run id, meshes, writes an
OpenFOAM case, solves it in the container, and fills the results table with
per-sensor ppmv for every selected gas. Each attempt leaves a never-reused
`runs/run-NNN/run.json` manifest recording its requested inputs, resolved source
provenance, the applied numerical settings with a digest of the generated case,
the requested iteration count, the terminal execution status, and its results,
so runs survive a restart and can be listed or looked up. Projects save and
load; the UI switches language at runtime; results export to CSV. Concentration
fields render from the solved case, ten cited AP-42 gases are selectable with
per-gas Fuller-Schettler-Giddings diffusivities, the sensor lab replays each
placement through a device model, and the container image is pulled from the GUI
into an app-private store.

**Gas generation (Phase 2–4 done, 2026-09-19):** a batch's gas is computed from
its composition and age by Equation HH-1, with ultimate potential, cumulative
mass, and instantaneous rate as separate quantities and the produced mixture
split by the regulation's `F = 0.5`. The phase label is an interpretation, not
a switch, so generation is continuous across every age boundary; the AP-42
55/40/5 mix is kept as a mature-landfill ceiling. Each gas carries an explicit
applicability, and the offered gas list follows holding time — a fresh load does
not offer methane. Manifest format 6 records the generation and phase
provenance. Fresh-waste VOC research is partly extracted (Statheropoulos 2005)
and partly recorded unavailable (Waste Manag. 2017 paywalled).

**What does not work:** absolute concentrations are not mesh-converged (see
below); nothing reads the run history back into the UI, so there is still no
scenario comparison view and no PDF reporting; the ventilation flag is stored —
recorded as requested but unmodelled — but has no effect on the case; and the
fuel-basis RDF parameters (NCV, ash, Cl) still need laboratory input, so no
EN 15359 / ISO 21640 class is claimed.

A recorded run separates four things that are easy to conflate. The *requested*
inputs are the project snapshot; the *applied* experiment is the block of
numerical settings the generated case actually used, plus a SHA-256 digest of
that case; the *execution* status says only whether the container pipeline
exited 0 and sampled every captured sensor; and *quality* carries the screening
classification plus explicit per-run gate states (`convergence`,
`mesh_independence`, `mass_balance`, `experimental_validation`), all
non-passing for an ordinary run. Solver exit 0 is never recorded as
convergence, verification, or validation.

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

A future comparison view must consume the strict `load_run()` contract rather
than hiding corrupt records, must refuse to compare runs whose case-input
digests differ unless the mismatch is explicit, and must never group or
difference by `ventilation.requested_on` while `ventilation.modelled` is false.

| Task | Status |
|---|---|
| 3.1 Run history manager | Done — `core/history.py`; persistent `run-NNN/run.json` manifests (format version 6), `list_runs()` / `get_run()` |
| 3.2 Comparison view | Not started — nothing reads the history back into the UI yet. Superseded in scope by T-142, which compares batches as well as runs |
| 3.3 CSV export | Done (from the results panel) |
| 3.4 PDF report | Not started |

### F4 — 3D and transient

Not started. 3D geometry and meshing, transient solver settings, and
response-delay analysis. The 2D pipeline should be trustworthy first.

### W — Waste intelligence layer

**Exit criterion:** a described batch produces a characterization, per-route
suitability scores, a per-stream yield, a quality statement, and one actionable
recommendation — each traceable to a cited input, and each refusing to answer
when its inputs are missing.

**Plan:** [superpowers/plans/2026-09-19-waste-intelligence.md](superpowers/plans/2026-09-19-waste-intelligence.md)
**Basis:** [gas-composition-basis.md](gas-composition-basis.md)

The W0–W3 engine shipped in 0.2.1: composition, phase, Equation HH-1
generation, mass balance, suitability, and the recommendation all exist as core
modules with unit tests, and `ui/batch_panel.py` exposes them live. The batch
panel now also mirrors its composition, holding time, tonnage, moisture, and
stream into the scenario the run uses, and manifest format 6 records them.

| Sub-phase | Content | Status |
|---|---|---|
| W0 | Composition, phase, Eq. HH-1 generation, moisture, manifest v5 | Done |
| W1 | Batch mass balance and per-stream yield | Done; split fractions remain labelled assumptions |
| W2 | RDF quality parameters and route suitability scores | Engine done; T-120 is partly blocked on laboratory data |
| W3 | Interpretation, batch history, forecast, recommendation | Recommendation done; interpretation/history/forecast not started |
| W4 | Characterization and decision panels, comparison view, layout | Batch panel done; comparison view and decision panel not started |

The governing rule for this phase: **a value without a citation does not enter
the model.** Where no cited value exists, the output states the gap rather than
filling it.

---

## Blocking issue: mesh independence

The design spec requires probe values to change by less than 10% when the mesh
is refined 2×. Measured on the current pipeline, 2026-09-19, on CO with the
analytical-benchmark harness:

| Mesh size | Cells | S1 (ppmv) | S2 (ppmv) | S3 (ppmv) |
|---|---|---|---|---|
| 0.50 m | 3 444 | 0.0775 | 0.0939 | 0.3543 |
| 0.25 m | 7 248 | 0.0338 | 0.1758 | 0.3845 |
| **Deviation** | | **56.4%** | **87.2%** | 8.5% |

The sequence is not converging — refining further moves the values more, not
less. An earlier measurement on a different sensor set read 76.5%; both are far
outside the gate, and the number depends on where the probes sit, which is
itself part of the problem.

**Cause.** The source is a `fixedValue` concentration on a diffusive patch. The
flux entering the domain is `D · ∂C/∂n` at the wall, and the near-wall gradient
scales as `1/Δy` for a fixed concentration difference. Uniform refinement of the
mound profile refines the surface *tangentially* but not the first cell height
*normal* to it, so the computed flux drifts.

**What is trustworthy in the meantime.** The transport itself is verified
against closed-form solutions: pure advection reproduces the inlet value with
zero error, and axial diffusion matches the exponential profile within 5.5% at
Pe = 5 (`tests/verification/test_analytical_benchmarks.py`). The error is in the
*source boundary*, not the solver — so relative comparisons and placement
rankings hold, while absolute concentrations do not.

**Fix options, in order of preference:**

1. **Mass-flux source.** Switch to a `fixedFluxPressure`-style or
   `externalWallHeatFluxTemperature`-equivalent scalar flux boundary so the
   emission rate (kg/m²/s) is imposed rather than the surface concentration.
   Note: the design spec's §4.2/§4.3 describe a `fixedValue` *concentration*
   boundary, so this is a change of plan, not a restoration of the spec. The
   spec's own gas-source field comment (`gas_sources: … kg/m2/s or ppm basis`)
   left the basis open, and this is the resolution.
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
   TRACK A (CFD credibility)            TRACK B (waste intelligence)
   ─────────────────────────            ────────────────────────────
   1. T-020 mass-flux source            1. T-100 composition model
        │                                    │
   2. T-021 mesh-independence gate      2. T-101 phase from age_h
        │                                    │
        │                                3. T-102 Eq. HH-1 generation
        │                                    │
        │                                4. T-103 replace linear scaling
        │                                   T-104 moisture → k
        │                                   T-105 manifest v4
        │                                    │
        │                                5. T-106 extract fresh-waste VOC
        │                                   T-107 phase-I gas set
        │                                    │
        └──────────────┬─────────────────────┘
                       │
        ┌──────────────▼───────────────────────┐
        │ W1  mass balance → per-stream yield  │
        └──────────────────┬───────────────────┘
                           │
        ┌──────────────────▼───────────────────────┐
        │ W2  quality parameters, suitability      │
        │     (T-120 partly needs laboratory data) │
        └──────────────────┬───────────────────────┘
                           │
        ┌──────────────────▼───────────────────────┐
        │ W3  interpretation, forecast,            │
        │     recommendation                       │
        └──────────────────┬───────────────────────┘
                           │
        ┌──────────────────▼───────────────────────┐
        │ W4  characterization + decision UI       │
        └──────────────────┬───────────────────────┘
                           │
        ┌──────────────────▼───────────────────────┐
        │ Supervisor review, then F4               │
        └──────────────────────────────────────────┘
```

Tracks A and B are independent and run in parallel. Track A gates the
*credibility* of anything Track B produces from concentrations; Track B gates the
*usefulness* of the tool. W2 cannot produce a defensible fuel grade until
T-120's lab-or-cited question is answered, so that research starts early.

---

## Milestones

| Milestone | Definition of done |
|---|---|
| **M1 — Trustworthy numbers** | Mesh independence <10%; mass balance automated and <5% |
| **M2 — Inspectable results** | Concentration field renders in the app for a solved run — **met** (`ui/field_view.py`) |
| **M3 — Comparison** | Two runs side by side with a difference column; PDF report with cited defaults |
| **M4 — Batch characterization** | A described batch yields composition, phase, and generation with every value cited |
| **M5 — Decision output** | Yield per stream, route suitability, and one actionable recommendation — each refusing to answer when inputs are missing |
| **M6 — Supervisor review** | Results reviewed and signed off before any hardware decision |
| **M7 — 3D** | 3D mesh runs; response delay measured |

M1 is the gate for using the tool to make a placement decision. Until it passes,
treat output as relative comparison between scenarios only. M5 inherits that
gate: a recommendation may not present a screening estimate as a measurement.

---

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Source term remains unresolved | Absolute values stay unreliable | Planned work above; M1 gates it. Transport itself is already verified against closed forms |
| **Fresh-waste VOC data cannot be extracted** | Phase I (the truck case) cannot be populated honestly | T-106 reports the gap; offer only gases with citations; never estimate |
| **No cited composition→NCV correlation exists** | RDF grade cannot be computed without lab data | Ship lab-input mode; state the limitation in the UI and README (T-120) |
| **Routing fractions are process assumptions** | Yield numbers look authoritative but are not | Provenance per fraction; user edits recorded as `user input` (T-111) |
| **Waste layer scope dwarfs the CFD core** | The core stalls | W0 first; each sub-phase ships independently; T-020/T-021 stay top of queue |
| 2D idealisation misses 3D effects | Placement advice may not transfer | State the limitation; F4 covers 3D |
| Solver runtime grows with mesh | Long waits in the UI | Runs are cancellable; mesh size is a parameter |
| OpenFOAM image tag moves | Pipeline breaks on a fresh machine | Image tag pinned in `casegen.IMAGE`; `setup_container.sh` verifies tools |
| Scope creep back to the AI/fleet layer | The simulation layer never finishes | F3 exit criterion is explicit; F4 and W are the only sanctioned extensions |

---

## Documentation map

| Document | Contents |
|---|---|
| [gas-composition-basis.md](gas-composition-basis.md) | Cited scientific basis for the waste layer: the basis mismatch, AP-42 phases, 40 CFR 98.343 Equation HH-1, Table HH-1 parameters, and the citation-status table |
| [superpowers/plans/2026-09-19-waste-intelligence.md](superpowers/plans/2026-09-19-waste-intelligence.md) | Phase W implementation plan with sequencing, verification strategy, and risks |
| [TASKS.md](TASKS.md) | Every task with status, files, and acceptance test |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Module map, data flow, physics setup, load-bearing implementation details |
| [references.md](references.md) | Provenance of every value currently in the model |
