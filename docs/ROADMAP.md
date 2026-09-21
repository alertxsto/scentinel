# Scentinel — Roadmap

**Version:** 0.2.3 · **Last updated:** 2026-09-21

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
fields render from the solved case, the full 47-gas AP-42 catalogue is
available for aged loads, and phase I exposes only its supported allow-list.
Each gas uses its Fuller-Schettler-Giddings diffusivity, the sensor lab replays
each placement through a device model, and the container image is pulled from
the GUI into an app-private store.

**Gas generation (Phases 2–3 done; Phase 4 partial):** a batch's gas is
computed from composition and age by Equation HH-1, with ultimate potential,
cumulative mass, and instantaneous rate as separate quantities. Methane uses
the regulation's measurement-replaceable default `F = 0.5`; the matching CO₂
carbon closure is an explicit model assumption. The phase label interprets age
rather than switching generation, so the curve stays continuous across every
boundary. AP-42 55/40/5 remains a mature-landfill ceiling. Manifest format 10
records generation, phase provenance, convergence evidence, and bin width.
Phase I enforces its gas allow-list, but cited fresh-waste source strengths are
still absent; Statheropoulos provides bin concentrations, while Waste
Management 2017 remains paywalled.

**What does not work:** absolute concentrations are not mesh-converged. The
source is a mass flux and scalar transport includes `D + ν_t/Sc_t`, but the
current containing-cell gate still reaches 266.29% while the k-epsilon velocity
field is also mesh-dependent. The workspace restores the latest compatible run;
side-by-side comparison and PDF reporting remain unimplemented. The ventilation
flag is persisted as requested but unmodelled and has no effect on the case.
Fuel-basis RDF parameters (NCV, ash, Cl) still need laboratory input, so no
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
| 2.5 Physics verification | **Blocked** | Mesh independence fails at 266.29% worst containing-cell deviation; see below |
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
| 3.1 Run history manager | Done — `core/history.py`; persistent `run-NNN/run.json` manifests (format version 10), `list_runs()` / `get_run()` |
| 3.2 Comparison view | Not started — history is restored in the workspace, but no side-by-side comparison UI exists; superseded in scope by T-142 |
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
panel mirrors composition, holding time, tonnage, moisture, and stream into the
scenario the run uses, and manifest format 10 records them plus bin width.

| Sub-phase | Content | Status |
|---|---|---|
| W0 | Composition, phase, Eq. HH-1 generation, moisture, manifest history through v10 | Done |
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
is refined 2×. Two reworks have cut the deviation but not closed it — worst
probe, measured 2026-09-19:

| Stage | Worst-probe deviation |
|---|---|
| pre-Phase-5 `fixedValue` concentration | ~87% |
| Phase 5 mass-flux boundary | ~63% |
| Phase 6 turbulent transport (Sc_t = 0.7), nearest-cell sampling | ~19% |
| Phase 7 corrected source + containing-cell sampling | 266.29% |

The current containing-cell 0.50→0.25 measurement is S1 18.65%, S2 0.53%,
S3 266.29%. S3 changes sign (+1.164e-8 → -1.935e-8), so its relative metric
is dominated by trace-scalar undershoot. The old 19.5% number used nearest-cell
sampling and is not comparable.

**Cause, measured.** At the same containing cells, velocity magnitude changes
by S1 30.84%, S2 5.55%, S3 12.53%, so the k-epsilon flow is not mesh-converged
at these cell counts. The scalar also sits at the discretisation noise floor.
Lowering Sc_t is outside the cited 0.7–0.9 RANS range; Sc_t remains 0.7 rather
than being tuned to pass.

**A second, independent resolution limit was found by the T-020c audit.** Once
the source-wall `nut` was corrected, the imposed flux is `D_mol * gradient`
(~1.5e-12 in fraction·m²/s), so the molecular sublayer is `D/U ~ 6e-5 m`
against a first cell of 0.5 m. Wall-adjacent cells oscillate around zero
(300/431 negative at ~0.8× the field maximum) and the near-wall probes are
noise-dominated. At 0.125 m every probe reads positive. **This is a second
reason absolute near-wall concentrations are not yet trustworthy** and it
points at the same fix: near-wall refinement, not a larger Sc_t.

**What is trustworthy in the meantime.** The transport itself is verified
against closed-form solutions: pure advection reproduces the inlet value with
zero error, and axial diffusion matches the exponential profile within 5.5% at
Pe = 5 (`tests/verification/test_analytical_benchmarks.py`). Integrated mass
balance closes to 1.4245%. Absolute probe concentrations and placement rankings
are not established while the containing-cell mesh gate fails.

**Fix options, in order of preference:**

1. **Mesh-converged velocity field (T-021).** Refine until the velocity at the
   probes is itself stable, then demonstrate the scalar converges. This is now
   the dominant limit.
2. **Near-wall refinement.** Add boundary-layer grading normal to the waste
   surface so the first cell height is resolved.
3. **Accept and document.** Keep the flux boundary and turbulent transport and
   state clearly that values are relative screening estimates. This is the
   current position.

Phases 5 and 6 are done; the gate now depends on the velocity field (T-021),
not on the source boundary or the scalar transport.


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
