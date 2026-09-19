# Scentinel Hardening Program — Master Plan

> **For agentic workers:** This master plan defines the program and each task's
> contract. It is **not** the per-phase execution plan. At each phase kickoff,
> write `docs/superpowers/plans/YYYY-MM-DD-phase-N-<slug>.md` with bite-sized
> TDD steps (superpowers:writing-plans), then execute that plan with
> superpowers:subagent-driven-development or superpowers:executing-plans.
> Checkbox (`- [ ]`) step lists live only in the per-phase plans.

**Date:** 2026-09-19
**Status:** Active — Phase 0 in progress
**Baseline tag:** `v0.2.2-audit` (points at the Phase 0 commit)
**Program brief:** user directive, 2026-09-19 — 20 phases reproduced in §3
**Basis:** [gas-composition-basis.md](../../gas-composition-basis.md) ·
[ROADMAP.md](../../ROADMAP.md) · [TASKS.md](../../TASKS.md) ·
[ARCHITECTURE.md](../../ARCHITECTURE.md) ·
[design spec](../specs/2026-09-18-scentinel-design.md)

---

## 1. Goal

Make each link of the chain *waste description → decomposition → gas generation
→ CFD source → transport → sensor → interpretation → quality → recommendation*
explicitly defined, provenance-labelled, and gated by a test that fails on the
old behaviour — **before** any 3D, transient, or UI-redesign work starts.

The audit that produced v0.2.2 found the pattern behind the defects: values
whose basis was never stated (uncited linear scaling, phase cutoffs treated as
physical truth, cumulative gas labelled "produced now", a `fixedValue`
concentration presented as a source strength, heuristic scores presented as a
decision model). This program removes that pattern from every layer.

**Out of scope until the program completes:** any feature not listed in §3.
Phase 0 freezes scope; changes to this document require an explicit edit plus a
CHANGELOG entry.

---

## 2. Global constraints

These apply to every phase; each per-phase plan repeats them in its own
"Global Constraints" section.

1. **Governing rule:** *a value without a citation does not enter the model.*
   Where no cited value exists, the output states the gap rather than filling
   it. (Established in `docs/gas-composition-basis.md`.)
2. **Provenance vocabulary** — every scientific or process value carries exactly
   one label: `cited`, `derived`, `model assumption`, `user input`,
   `laboratory`, `unavailable`. No path may emit a number with provenance
   `None` or an unlabelled default.
3. **TDD Iron Law:** no production code without a failing test first. Each task
   lands as: failing test → run it → minimal implementation → green → commit.
4. **Suite stays green.** Baseline at Phase 0: `566 passed`
   (`.venv/bin/pytest -q`). Ruff baseline: 67 findings across
   `src tests scripts` (never ruff-clean); no *new* findings.
5. **Manifest/project versioning.** Any change to a persisted schema bumps
   `RUN_FORMAT_VERSION` (`core/history.py`) or `FORMAT_VERSION`
   (`core/project.py`) and either migrates old records or rejects them naming
   both versions. Known bumps: project v2 + manifest v5 (T-213/T-214),
   manifest v6 (T-224), manifest v7 (T-020).
6. **i18n:** every user-visible string goes through `Translator.t` with keys in
   both `resources/locales/en.json` and `id.json` — until Phase 18 replaces the
   shell, after which the same rule applies to the new UI's message catalogue.
7. **Python:** CI runs 3.12 (`pyproject.toml` `target-version = py312`); the
   local venv is 3.14. No new runtime dependency without a written
   justification, and none scientific without a citation.
8. **Commits:** conventional-commit style as in `git log`; one task per commit
   where practical; docs updated in the same commit as the behaviour they
   describe.
9. **Commands:** unit+UI `.venv/bin/pytest tests/unit tests/ui -q`; full suite
   `.venv/bin/pytest -q`; container gates `.venv/bin/pytest -m integration -q`
   and `.venv/bin/pytest -m verification -q`; lint
   `.venv/bin/ruff check src tests scripts`.
10. **No silent defaults.** Every default (routing fraction, phase cutoff, Sc_t,
    split efficiency) is labelled and inspectable in the UI or the manifest.

---

## 3. Phases and tasks

### Phase 0 — Scope freeze and baseline · T-200

**Goal:** freeze scope, sync the docs to the code, tag the baseline.

**Depends on:** nothing. **Blocks:** every phase.

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-200 Baseline freeze | `v0.2.2-audit` tag on the doc-sync commit; ROADMAP/TASKS/ARCHITECTURE/README/gas-basis claim nothing the code does not do | `docs/*`, `README.md`, `CHANGELOG.md` | `git tag` lists the baseline; full suite green; no stale status/number remains (checked by grep for the known stale strings) |

---

### Phase 1 — Material taxonomy · T-210…T-214

**Goal:** physical materials and decomposition categories become separate
things. Plastic is **not** inert for RDF or recycling; it is inert only for
HH-1 decomposition.

**Depends on:** Phase 0. **Blocks:** Phases 2, 4, 8, 10, 12.

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-210 Material taxonomy | `Material` dataclass + registry for the 15 materials: `food`, `garden`, `paper`, `wood`, `textile`, `diaper`, `sludge`, `PET`, `HDPE`, `LDPE`, `PP`, `PVC`, `glass`, `metal`, `other-inert`. Each carries `hh1_category`, `recyclable`, `rdf_feedstock`, `chlorine_fraction: float \| None`, and its citation | `core/materials.py` (new), `tests/unit/test_materials.py` (new) | every material maps to exactly one HH-1 category; PVC's chlorine figure is cited or `None` with a stated gap (no invented number); `glass`/`metal` have `rdf_feedstock=False`; mass fractions still sum to 1 |
| T-211 Material → HH-1 mapper | `decomposition_view(materials) -> WasteComposition`; plastics/glass/metal contribute to `inert` for decomposition | `core/materials.py`, `tests/unit/test_materials.py` | mapped fractions sum to 1 within 1e-9; PVC/PET add zero DOC; a material composition round-trips through `WasteComposition` without loss |
| T-212 RDF/recycling read materials | plastic share, PVC chlorine risk, metal/glass exclusion; `halogen_load()` becomes a function of composition | `core/suitability.py`, `core/assessment.py`, `tests/unit/test_assessment.py` | two batches differing only in PVC share produce different chlorine risk; metal/glass are never counted as RDF feedstock; the halogen block responds to composition and tonnage (retires T-122) |
| T-213 Project format v2 + migration | `.scentinel` stores material keys; v1 files migrate (`inert` → `other-inert`) and load | `core/project.py`, `core/scenario.py`, `tests/unit/test_project.py` | a v1 fixture loads through migration; unknown material key is rejected naming the key; presets do **not** invent a plastic split — where no cited split exists the share stays `other-inert` with the gap stated |
| T-214 Manifest v5 | run manifests record the material composition; v4 rejected naming v5 | `core/history.py`, `tests/unit/test_history.py` | v4 manifest raises naming both versions; v5 round-trips; a hand-edited manifest with an unknown material key is rejected |

**Exit gate:** `decomposition_view` conservation test passes; the RDF block
changes when composition changes; old project and old manifest behaviour is
explicit (migrate or reject), never silent.

---

### Phase 2 — Gas-generation definitions · T-220…T-224

**Goal:** stop conflating three different quantities. Ultimate potential,
cumulative generated, and instantaneous rate are separate outputs with separate
units.

**Depends on:** Phase 1. **Blocks:** Phase 5 (CFD source needs a rate).

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-220 Three quantities | `ultimate_gas_potential()` (kg/t), `cumulative_gas(age_h)` (kg), `generation_rate(age_h)` (kg/s, with a kg/h helper) | `core/generation.py`, `tests/unit/test_generation.py` | `generation_rate` equals the analytical derivative of `cumulative_gas` within 1e-6 relative; `cumulative_gas` is monotone non-decreasing in age; units are in the names and the docstrings |
| T-221 UI truth-in-labelling | `batch.readout.gas_now` replaced by two readouts: cumulative (kg) and rate (kg/h); locale keys in en/id | `ui/batch_panel.py`, `resources/locales/{en,id}.json`, `tests/ui/test_batch_panel.py` | no label describes cumulative mass as "produced now"; both readouts show units; the rate changes with age while cumulative also changes |
| T-222 Continuity across age | tests that generation is continuous across the phase boundaries | `tests/unit/test_generation.py` | `\|rate(t−ε) − rate(t+ε)\| < tol` at 48 h, 90 d, 365 d; cumulative has no step |
| T-223 Phase is interpretation, not a switch | the generation math never consults `phase_for()`; `PHASE_GASES` becomes applicability metadata | `core/generation.py`, `core/composition.py`, `core/scenario.py`, `tests/unit/test_scenario.py` | removing/monkeypatching the stage function changes no generation number; the II→III CH₄ jump is gone; where a phase's model does not apply, the output says so instead of emitting zero or a landfill value |
| T-224 Manifest v6 | records ultimate / cumulative / rate separately; v5 rejected | `core/history.py`, `tests/unit/test_history.py` | v5 raises naming v6; v6 round-trips; a manifest cannot claim a rate the model did not compute |

**Exit gate:** continuity tests pass at every boundary; no UI string or manifest
field calls cumulative gas a rate.

---

### Phase 3 — Phase model · T-230…T-232

**Goal:** the 48 h / 90 d / 365 d cutoffs become an explicit, cited-as-assumed
model choice, and decomposition stage is separated from continuous decay.

**Depends on:** Phase 2.

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-230 Cutoffs as assumptions | a `PhaseModel` value object: `boundary_hours`, `provenance="model assumption"`, `basis` text (AP-42 narrative), `uncertainty` note; module constants become members | `core/composition.py`, `tests/unit/test_composition.py` | no code path treats a boundary as measured; the model object is serialisable into the manifest; docs name the assumption |
| T-231 Stage vs decay separation | `decomposition_stage(age_h)` is pure interpretation; decay math is independent | `core/composition.py`, `core/generation.py`, `tests/unit/test_generation.py` | generation output is byte-identical with the stage function stubbed; a test asserts the decoupling |
| T-232 Phase provenance in output | every phase interpretation carries `source`, `applicability`, `uncertainty` and reaches the UI/manifest | `core/generation.py`, `core/history.py`, `ui/batch_panel.py` | each gas row shows phase applicability and uncertainty; a phase with no cited model reports `unavailable` rather than a default |

**Exit gate:** the phase label never changes a number; every boundary has a
provenance label.

---

### Phase 4 — Fresh-waste model · T-106, T-107

**Goal:** phase I gets its own cited gas set instead of landfill trace defaults
presented as equivalent.

**Depends on:** Phase 1 (taxonomy), Phase 3 (applicability). Research task
T-106 can start immediately and runs in parallel.

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-106 Fresh-waste research extraction | cited values for fresh MSW / bin waste: paper fresh-MSW VOC profile; H₂S, mercaptans, NH₃, VOC, terpenes; acquisition metadata (URL, UTC, SHA-256) | `docs/data/fresh_waste_*.json` (new), `docs/references.md`, `scripts/scrape_references.py` | every extracted value has a page/table reference and rating; a source that cannot be extracted is recorded `unavailable` with the reason; no value estimated in its place |
| T-107 Phase-I gas set | gas catalogue gains `source`, `applicability`, `phase`, `uncertainty`; phase-I selection is a function of `age_h` | `core/generation.py`, `core/gas_data.py`, `docs/references.md`, locale files, tests | phase I offers only cited phase-I gases; CH₄ is absent (not merely disabled) below the threshold; landfill trace defaults are never offered for phase I as if equivalent; every gas row carries applicability + uncertainty |

**Exit gate:** a fresh bin reports only gases whose phase-I basis exists, each
labelled; a missing basis is a stated gap.

---

### Phase 5 — CFD source term · T-020

**Goal:** the source becomes an emission mass flux (kg/m²/s), so tonnage and age
actually drive the CFD.

**Depends on:** Phase 2 (rate in kg/s), Phase 3. **Blocks:** Phase 7 gates.

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-020 Mass-flux source | chain `batch → rate kg/s → emitting area m² → kg/m²/s → CFD boundary`; UI exposes the flux with its derivation; manifest v7 | `core/casegen.py`, `core/scenario.py`, `core/history.py`, `ui/setup_panel.py`, `tests/unit/test_casegen.py`, `tests/verification/*` | `pytest -m verification` shows probe deviation <10% between 0.5 m and 0.25 m with a monotone trend; changing tonnage or age changes the CFD source; the source strength is **not** derived from the 55% mole fraction |

**Exit gate:** mesh deviation <10% and monotone; source provenance visible in
the manifest.

---

### Phase 6 — Turbulent scalar transport · T-240

**Goal:** dispersion is not molecular diffusion alone.

**Depends on:** Phase 0. Can run in parallel with Phases 2–5.

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-240 Turbulent diffusivity | `D_eff = D_molecular + ν_t / Sc_t`; `Sc_t` is a named constant with citation or explicit `model assumption`; documented | `core/casegen.py`, `docs/ARCHITECTURE.md`, `docs/references.md`, `tests/unit/test_casegen.py` | the generated case carries the turbulent term; `Sc_t` appears in `applied_physics`; a sensitivity test over Sc_t quantifies its effect; a molecular-only vs turbulent benchmark is recorded under `tests/verification/` |

**Exit gate:** no field is solved with molecular diffusion as the only
transport mechanism, and Sc_t's basis is stated.

---

### Phase 7 — CFD verification gates · T-021, T-022, T-241, T-242

**Goal:** the gates become automated, and "exit code 0" stops standing in for
convergence or valid sampling.

**Depends on:** Phases 5 and 6.

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-021 Mesh-independence gate | assert <10% with monotone trend | `tests/verification/test_mesh_independence.py` | test fails if deviation ≥10% or the trend reverses |
| T-022 Mass-balance gate | integrated source flux vs outlet flux, automated | `core/post.py`, `tests/verification/test_mass_balance.py` | <5% on a converged case |
| T-241 Residual parsing + convergence state | parse the `residuals` function object; `quality.convergence` is `passed`/`failed`/`not_evaluated` with the reason; `solver_termination` parsed | `core/post.py`, `core/history.py`, `core/pipeline.py`, tests | a converged case reports `passed`; a max-iterations case reports `failed`; exit 0 alone never marks convergence; the reason string is persisted |
| T-242 Sensor containment validation | replace `find_closest_cell()` with containment validation; reject sensors outside the fluid domain (and inside the mound) at placement and at sampling; persist the diagnostic | `core/post.py`, `ui/viewport.py`, tests | an invalid sensor is rejected with a reason; a valid one samples its containing cell; no silent nearest-cell fallback remains |

**Exit gate:** both numeric gates pass; convergence and containment are
automated and persisted.

---

### Phase 8 — RDF quality model · T-120

**Goal:** quality parameters become explicit laboratory/cited inputs, never
inferred from the gas phase.

**Depends on:** Phase 1. **Blocks:** Phases 9, 10, 11.

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-120 Quality model rework | `core/quality.py`: NCV, chlorine, mercury, moisture; ash as additional characterization; per-field provenance `laboratory` / `cited correlation` / `unavailable` | `core/quality.py` (new), `core/suitability.py`, `ui/results_panel.py`, `tests/unit/test_quality.py` (new) | no lab input → "requires laboratory characterisation" and no number; an entered value carries its provenance; no path returns a number with provenance `None`; a test proves no CFD reading can populate NCV/Cl/Hg |

**Exit gate:** every quality field is either laboratory, cited correlation, or a
stated gap.

---

### Phase 9 — ISO 21640 classification · T-121

**Goal:** a real classification with the standard's table entered from an
official source, or no class.

**Depends on:** Phase 8.

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-121 ISO 21640 class | the standard's classification table entered with citation; class assigned only when every required parameter is available | `core/quality.py`, `docs/references.md`, `tests/unit/test_quality.py` | complete input → class + clause reference; one missing parameter → `classification unavailable` naming it; the table's source is cited in `docs/references.md` |

**Exit gate:** no class without all required parameters; the table is cited.

---

### Phase 10 — Suitability engine v2 · T-250

**Goal:** separate four things the current heuristic mixes: screening score,
process eligibility, quality compliance, final recommendation. Retires T-122.

**Depends on:** Phases 1, 8 (quality gates), 12 (streams).

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-250 Suitability v2 | four independently inspectable layers; plastic contribution to RDF; PVC → chlorine risk; metal/glass excluded as feedstock; facility routing editable with `user input` provenance | `core/suitability.py`, `core/recommend.py`, tests | each layer can be read alone; PVC lowers RDF eligibility through the chlorine gate; metal/glass never contribute to a feedstock score; an edited routing table changes scores and is labelled `user input` |

**Exit gate:** no heuristic is presented as the final decision; every layer
names its inputs and its basis.

---

### Phase 11 — Recommendation gating · T-251

**Goal:** no "Recommended for RDF" before the quality gates pass.

**Depends on:** Phase 10 (and Phase 9 for the gate).

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-251 Gated recommendation | pre-quality states: `RDF candidate` / `RDF pre-screening suitable`; final recommendation only after quality gates pass; otherwise `requires laboratory characterisation`; confidence/state always visible | `core/recommend.py`, `ui/batch_panel.py`, locale files, tests | incomplete quality → no final recommendation, with the missing list; complete quality → final recommendation includes each gate result; the state label is always rendered |

**Exit gate:** the word "recommended" cannot appear without its gates.

---

### Phase 12 — Waste mass balance v2 · T-260

**Goal:** mass closure with explicit sorting efficiency, contamination/loss, and
moisture removal.

**Depends on:** Phase 1. Feeds Phase 10.

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-260 Mass balance v2 | facility-editable sorting efficiency per stream; contamination/loss; moisture removal; outputs: feed, recovered RDF, recyclable, organic, residue, water/loss | `core/massbalance.py`, `ui/batch_panel.py`, tests | closure is exactly 100% within 1e-9 relative for every parameter set; each stream and each loss carries provenance; an edited efficiency is labelled `user input`; T-112 sensitivity reports the delta per stream |

**Exit gate:** closure test passes across a parameter sweep, not one example.

---

### Phase 13 — Interpretation layer · T-130

**Goal:** a sensor value becomes a stated interpretation with a threshold and a
basis — never a causal claim.

**Depends on:** Phases 7 (valid sampling), 8 (quality context).

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-130 Interpretation | states `detected`, `elevated`, `threshold exceedance`, `unknown`; every interpretation names its threshold or basis; en/id strings | `core/interpret.py` (new), `tests/unit/test_interpret.py` (new), locale files | above-limit → `threshold exceedance` citing the limit; below detection → `no exposure detected`; insufficient data → `unknown`; no output asserts a cause the data cannot show |

**Exit gate:** every displayed interpretation is traceable to a threshold.

---

### Phase 14 — Scenario comparison · T-142

**Goal:** compare recorded scenarios side by side, and refuse when the physics
are not comparable.

**Depends on:** Phases 13, 15 (history), 7 (digest discipline).

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-142 Comparison | compare composition, moisture, age, gas rate, CFD concentrations, sensor coverage, RDF suitability, yield, quality, recommendation; delta column; refuse incomparable physics | `ui/comparison_view.py` (new), `tests/ui/test_comparison_view.py` (new) | deltas match the underlying values; a case-input-digest or source-basis mismatch blocks the comparison with a stated reason; every row shows its quality classification and screening caveat |

**Exit gate:** a comparison cannot silently mix different physics.

---

### Phase 15 — Batch history and forecasting · T-131, T-132

**Goal:** batches persist like runs do, and forecasting only runs on enough
data.

**Depends on:** Phase 1 (records the material composition).

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-131 Batch history | append-only batch records beside the project, same discipline as `history.py` | `core/batchhistory.py` (new), `tests/unit/test_batchhistory.py` (new) | records survive restart; never-reused ids; a corrupt record is reported individually; ordering stable |
| T-132 Forecasting | named method + error + sample count; minimum-N gate | `core/forecast.py` (new), `tests/unit/test_forecast.py` (new) | a synthetic linear series recovered within a stated tolerance; fewer than N records → `insufficient_history`; method and N appear in the output |

**Exit gate:** no forecast without a stated method, error, and sample count.

---

### Phase 16 — CI/CD · T-270…T-272

**Goal:** every push and PR is gated; the release cannot publish red.

**Depends on:** nothing. Recommended to run early, in parallel.

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-270 CI workflow | ruff, unit, UI headless (`QT_QPA_PLATFORM=offscreen`), scientific non-container tests, build check, on push/PR | `.github/workflows/ci.yml` (new) | a failing lint or test fails the workflow; jobs split so the fast gate reports first |
| T-271 Release gated on CI | release workflow requires the CI workflow to pass for the same ref | `.github/workflows/release.yml` | a red CI run blocks the release; verified by a deliberate failing branch or `workflow_run` dry-run |
| T-272 Nightly verification | scheduled + manual OpenFOAM container verification (integration + verification markers) | `.github/workflows/verify-nightly.yml` (new) | runs on `schedule` and `workflow_dispatch`; artifacts retain the log; failure notifies |
| (note) | update actions off the deprecated Node 20 majors | workflow files | no deprecation warning in a run |

**Exit gate:** CI is required for merge; release depends on it.

---

### Phase 17 — Documentation provenance cleanup · T-280

**Goal:** every scientific assumption in the docs carries one of the six
provenance labels, and stale numbers/statuses are gone.

**Depends on:** runs continuously; final pass after Phase 15.

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-280 Docs provenance pass | README, ROADMAP, TASKS, ARCHITECTURE, gas-composition-basis reviewed; stale numbers/statuses removed; each assumption labelled | `README.md`, `docs/*.md` | a grep checklist finds no known-stale string; each scientific assumption in the basis document carries a label; the doc map in ROADMAP lists every doc |

**Exit gate:** a reviewer can trace every number in the UI to a labelled basis
or a stated gap.

---

### Phase 18 — UI redesign · T-290…T-294

**Goal:** replace the presentation layer with Tauri 2 + React + TypeScript +
Tailwind + shadcn/ui + ECharts, keeping the Python scientific core.

**Depends on:** Phases 1–15. Supersedes T-141 and T-143.

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-290 Core service boundary | headless API over the Python core (JSON-RPC or local HTTP) with a versioned contract and contract tests; imports no Qt | `src/scentinel/api/` (new), `tests/api/` (new) | the full flow is callable headlessly; contract tests run in CI without a display; the core package imports without PySide6 |
| T-291 Tauri + React scaffold | Tauri 2 shell, React+TS, Tailwind, shadcn/ui, ECharts; dev and build pipelines | `ui/` (new, or `apps/`), CI build job | `cargo tauri build` (or the Linux equivalent) produces a runnable bundle in CI; lint/typecheck wired into T-270 |
| T-292 Flow screens | nine steps: Waste Input → Characterization → Gas Generation → CFD → Sensor → Treatment → Quality → Decision → Compare | `ui/src/routes/*` | the flow is navigable end to end without a solve; every step reads from the T-290 API; no placeholder that looks like a result |
| T-293 Field view + charts | concentration field, sensor telemetry, comparison deltas in ECharts | `ui/src/components/*` | field image and deltas match the API payloads |
| T-294 Packaging/release | new shell packaged for Linux/Windows; PySide removed from the presentation path (kept only if still needed for tests) | packaging scripts, release workflow | installers build; the old PySide shell is either retired or explicitly optional |

**Exit gate:** the new shell passes the same flow the PySide shell did, with the
core untouched; the old shell is retired or clearly optional.

---

### Phase 19 — 3D and transient · T-040…T-042

**Goal:** only after the 2D gates pass.

**Depends on:** Phases 5–7 (gates green), Phase 18 not required.

| Task | Deliverable | Files | Acceptance |
|---|---|---|---|
| T-040 3D geometry and meshing | extrude the 2D cross-section to the bin width; `checkMesh` passes | `core/geometry.py`, `core/mesh.py`, `core/casegen.py`, tests | a 3D case solves; mesh gate still <10% |
| T-041 Transient settings | `ddtSchemes { default backward; }`, adjustable `deltaT`, probe time series | `core/casegen.py`, tests | a transient run writes a time series at each probe |
| T-042 Response-delay analysis | time to 50% and 90% of steady state per sensor | `core/delay.py` (new), tests | matches a synthetic first-order response |

**Exit gate:** 3D and transient each carry the same verification gates as 2D.

---

## 4. Dependency map

```
Phase 0  Baseline
├─ 1  Material taxonomy ──┬─ 2  Generation definitions ─ 3  Phase model ──┐
│                         ├─ 4  Fresh waste (T-106/T-107)                │
│                         ├─ 8  Quality model ─ 9  ISO 21640             │
│                         ├─ 10 Suitability v2 ─ 11 Recommendation gate  │
│                         └─ 12 Mass balance v2 ─────────────────────────┤
├─ 5  CFD mass-flux source ◄─────────────────────────────────────────────┘
│      │
├─ 6  Turbulent transport ──► 7  Verification gates (T-021, T-022, T-241, T-242)
│                                   │
├─ 13 Interpretation ◄──────────────┘
├─ 15 Batch history + forecast ──► 14 Comparison
├─ 16 CI/CD (independent; recommended early)
├─ 17 Docs provenance (continuous; final pass after 15)
└─ 18 UI redesign (after 1–15) ──► 19 3D / transient
```

Phases 4, 6, and 16 may run in parallel with their neighbours. Everything else
runs in order.

---

## 5. Task index

| ID | Phase | One line |
|---|---|---|
| T-200 | 0 | Baseline freeze, doc sync, `v0.2.2-audit` tag |
| T-210 | 1 | 15-material taxonomy with HH-1 category + RDF flags |
| T-211 | 1 | Material → HH-1 decomposition mapper |
| T-212 | 1 | RDF/recycling consume materials; halogen load is real |
| T-213 | 1 | Project format v2 with v1 migration |
| T-214 | 1 | Manifest v5 material composition |
| T-220 | 2 | Ultimate / cumulative / rate as separate quantities |
| T-221 | 2 | UI shows cumulative kg and rate kg/h |
| T-222 | 2 | Continuity tests across ages |
| T-223 | 2 | Phase is interpretation, not a gas switch |
| T-224 | 2 | Manifest v6 generation quantities |
| T-230 | 3 | Phase cutoffs as explicit model assumptions |
| T-231 | 3 | Stage separated from continuous decay |
| T-232 | 3 | Phase provenance in output |
| T-106 | 4 | Fresh-waste VOC/H₂S/NH₃/terpene research extraction |
| T-107 | 4 | Phase-I gas set with source/applicability/uncertainty |
| T-020 | 5 | Mass-flux source kg/m²/s; manifest v7 |
| T-240 | 6 | Turbulent diffusivity and Sc_t |
| T-021 | 7 | Mesh-independence gate <10% |
| T-022 | 7 | Mass-balance gate <5% |
| T-241 | 7 | Residual parsing and convergence state |
| T-242 | 7 | Sensor containment validation |
| T-120 | 8 | Quality model: NCV, Cl, Hg, moisture; ash extra |
| T-121 | 9 | ISO 21640 classification from the official table |
| T-250 | 10 | Suitability v2: score / eligibility / compliance / decision |
| T-251 | 11 | Recommendation gating and states |
| T-260 | 12 | Mass balance v2 with efficiency, loss, moisture removal |
| T-130 | 13 | Interpretation states with thresholds |
| T-142 | 14 | Scenario comparison with refusal rules |
| T-131 | 15 | Batch history persistence |
| T-132 | 15 | Forecasting with method, error, minimum N |
| T-270 | 16 | CI on push/PR |
| T-271 | 16 | Release gated on CI |
| T-272 | 16 | Nightly OpenFOAM verification |
| T-280 | 17 | Docs provenance labels, stale claims removed |
| T-290 | 18 | Headless core API + contract tests |
| T-291 | 18 | Tauri 2 + React scaffold |
| T-292 | 18 | Nine flow screens |
| T-293 | 18 | Field view and charts |
| T-294 | 18 | Packaging and release of the new shell |
| T-040 | 19 | 3D geometry and meshing |
| T-041 | 19 | Transient settings and probe time series |
| T-042 | 19 | Response-delay analysis |

**Absorbed or superseded by this program:** T-122 → T-212/T-250; T-141 →
T-292; T-143 → T-291/T-292; T-023 stays as a Phase 7 companion; T-112 is a
Phase 12 companion.

---

## 6. Execution protocol

1. **Phase kickoff:** write
   `docs/superpowers/plans/YYYY-MM-DD-phase-N-<slug>.md` with bite-sized TDD
   steps, using this document's task contracts as the spec. No phase starts
   without its plan.
2. **Execute:** superpowers:subagent-driven-development (recommended) or
   superpowers:executing-plans. One task per commit where practical.
3. **Every task:** failing test → run it → minimal implementation → green →
   commit → update `TASKS.md` status.
4. **Phase exit:** run the phase's exit gate plus the full suite; update
   `CHANGELOG.md`; only then start the next phase (parallel-safe phases
   excepted).
5. **Scope changes:** edit this file explicitly and note it in the CHANGELOG.
   Nothing enters through the back door.

## 7. Program definition of done

- All 20 phases closed with their exit gates passing.
- `pytest -q` green, including container-marked gates where the environment
  provides them.
- Every scientific value in the UI traceable to `cited`, `derived`,
  `model assumption`, `user input`, `laboratory`, or an explicit
  `unavailable`.
- A fresh bin and an aged landfill each produce a defensible, labelled gas
  set; the CFD source is a mass flux; the quality/recommendation chain refuses
  to answer when its inputs are missing.
- The new UI runs the whole flow; the old shell is retired or optional.
- 3D and transient carry the same verification discipline as 2D.
