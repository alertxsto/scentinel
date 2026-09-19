# Phase 2 — Gas Generation Definitions: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate ultimate potential, cumulative generated gas, and instantaneous
generation rate into distinct, unit-bearing outputs; remove the phase switch so
generation is continuous in age; base the produced-gas mixture on the same
regulation as Equation HH-1 (F = 0.5) instead of applying the AP-42 mature-
landfill measured mix to every age.

**Architecture:** `core/generation.py` computes one continuous first-order decay
curve. Cumulative mass is `ultimate × (1 − e^(−k·t))`; the rate is its exact
derivative. The degraded carbon splits into CH4 and CO2 by the regulation's
`F = 0.5`; N2 is zero because it is not a decay product. The AP-42 55/40/5 mix
stays in the model as a ceiling and a comparison, not as an input. The phase
label remains on the record as an interpretation and gates nothing.

**Tech Stack:** Python 3.12+ (CI), pytest, PySide6 for the panel.

**Spec:** `docs/superpowers/plans/2026-09-19-hardening-program.md` (Phase 2,
T-220…T-224). Master plan anticipated manifest v6 after Phase 1's v5; gas work
is being done first, so the manifest bumps v4 → **v5** here and Phase 1 will
bump v5 → v6.

## Global Constraints

1. A value without a citation does not enter the model; where no cited value
   exists the output states the gap.
2. Provenance labels: `cited`, `derived`, `model assumption`, `user input`,
   `laboratory`, `unavailable`.
3. TDD: failing test → run → minimal implementation → green → commit.
4. Suite baseline: `566 passed`; ruff: no new findings.
5. Persisted-schema change bumps `RUN_FORMAT_VERSION` and rejects the old
   version naming both.
6. i18n: en/id keys for every user-visible string.
7. Commands: `.venv/bin/pytest tests/unit tests/ui -q`; full `.venv/bin/pytest -q`;
   lint `.venv/bin/ruff check src tests scripts`.

---

### Task 1 (T-220, T-223 core): one continuous generation curve, three quantities

**Files:**
- Modify: `src/scentinel/core/generation.py`
- Test: `tests/unit/test_generation.py`

**Interfaces:**
- Consumes: `WasteComposition`, `LANDFILL_GAS_METHANE_FRACTION = 0.5`,
  `STOICHIOMETRIC_RATIO = 16/12`, `decay_fraction`.
- Produces: `Generation` with `ultimate_ch4_kg`, `ch4_cumulative_kg`,
  `ch4_cumulative_m3`, `ch4_rate_kg_per_h`, `co2_cumulative_kg`,
  `co2_rate_kg_per_h`, `methane_fraction`; helpers `ultimate_carbon_kg`,
  `co2_from_carbon`, `carbon_rate_kg_per_h`; `Generation.notes` no longer
  contains "pre-methanogenic".

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_generation.py`:

```python
def test_rate_is_the_derivative_of_cumulative_mass():
    """The rate must be the same first-order curve, differentiated — not a second model."""
    preset = comp.PRESETS["mixed-msw"]
    k = preset.weighted_decay(0.4)
    age = 24.0 * 365
    eps = 0.5
    plus = gen.generate(preset, tonnage_t=10.0, age_h=age + eps, moisture=0.4)
    minus = gen.generate(preset, tonnage_t=10.0, age_h=age - eps, moisture=0.4)
    at = gen.generate(preset, tonnage_t=10.0, age_h=age, moisture=0.4)
    numeric = (plus.ch4_cumulative_kg - minus.ch4_cumulative_kg) / (2.0 * eps)
    assert at.ch4_rate_kg_per_h == pytest.approx(numeric, rel=1e-6)


def test_carbon_closes_between_methane_and_carbon_dioxide():
    """Every degraded carbon atom leaves as CH4 or CO2, by the regulation's F."""
    g = gen.generate(comp.PRESETS["mixed-msw"], tonnage_t=10.0, age_h=24 * 365 * 10, moisture=0.4)
    carbon_kg = gen.ultimate_carbon_kg(comp.PRESETS["mixed-msw"], 10.0) * g.decay_fraction
    carbon_out = (
        g.ch4_cumulative_kg / gen.METHANE_MOLAR_MASS * comp.CARBON_MOLAR_MASS
        + g.co2_cumulative_kg / gen.CO2_MOLAR_MASS * comp.CARBON_MOLAR_MASS
    )
    assert carbon_out == pytest.approx(carbon_kg, rel=2e-3)


def test_the_mixture_is_the_regulations_f_at_every_age():
    """The generated gas is ~50/50 CH4/CO2 at 8 hours and at 30 years alike."""
    preset = comp.PRESETS["mixed-msw"]
    for age_h in (8.0, 24 * 90, 24 * 365 * 30):
        g = gen.generate(preset, tonnage_t=10.0, age_h=age_h, moisture=0.4)
        assert g.methane_fraction == pytest.approx(0.5, abs=1e-3)
```

Update the existing tests that name `ch4_kg`/`co2_kg` to the new names
(`ch4_cumulative_kg`, `co2_cumulative_kg`): `test_generation_scales_linearly_with_tonnage`,
`test_more_moisture_produces_more_gas_at_the_same_age`, `test_age_orders_generation`,
`test_an_all_inert_load_produces_nothing`, `test_zero_tonnage_is_allowed_and_yields_nothing`.
Replace `test_methane_fraction_matches_the_ap42_steady_state_ratio` with
`test_the_mixture_is_the_regulations_f_at_every_age`; replace
`test_co2_tracks_methane_at_the_cited_ratio` with the carbon-closure test;
`test_a_fresh_load_reports_no_methane_in_its_gas_set` keeps the gas-set
assertion but drops the "pre-methanogenic" note assertion (the note is gone).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_generation.py -q`
Expected: FAIL with `AttributeError: 'Generation' object has no attribute 'ch4_cumulative_kg'` (and `ultimate_carbon_kg` not defined).

- [ ] **Step 3: Implement the new curve**

In `src/scentinel/core/generation.py`:
- Add `CO2_MOLAR_MASS = 44.009` beside `METHANE_MOLAR_MASS`; delete
  `STEADY_STATE_MIX`, `co2_from_ch4`, `nitrogen_from_ch4`.
- Add:

```python
#: CO2/C mass ratio for the carbon that does not leave as methane. The
#: regulation fixes only the CH4 conversion (16/12); CO2 uses molar masses.
CO2_CARBON_RATIO = CO2_MOLAR_MASS / CARBON_MOLAR_MASS


def ultimate_carbon_kg(composition: WasteComposition, tonnage_t: float) -> float:
    """Dissimilated carbon in the batch once every degradable tonne has decayed."""
    return (
        1000.0
        * composition.weighted_doc()
        * DISSIMILATED_DOC_FRACTION
        * tonnage_t
    )


def co2_from_carbon(carbon_kg: float) -> float:
    """CO2 mass from the carbon share the methane fraction leaves behind."""
    if carbon_kg < 0.0:
        raise ValueError("carbon_kg must not be negative")
    return carbon_kg * (1.0 - LANDFILL_GAS_METHANE_FRACTION) * CO2_CARBON_RATIO


def carbon_rate_kg_per_h(
    composition: WasteComposition, tonnage_t: float, *, k_per_year: float, age_h: float
) -> float:
    """Instantaneous degraded-carbon rate: the derivative of the decay curve."""
    if age_h < 0.0:
        raise ValueError("age_h must not be negative")
    return (
        ultimate_carbon_kg(composition, tonnage_t)
        * k_per_year
        / HOURS_PER_YEAR
        * math.exp(-k_per_year * age_h / HOURS_PER_YEAR)
    )
```

- Rewrite `generate()`: delete `producing_methane` and both branches; compute
  `carbon_kg = ultimate_carbon_kg(...) * fraction`,
  `ch4_cumulative_kg = carbon_kg * LANDFILL_GAS_METHANE_FRACTION * STOICHIOMETRIC_RATIO`,
  `co2_cumulative_kg = co2_from_carbon(carbon_kg)`,
  `carbon_rate = carbon_rate_kg_per_h(...)`,
  `ch4_rate_kg_per_h = carbon_rate * LANDFILL_GAS_METHANE_FRACTION * STOICHIOMETRIC_RATIO`,
  `co2_rate_kg_per_h = co2_from_carbon(carbon_rate)`,
  `n2` removed. Validate `age_h >= 0`.
- Update the `Generation` dataclass field list to the interface above; keep
  `phase` (interpretation) but compute every number without consulting it.
- Update the module docstring: mixture basis F = 0.5, continuity, AP-42 55/40/5
  as ceiling/comparison only.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_generation.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/generation.py tests/unit/test_generation.py
git commit -m "fix(generation): separate ultimate, cumulative, and rate; one continuous curve"
```

---

### Task 2 (T-222, T-223): continuity and phase decoupling

**Files:**
- Test: `tests/unit/test_generation.py`

**Interfaces:**
- Consumes: `generate`, `phase_for` as imported in `generation.py`.
- Produces: regression tests that fail if a phase switch is reintroduced.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("boundary_h", [48.0, 24.0 * 90, 24.0 * 365])
def test_generation_is_continuous_across_phase_boundaries(boundary_h):
    """A holding time one hour older must not jump the gas output."""
    preset = comp.PRESETS["mixed-msw"]
    before = gen.generate(preset, tonnage_t=10.0, age_h=boundary_h - 1.0, moisture=0.4)
    after = gen.generate(preset, tonnage_t=10.0, age_h=boundary_h + 1.0, moisture=0.4)
    assert after.ch4_cumulative_kg - before.ch4_cumulative_kg == pytest.approx(
        before.ch4_rate_kg_per_h * 2.0, rel=1e-6
    )
    assert after.ch4_rate_kg_per_h == pytest.approx(before.ch4_rate_kg_per_h, rel=1e-5)


def test_the_phase_label_changes_no_generation_number(monkeypatch):
    """The phase is an interpretation of the curve, never an input to it."""
    preset = comp.PRESETS["mixed-msw"]
    baseline = gen.generate(preset, tonnage_t=10.0, age_h=8.0, moisture=0.4)
    monkeypatch.setattr(gen, "phase_for", lambda age_h: "IV")
    patched = gen.generate(preset, tonnage_t=10.0, age_h=8.0, moisture=0.4)
    assert patched.phase == "IV"
    for field in (
        "ch4_cumulative_kg",
        "co2_cumulative_kg",
        "ch4_rate_kg_per_h",
        "co2_rate_kg_per_h",
        "decay_fraction",
        "methane_fraction",
    ):
        assert getattr(patched, field) == getattr(baseline, field), field
```

- [ ] **Step 2: Run to verify they fail on the old behaviour**

Run: `.venv/bin/pytest tests/unit/test_generation.py -q -k "continuous or phase_label"`
Expected on the old code: FAIL — the boundary test reads a zero-to-nonzero step at 90 days, and the phase-label test changes the gas. (After Task 1 they pass; if they pass before Task 1, the tests are not exercising the switch — fix them.)

- [ ] **Step 3: No implementation needed if Task 1 landed**

If either test fails, the switch survived in `generate()`; remove it.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_generation.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_generation.py
git commit -m "test(generation): guard continuity across phase boundaries"
```

---

### Task 3 (T-223 downstream): the source share follows the same mixture

**Files:**
- Modify: `src/scentinel/core/scenario.py`
- Test: `tests/unit/test_scenario.py`

**Interfaces:**
- Consumes: `Generation.methane_fraction`, `Generation.ch4_cumulative_kg`,
  `Generation.co2_cumulative_kg`.
- Produces: `generated_source_ppmv` returns the F-based CH4 and CO2 shares for
  every age; no phase refusal; `auto_provenance` cites F = 0.5.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_scenario.py`, replace the fresh-load and phase-CO2 tests:

```python
def test_the_generated_source_share_is_the_same_at_every_age():
    """The switch that made a fresh load read 0 ppmv and a 91-day load 550 000 is gone.

    The produced gas is the regulation's F split at every age; what the holding
    time changes is the amount produced, which the rate reports.
    """
    fresh = Scenario(waste_type="mixed-msw", age_h=8.0)
    aged = Scenario(waste_type="mixed-msw", age_h=24.0 * 365 * 30)
    assert auto_concentration_ppmv(fresh, "CH4") == pytest.approx(500_000.0, rel=2e-3)
    assert auto_concentration_ppmv(aged, "CH4") == pytest.approx(500_000.0, rel=2e-3)
    assert auto_concentration_ppmv(fresh, "CO2") == pytest.approx(500_000.0, rel=2e-3)
    assert auto_concentration_ppmv(aged, "CO2") == pytest.approx(500_000.0, rel=2e-3)


def test_the_rate_carries_the_age_difference_the_share_no_longer_does():
    fresh = Scenario(waste_type="mixed-msw", age_h=8.0)
    aged = Scenario(waste_type="mixed-msw", age_h=24.0 * 365 * 3)
    fresh_gen = gen.generate(fresh.composition, tonnage_t=10.0, age_h=fresh.age_h, moisture=0.4)
    aged_gen = gen.generate(aged.composition, tonnage_t=10.0, age_h=aged.age_h, moisture=0.4)
    assert aged_gen.ch4_cumulative_kg > fresh_gen.ch4_cumulative_kg * 1000
    assert fresh_gen.ch4_rate_kg_per_h > aged_gen.ch4_rate_kg_per_h
```

Delete `test_a_phase_one_carbon_dioxide_source_is_refused_rather_than_fabricated`;
update `test_an_aged_load_reaches_the_cited_steady_state_methane` (rename to
`..._the_regulation_default_mixture`) to 500 000 and
`test_resolve_sources_carries_the_generated_value_as_a_volume_fraction` to 0.5,
and `test_moisture_changes_the_generation_mass_not_the_steady_state_share` to
the new field names and 500 000.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_scenario.py -q`
Expected: FAIL — fresh CH4 reads 0.0 and fresh CO2 raises.

- [ ] **Step 3: Implement**

In `scenario.py`:
- `generated_source_ppmv`: remove the phase-I/II refusal; compute the CO2 share
  from the cumulative masses (`moles_co2 / (moles_ch4 + moles_co2)`) at the
  scenario's age; keep the CH4 share from `methane_fraction`. Update the
  docstring to state the F basis and that age moves the rate, not the share.
- `auto_provenance`: replace the AP-42 tail with
  `"40 CFR 98.343 Table HH-1 F=0.5 splits the degraded carbon between CH4 and CO2"`.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_scenario.py tests/unit/test_casegen.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/scenario.py tests/unit/test_scenario.py
git commit -m "fix(scenario): source share follows the F=0.5 mixture at every age"
```

---

### Task 4 (T-221): the UI reports cumulative and rate, never "now"

**Files:**
- Modify: `src/scentinel/ui/batch_panel.py`,
  `src/scentinel/resources/locales/en.json`,
  `src/scentinel/resources/locales/id.json`,
  `src/scentinel/core/pipeline.py`
- Test: `tests/ui/test_batch_panel.py`, `tests/unit/test_pipeline.py`

**Interfaces:**
- Consumes: the new `Generation` fields.
- Produces: readout keys `gas_cumulative` and `gas_rate`; locale keys
  `batch.readout.gas_cumulative`, `batch.readout.gas_rate`; pipeline summary
  lines with units.

- [ ] **Step 1: Write the failing tests**

In `tests/ui/test_batch_panel.py`, replace the `gas_now` test:

```python
def test_the_gas_readout_separates_cumulative_mass_from_rate(panel):
    """Cumulative kg and kg/h are different quantities; one label cannot serve both."""
    panel._age_h.setValue(24.0 * 365 * 5)
    cumulative = _text(panel, "gas_cumulative")
    rate = _text(panel, "gas_rate")
    assert "kg" in cumulative and "kg/h" not in cumulative
    assert "kg/h" in rate
    assert cumulative != rate


def test_holding_time_moves_both_readouts_without_a_jump(panel):
    panel._age_h.setValue(24.0 * 89)
    before = (_text(panel, "gas_cumulative"), _text(panel, "gas_rate"))
    panel._age_h.setValue(24.0 * 91)
    after = (_text(panel, "gas_cumulative"), _text(panel, "gas_rate"))
    assert before != after
    assert "kg/h" in after[1]
```

In `tests/unit/test_pipeline.py`, update the summary assertions to the new
field names and add:

```python
def test_the_summary_states_cumulative_and_rate_with_units():
    result = pipeline.assess_batch(
        comp.PRESETS["mixed-msw"], tonnage_t=10.0, moisture=0.40, age_h=24 * 365
    )
    joined = "\n".join(result.summary_lines())
    assert "cumulative" in joined
    assert "kg/h" in joined
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/ui/test_batch_panel.py tests/unit/test_pipeline.py -q`
Expected: FAIL — `KeyError: 'gas_cumulative'`.

- [ ] **Step 3: Implement**

- `batch_panel.py`: replace `"gas_now"` in the readout keys with
  `"gas_cumulative"` and `"gas_rate"`; render:
  `f"CH4 {gen.ch4_cumulative_kg:.3f} kg · CO2 {gen.co2_cumulative_kg:.3f} kg"` and
  `f"CH4 {gen.ch4_rate_kg_per_h:.4f} kg/h · CO2 {gen.co2_rate_kg_per_h:.4f} kg/h"`.
- Locales: remove `batch.readout.gas_now`; add
  `"batch.readout.gas_cumulative": "Gas generated so far (cumulative)"` /
  `"Gas yang sudah terbentuk (kumulatif)"` and
  `"batch.readout.gas_rate": "Generation rate"` / `"Laju pembentukan gas"`.
- `pipeline.py`: summary lines use the new names and print both quantities.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/pytest tests/ui/test_batch_panel.py tests/unit/test_pipeline.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/ui/batch_panel.py src/scentinel/resources/locales/en.json \
  src/scentinel/resources/locales/id.json src/scentinel/core/pipeline.py \
  tests/ui/test_batch_panel.py tests/unit/test_pipeline.py
git commit -m "fix(ui): report cumulative gas and generation rate as separate quantities"
```

---

### Task 5 (T-224): manifest v5 records all three quantities

**Files:**
- Modify: `src/scentinel/core/history.py`
- Test: `tests/unit/test_history.py`

**Interfaces:**
- Consumes: `Generation.ultimate_ch4_kg_per_t`, `ultimate_ch4_kg`,
  `ch4_cumulative_kg`, `co2_cumulative_kg`, `ch4_rate_kg_per_h`,
  `co2_rate_kg_per_h`, `methane_fraction`.
- Produces: `RUN_FORMAT_VERSION = 5`; `GenerationRecord` with those fields;
  v4 manifests rejected naming both versions.

- [ ] **Step 1: Write the failing tests**

Update `tests/unit/test_history.py`:
- `test_begin_run_...` payload assertion `format_version == 4` → `5`.
- `test_the_manifest_records_the_composition_and_its_derived_chemistry`:
  `methane_fraction == 0.55` → `pytest.approx(0.5, abs=2e-3)`; add
  `chemistry["ch4_cumulative_kg"]`, `chemistry["ch4_rate_kg_per_h"]` present.
- `test_a_version_3_manifest_is_rejected_naming_both_versions` → v4 rejected
  naming 4 and 5.
- `test_a_generated_source_cites_the_model_that_produced_it`: 550 000 → 500 000
  (`rel=2e-3`); provenance contains "F=0.5" and the resolved value, not "550000".

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_history.py -q`
Expected: FAIL — format version 4, missing rate keys.

- [ ] **Step 3: Implement**

- `RUN_FORMAT_VERSION = 5`.
- `GenerationRecord` fields: `phase`, `doc`, `k_per_year`, `decay_fraction`,
  `methane_fraction`, `ultimate_ch4_kg_per_t`, `ultimate_ch4_kg`,
  `ch4_cumulative_kg`, `co2_cumulative_kg`, `ch4_rate_kg_per_h`,
  `co2_rate_kg_per_h`.
- `_GENERATION_KEYS` matching; `_snapshot_project` and every encode site
  (`rg -n "ch4_kg|co2_kg" src/`) updated; `_decode_generation` updated with
  `minimum=0.0` on every mass and rate.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_history.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/history.py tests/unit/test_history.py
git commit -m "feat(history): manifest v5 records ultimate, cumulative, and rate"
```

---

### Task 6: docs and status records

**Files:**
- Modify: `docs/gas-composition-basis.md`, `docs/ARCHITECTURE.md`,
  `docs/TASKS.md`, `docs/ROADMAP.md`, `README.md`, `CHANGELOG.md`

- [ ] **Step 1: Update the basis document**

State the F = 0.5 choice (40 CFR 98.343 Table HH-1), that CO2 follows the
carbon balance, that N2 is not a decay product, and that the AP-42 55/40/5 mix
is retained as a measured mature-landfill ceiling/comparison. Label the choice
`cited` (regulation default) and the CO2/C molar ratio `derived`.

- [ ] **Step 2: Update the module map and status records**

`ARCHITECTURE.md`: generation module paragraph. `TASKS.md`: T-220…T-224 DONE
with the corrected manifest-version note. `ROADMAP.md`: current-position text
no longer says a fresh load reports no methane; the sequencing note records
that gas work ran before Phase 1 and the manifest versions swapped.
`CHANGELOG.md`: `[Unreleased]` entries. `README.md`: any "fresh load has no
methane" or "55%" claim corrected (`rg -n "55%|no methane|550" README.md`).

- [ ] **Step 3: Run the full suite and lint**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check src tests scripts`
Expected: all pass; no new ruff findings.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "docs: record the F=0.5 generation basis and Phase 2 status"
```

---

## Self-review

- **Spec coverage:** T-220 (Task 1), T-221 (Task 4), T-222 (Task 2), T-223
  (Tasks 1–3), T-224 (Task 5), docs (Task 6). Phase exit gate — continuity at
  every boundary, no UI string calling cumulative a rate — is Tasks 2 and 4.
- **No placeholders:** every step names files, code, and the expected failure.
- **Type consistency:** `ch4_cumulative_kg`, `ch4_rate_kg_per_h`,
  `co2_cumulative_kg`, `co2_rate_kg_per_h`, `ultimate_ch4_kg`,
  `ultimate_ch4_kg_per_t` are used with the same names in Tasks 1, 3, 4, 5.
- **Known intermediate state:** until T-020 (Phase 5) the CFD source is still a
  concentration, so the CH4 surface value no longer depends on age; the age now
  lives in the rate. This is stated in the plan, the module docstring, and the
  CHANGELOG, and is the reason Phase 5 exists.
