# Scentinel — Waste Intelligence Layer: Implementation Plan

**Date:** 2026-09-19
**Status:** Approved for planning
**Basis:** [gas-composition-basis.md](../../gas-composition-basis.md) — the cited
scientific foundation this plan implements
**Prerequisite reading:** [ROADMAP.md](../../ROADMAP.md), [TASKS.md](../../TASKS.md)

---

## 1. Why this plan exists

Scentinel today answers *"what concentration does each candidate sensor see?"*
It cannot answer *"what should we do with this waste?"* — which is the question
the team is actually asked.

The gap is not cosmetic. Three defects were measured, not inferred:

| Defect | Evidence | Consequence |
|---|---|---|
| **Wrong generation basis** | AP-42 Ch.2.4 (landfill, anaerobic, aged) drives a "waste collection vehicle" model (fresh, aerobic) | CH₄ ≈ 500 000 ppmv for waste loaded hours ago; wrong by orders of magnitude |
| **Uncited linear scaling** | `organic_fraction / 0.50` has zero citations in `docs/` and no basis in the literature reviewed | Produces physically impossible composition: `green-waste` → 85% CH₄ vs a 55% ceiling |
| **Dead input** | `inspect.getsource(auto_concentration_ppmv)` — `moisture` never referenced | `moisture_fraction` is persisted and displayed but changes nothing |
| **Decorative RDF block** | `halogen_load()` takes no `scenario` argument; three different waste types produce byte-identical output | The RDF panel does not respond to any input |

The plan below replaces the linear-scaling guess with the EPA's own regulatory
model, adds the mass balance that turns composition into yield, and builds the
decision output on top.

**Governing rule, from the basis document:** *a value without a citation does
not enter the model.* Where no cited value exists, the output states the gap
rather than filling it.

---

## 2. What is already accurate (do not rebuild)

Measured 2026-09-19 by `tests/verification/test_analytical_benchmarks.py`:

| Capability | Measurement | Verdict |
|---|---|---|
| Advection transport | worst \|C−1\| = **0.0000** | exact |
| Axial diffusion vs closed form | deviation **0.0552** (Pe=5, 100 cells) | correct for first-order |
| Probe bounds | within [0, source] | invariant holds |
| Per-gas diffusivity | Fuller-Schettler-Giddings, reaches `scalarTransport` D | verified in generated case |
| Container isolation | `~/.scentinel/containers`, 1.7 GB, user storage untouched | verified |
| Run manifest | version 3, digest over case inputs | verified |

**The solver is trustworthy. The inputs are not.** This plan fixes the inputs.

---

## 3. What is not accurate (and blocks what)

| Blocker | Measurement | Blocks |
|---|---|---|
| Mesh independence | 56.4% / 87.2% / 8.5% deviation under 2× refinement | Any absolute-concentration claim, including sensor thresholds |
| `fixedValue` source term | flux scales with first cell height | Above; the fix is a mass-flux boundary |
| Fresh-waste gas composition | no cited values in the repo for the aerobic phase | All characterization output |

The first two are the pre-existing T-020/T-021 chain and stay first in the
queue. The third is new work this plan defines.

---

## 4. Architecture of the new layer

```
INPUTS                          ENGINE                          OUTPUTS
──────────────────────────────────────────────────────────────────────────────
composition (7 fractions) ─┐
age_h (holding time)      ─┤
tonnage per batch         ─┼─► generation.py (HH-1) ──┬─► characterization
moisture                  ─┤    massbalance.py        ├─► suitability scores
sensor (CFD + lab model)  ─┤    quality.py            ├─► yield per stream
process parameters        ─┘    suitability.py        ├─► quality prediction
                                                       ├─► interpretation
                                                       ├─► forecast
                                                       └─► recommendation
```

Every arrow is computed from cited inputs. No arrow invents a number.

---

## 5. Phases

| Phase | Content | Exit criterion |
|---|---|---|
| **W0** | Composition & generation model | A batch described by fractions + age yields gas generation from Eq. HH-1, with the phase selected by age |
| **W1** | Mass balance & yield | 10 t in → per-stream tonnage out, summing to the input within 0.1% |
| **W2** | Quality & suitability | RDF quality parameters and route scores respond to composition, or state which need laboratory data |
| **W3** | Interpretation, forecast, recommendation | A batch produces a one-line actionable recommendation traceable to its inputs |
| **W4** | UI for the decision flow | The flow characterization → simulation → recommendation is navigable end to end |

W0 is the critical path. W1–W3 depend on it. W4 can start once W1 lands.

---

## 6. Task breakdown

### Phase W0 — Composition and generation model

#### T-100 Waste composition model · TODO
Files: `src/scentinel/core/composition.py` (new), `tests/unit/test_composition.py` (new)
Why: `waste_type` is a single label that can only pick a regime. The EPA's own
material-specific option (Table HH-1) requires per-material fractions.
Change: `WasteComposition` with seven mass fractions (`food`, `garden`, `paper`,
`wood`, `textile`, `diaper`, `inert`), each carrying its Table HH-1 `DOC` and `k`
range. Validation: fractions sum to 1.0 ± 1e-6; each in [0, 1]; `k` inside its
cited range. Preset compositions for the six existing streams so nothing regresses.
Acceptance: a preset round-trips through `Project`; an invalid sum is rejected
with the offending value named; every preset's fractions match its cited source
in `docs/gas-composition-basis.md` §3.1.

#### T-101 Holding-time and phase model · TODO
Files: `src/scentinel/core/composition.py`, `tests/unit/test_composition.py`
Why: `age` is the parameter that separates a truck bin (hours, aerobic, no CH₄)
from a landfill (years, anaerobic, 55% CH₄). AP-42 §2.4.4 defines four phases by
time; the app models none of them.
Change: `age_h: float` on the scenario; `phase()` returns
`I | II | III | IV` from the AP-42 §2.4.4 description; the phase gates which
gases are generated at all.
Acceptance: `age_h=8` → phase I; `age_h=8760` → phase IV; a phase-I batch
produces CH₄ below 0.1% of ultimate yield (the decay table in the basis doc
§3.1 is the expected value).

#### T-102 Methane generation engine (Eq. HH-1) · TODO
Files: `src/scentinel/core/generation.py` (new), `tests/unit/test_generation.py` (new)
Why: the current `organic_fraction / 0.50` linear rule is uncited and can exceed
the 55% physical ceiling. EPA's regulatory model is first-order decay.
Change: implement
`G_CH4 = Σ_x W_x × MCF × DOC × DOC_F × F × (16/12) × (e^(-k(T-x-1)) - e^(-k(T-x)))`
per 40 CFR §98.343(a)(1), with `DOC_F = 0.5`, `F = 0.5`, `MCF` from the stream
type, and composition-weighted `DOC`/`k`. Cap the CH₄ volume fraction at the
AP-42 steady-state ceiling (55%).
Acceptance: ultimate yield for DOC = 0.31 is 103.3 kg CH₄/Mg (basis doc §3.2);
the 24-hour decay fraction is below 0.06% for every Table HH-1 `k`;
`CH4` never exceeds 550 000 ppmv for any composition or age.

#### T-103 Replace linear scaling in the source path · TODO
Files: `src/scentinel/core/scenario.py`, `src/scentinel/core/casegen.py`,
`tests/unit/test_scenario.py`, `tests/unit/test_casegen.py`
Why: `auto_concentration_ppmv()` is the function that produces the impossible
85% CH₄.
Change: route `auto` sources through `generation.py`. Delete
`ORGANIC_REFERENCE`, `ORGANIC_SCALE_GASES`, and the linear rule outright — no
alias, no fallback. Non-generation gases (trace species) keep their AP-42
Table 2.4-1 values but are only offered when the phase produces them.
Acceptance: `green-waste` at its preset composition no longer yields 850 000
ppmv; every generated source is traceable to either HH-1 or a Table 2.4-1 row;
`grep -r ORGANIC_SCALE_GASES src/` returns nothing.

#### T-104 Make moisture a real input · TODO
Files: `src/scentinel/core/generation.py`, `src/scentinel/core/scenario.py`,
`tests/unit/test_generation.py`
Why: `moisture_fraction` is persisted, displayed, and never used — verified by
`inspect.getsource`. AP-42 p.2.4-5 states the decay rate depends on waste
moisture.
Change: moisture selects the `k` value within its cited range (Table HH-1 gives
a range per material, keyed to precipitation/leachate in the bulk option) and
adjusts the dry-mass basis for `DOC`. Document the mapping; do not invent a
curve — use the table's own range endpoints and interpolate linearly between
them, stating that choice in the docstring.
Acceptance: two scenarios differing only in moisture produce different `k` and
therefore different generation; the mapping's endpoints match Table HH-1.

#### T-105 Manifest version 4 · TODO
Files: `src/scentinel/core/history.py`, `tests/unit/test_history.py`
Why: composition and age change what a run means. A version 3 manifest cannot
say which composition produced its concentrations.
Change: bump `RUN_FORMAT_VERSION` to 4; record the seven fractions, `age_h`,
the derived phase, and the resolved `DOC`/`k` per material. Reject version 3
rather than misread it.
Acceptance: a version 3 manifest raises with a message naming both versions; the
new manifest round-trips; `applied_physics` gains the generation inputs so a
manifest cannot claim a composition the engine did not use.

#### T-106 Extract fresh-waste VOC data · TODO — **research, blocks T-107**
Files: `docs/data/` (new artifacts), `docs/references.md`, `scripts/scrape_references.py`
Why: phase I has no cited composition in the repo. The basis document §5.1 names
three sources; none are extracted. Without this, phase I cannot be populated
honestly.
Change: extract and record, with retrieval metadata (canonical URL, UTC,
SHA-256 of the artifact), from:
- *Emission characteristics and variation of volatile odorous compounds in the
  initial decomposition stage of MSW*, Waste Manag. 2017, 68:677-687,
  DOI `10.1016/j.wasman.2017.07.015`
- Statheropoulos et al. 2005, *A study of VOCs evolved in urban waste disposal
  bins*, Atmos. Environ.
- NIOSH NMAM Method 3900 (analyte list — method only, not values)
Acceptance: each extracted value carries a page/table reference and a rating; a
source that cannot be extracted is recorded as unavailable with the reason, and
no value is estimated in its place.

#### T-107 Phase-I gas set · TODO — blocked by T-106
Files: `src/scentinel/core/generation.py`, `src/scentinel/core/gas_data.py`,
`docs/references.md`
Why: the app currently offers CH₄ for fresh waste, which the phase model says is
absent, and does not offer CO₂, which dominates.
Change: derive the phase-I gas set from T-106's extraction: CO₂, H₂S, mercaptans,
dimethyl sulfide, and the measured VOC species. Offer CH₄ only above the phase
threshold.
Acceptance: a phase-I scenario cannot select CH₄ (the checkbox is absent, not
merely disabled); CO₂ appears with a cited default; the gas list is a function of
`age_h`.

---

### Phase W1 — Mass balance and yield

#### T-110 Batch mass balance · TODO
Files: `src/scentinel/core/massbalance.py` (new), `tests/unit/test_massbalance.py` (new)
Why: the user's expected output is tonnage per stream ("10 t in → 6.4 t RDF"). No
mass model exists today (`tonnage` has zero hits in `src/`).
Change: `Batch(tonnage_t, composition, moisture)` → per-stream mass by applying
each material's routing fraction. Moisture leaves as a separate stream, not
folded into the product.
Acceptance: streams sum to the input within 0.1%; a 10 t batch at the mixed-MSW
preset produces plausible split fractions; zero tonnage raises rather than
returning zeros.

#### T-111 Route split fractions · TODO — **needs cited basis**
Files: `src/scentinel/core/massbalance.py`, `docs/references.md`
Why: how much of each material goes to RDF vs recycling vs composting is a
process property, not a physical constant.
Change: define routing as an explicit, editable process parameter with a cited
default where one exists, and an explicit "user assumption" provenance where one
does not. Never present an assumption as a citation.
Acceptance: each split fraction displays its provenance in the UI and records it
in the manifest; a user-edited fraction is recorded as `user input`, exactly as
manual gas sources already are.

#### T-112 Process-parameter sensitivity · TODO
Files: `src/scentinel/core/massbalance.py`, `src/scentinel/ui/`
Why: the user asked to change a parameter and see the effect ("sorting better →
RDF yield +14%").
Change: recompute the balance on parameter change and report the delta against
the previous setting, labelled as a sensitivity, not a prediction.
Acceptance: changing one split fraction reports the tonnage delta for every
stream it touches; the report names which parameter moved.

---

### Phase W2 — Quality and suitability

#### T-120 RDF quality parameters · TODO — **partially blocked on lab data**
Files: `src/scentinel/core/quality.py` (new), `tests/unit/test_quality.py` (new)
Why: NCV, ash, and fuel-basis chlorine are what an offtaker buys. The basis
document §6.4 states these cannot be derived from the gas phase — the gas does
not know the mass of the fuel.
Change: three explicit input modes, never mixed:
1. **Measured** — the user enters laboratory values; provenance `laboratory`.
2. **Correlated** — only if a cited correlation from composition exists; the
   task is to search for one and record the citation or record its absence.
3. **Unknown** — reported as needing laboratory data.
Acceptance: with no lab input the fields read "requires laboratory
characterisation" and the overall verdict does not claim a grade; with lab input
they show the entered values and the provenance; no path produces a number with
provenance `None`.

#### T-121 EN 15359 / ISO 21640 class assignment · TODO — blocked by T-120
Files: `src/scentinel/core/quality.py`, `docs/references.md`
Why: the user asked for "estimated RDF grade".
Change: map NCV/Cl/ash to the standard's class grid **only** when all three are
measured or correlated with a citation. Otherwise state which input is missing.
Acceptance: a complete input set yields a class and the standard clause it comes
from; an incomplete set names the missing parameter and yields no class.

#### T-122 Fix the decorative RDF block · TODO
Files: `src/scentinel/core/assessment.py`, `src/scentinel/ui/results_panel.py`,
`tests/unit/test_assessment.py`
Why: measured today — `halogen_load()` takes no `scenario`, so three different
waste types produce byte-identical output. The panel does not respond to input.
Change: make the halogen and sulfur loading a function of the composition and
the selected trace species, scaled by the batch tonnage so the number means
something. If the composition cannot support it, say so.
Acceptance: two different compositions produce different loading; the value
changes when tonnage changes; the panel text names the composition it used.

#### T-123 Suitability scoring · TODO
Files: `src/scentinel/core/suitability.py` (new), `tests/unit/test_suitability.py` (new)
Why: the user asked for scores per route (RDF 87%, recycling 42%, composting 18%).
Change: score each route from composition, moisture, and quality parameters.
Each score carries the inputs it used and the rule that produced it. A score
whose inputs are missing is reported as `insufficient_data`, never as a number.
Acceptance: a dry, high-paper batch scores higher for RDF than a wet, food-heavy
one; a batch missing a required parameter yields `insufficient_data` for that
route; every score exposes its rule.

---

### Phase W3 — Interpretation, forecasting, recommendation

#### T-130 Sensor interpretation layer · TODO
Files: `src/scentinel/core/interpret.py` (new), `tests/unit/test_interpret.py` (new)
Why: the user wants "TVOC tinggi" translated into meaning, not just displayed.
Change: map measured and simulated values to stated interpretations with their
basis. Two rules that must hold: an interpretation names the threshold or
mechanism it rests on, and it never asserts a cause the data cannot show.
Acceptance: a TVOC above the configured limit produces a stated interpretation
citing the limit; a value below detection produces "no exposure detected", not a
trend claim; interpretations are translatable (en/id).

#### T-131 Batch history persistence · TODO
Files: `src/scentinel/core/batchhistory.py` (new), `tests/unit/test_batchhistory.py` (new)
Why: forecasting needs history; nothing stores batches today.
Change: append-only batch records beside the project, same discipline as
`history.py` (immutable, never-reused ids, strict load). Reuse the manifest
patterns rather than inventing a second scheme.
Acceptance: records survive a restart; a corrupt record is reported
individually, not hidden; ordering is stable.

#### T-132 Tonnage forecasting · TODO — blocked by T-131
Files: `src/scentinel/core/forecast.py` (new), `tests/unit/test_forecast.py` (new)
Why: the user asked for daily/weekly/monthly tonnage and required capacity.
Change: forecast from recorded history with an explicitly named method and its
error. With too few records, report that rather than extrapolating from noise.
Acceptance: a synthetic linear series is recovered within a stated tolerance;
fewer than N records yields `insufficient_history`; the method and the sample
count appear in the output.

#### T-133 Decision recommendation · TODO — blocked by T-123, T-130
Files: `src/scentinel/core/recommend.py` (new), `tests/unit/test_recommend.py` (new)
Why: the user called this "output paling penting" — e.g. *"recommended for RDF
after moisture reduction"*.
Change: rank routes by their suitability score and produce one recommendation
with its reason and its caveats. It must refuse to recommend when the inputs are
insufficient, and must carry the screening caveat while mesh independence fails.
Acceptance: the recommendation names the route, the reason, and every input it
rested on; an insufficient batch yields "not enough information" plus the
missing list; the text never presents a screening estimate as a measurement.

---

### Phase W4 — UI for the decision flow

#### T-140 Characterization panel · TODO
Files: `src/scentinel/ui/characterization_panel.py` (new), `src/scentinel/ui/home_window.py`
Why: the setup panel is a CFD form. The user's flow starts from the waste, not
the mesh.
Change: a panel for composition, age, tonnage, and moisture that emits a
`Batch`, with the derived phase and generation preview shown live.
Acceptance: editing a fraction updates the preview without a solve; the panel
emits a valid `Batch` or names the invalid field.

#### T-141 Decision panel · TODO — blocked by T-133
Files: `src/scentinel/ui/decision_panel.py` (new)
Why: the outputs exist in core but have no surface.
Change: one panel showing characterization → suitability → yield → quality →
recommendation, each row traceable to its inputs.
Acceptance: every displayed number carries its provenance or its "needs lab"
state; nothing shows a placeholder that looks like a result.

#### T-142 Scenario comparison · TODO
Files: `src/scentinel/ui/comparison_view.py` (new), `tests/ui/test_comparison_view.py` (new)
Why: the user asked for A vs B vs C deltas. This is also the pre-existing T-031.
Change: compare recorded runs and batches side by side with a difference column,
consuming the strict `load_run()` contract, refusing to compare runs whose
`case_input_digest` differs unless the mismatch is explicit, and never
differencing by `ventilation.requested_on` while `ventilation.modelled` is false.
Acceptance: a difference column matches the underlying values; a digest mismatch
blocks the comparison; every compared row shows its quality classification.

#### T-143 Layout redesign · TODO
Files: `src/scentinel/ui/theme.py`, `src/scentinel/ui/home_window.py`, locale files
Why: the user explicitly permitted this ("kalo lu butuh redesign layout dan
fungsi juga boleh banget"). The current shell was built around a CFD form.
Change: restructure the shell around the decision flow, keeping the top toolbar
and the single shared project. Every user-visible string goes through
`Translator.t` with keys in both locales.
Acceptance: the flow is navigable end to end without a solve; the offscreen UI
suite passes; no string is hardcoded.

---

## 7. Prerequisite work (pre-existing, still blocking)

| Task | Why it gates this plan |
|---|---|
| **T-020** Mass-flux source term | Absolute concentrations are unreliable until this lands; the threshold output and any quality decision inherit that |
| **T-021** Mesh-independence gate | The measured 56.4%/87.2% deviation is the reason every concentration is labelled `screening_estimate` |
| **T-024** Field visualisation | Already implemented (`ui/field_view.py`); TASKS.md still lists it as TODO — correct the record |

---

## 8. Sequencing

```
T-020 mass-flux ──► T-021 mesh independence ─┐
                                             ├──► credibility for W2/W3 output
T-100 composition ──► T-101 phase ──► T-102 HH-1 ──► T-103 replace scaling ──┐
                                                              T-104 moisture ─┤
                                                                  T-105 v4 ───┤
                                                                              ▼
T-106 extract VOC ──► T-107 phase-I gases ──────────────────────────► W1 yield
                                                                              │
                                                          W2 quality/suitability
                                                                              │
                                              T-131 history ──► T-132 forecast
                                                                              ▼
                                                                    W3 recommendation
                                                                              │
                                                                    W4 UI redesign
```

T-020/T-021 and T-100/T-102 are independent tracks and can run in parallel.
W2 cannot produce a defensible grade until T-120's lab-or-cited question is
answered, so that research task starts early.

---

## 9. Verification strategy

Every phase adds a gate that a plausible bug would fail:

| Gate | Test | Passes when |
|---|---|---|
| Generation physics | `test_generation.py` | ultimate yield 103.3 kg/Mg; 24 h < 0.06% of ultimate; CH₄ ≤ 55% always |
| Mass conservation | `test_massbalance.py` | streams sum to input within 0.1% |
| Provenance | `test_recommend.py` | no output number has provenance `None` |
| Responsiveness | `test_assessment.py` | two compositions produce different loading |
| Solver accuracy | `test_analytical_benchmarks.py` | advection 0.0000; diffusion < 8% |
| Phase gate | `test_composition.py` | phase-I cannot select CH₄ |

The existing `screening_estimate` classification stays until T-021 passes. No
output from this layer may claim more confidence than the transport underneath it.

---

## 10. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| T-106 finds no usable fresh-waste VOC data | Phase I cannot be populated | Report the gap; offer only gases that do have citations; do not estimate |
| No cited composition→NCV correlation exists | RDF grade cannot be computed without lab data | Ship lab-input mode only; state the limitation in the UI and README |
| Routing fractions are process assumptions | Yield numbers look authoritative but are not | Provenance per fraction; user edits recorded as `user input` |
| Scope: this is a large layer | The CFD core could stall | W0 first; each phase ships independently; T-020/T-021 stay top of queue |
| Manifest churn (v3 → v4) | Old runs unreadable | Deliberate: a v3 record cannot describe a v4 composition. Document the break |
