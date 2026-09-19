# Phase 3 — Phase Model: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the 48 h / 90 d / 365 d decomposition cutoffs an explicit, labelled
model assumption; separate the decomposition *stage* (interpretation) from the
continuous decay math; and carry each phase's source, applicability, and
uncertainty through to the UI and the manifest.

**Architecture:** A frozen `PhaseModel` value object holds the boundaries, their
provenance (`model assumption`), the basis text (AP-42 §2.4.4 narrative), and an
uncertainty note. `phase_for()` and `interpret_phase()` take the model as a
parameter. The generation math already ignores the phase (Phase 2); this phase
makes that explicit and adds an applicability statement — in particular that the
HH-1 first-order model is an *anaerobic landfill* model applied to the aerobic
phase I as an extrapolation.

**Tech Stack:** Python 3.12+ (CI), pytest, PySide6.

**Spec:** `docs/superpowers/plans/2026-09-19-hardening-program.md` (Phase 3,
T-230…T-232). Manifest numbering: Phase 2 landed v5; this phase adds the phase
interpretation and bumps v5 → v6.

## Global Constraints

1. A value without a citation does not enter the model; where no cited value
   exists the output states the gap.
2. Provenance labels: `cited`, `derived`, `model assumption`, `user input`,
   `laboratory`, `unavailable`.
3. TDD: failing test → run → minimal implementation → green → commit.
4. Suite baseline after Phase 2: `573 passed`; ruff 67, no new findings.
5. Persisted-schema change bumps `RUN_FORMAT_VERSION` and rejects the old
   version naming both.
6. i18n: en/id keys for every user-visible string.

---

### Task 1 (T-230): the phase model is an explicit assumption

**Files:** `src/scentinel/core/composition.py`, `tests/unit/test_composition.py`

**Interfaces:**
- Produces: `PhaseModel(boundaries_h, provenance, basis, uncertainty)`,
  `DEFAULT_PHASE_MODEL`, `phase_for(age_h, model=DEFAULT_PHASE_MODEL)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_phase_model_is_a_labelled_assumption():
    m = comp.DEFAULT_PHASE_MODEL
    assert m.boundaries_h == (48.0, 24.0 * 90.0, 24.0 * 365.0)
    assert m.provenance == "model assumption"
    assert m.basis  # names the AP-42 narrative
    assert m.uncertainty


def test_a_custom_phase_model_moves_the_boundaries():
    fast = comp.PhaseModel(
        boundaries_h=(1.0, 2.0, 3.0),
        provenance="user input",
        basis="test",
        uncertainty="test",
    )
    assert comp.phase_for(1.5, model=fast) == "II"
    assert comp.phase_for(1.5) == "I"
```

- [ ] **Step 2: Run to verify they fail** — `AttributeError: PhaseModel`.

- [ ] **Step 3: Implement** the dataclass and thread `model` through
  `phase_for`; replace the three module constants with
  `DEFAULT_PHASE_MODEL.boundaries_h`.

- [ ] **Step 4: Run to verify they pass.**

- [ ] **Step 5: Commit.**

---

### Task 2 (T-231): stage separated from decay

**Files:** `src/scentinel/core/composition.py`, `src/scentinel/core/generation.py`,
`tests/unit/test_generation.py`

**Interfaces:**
- Produces: `interpret_phase(age_h, model=DEFAULT_PHASE_MODEL) -> PhaseInterpretation`;
  `Generation.phase_interpretation`.

- [ ] **Step 1: Write the failing tests**

```python
def test_interpretation_carries_source_applicability_and_uncertainty():
    interp = comp.interpret_phase(8.0)
    assert interp.phase == "I"
    assert interp.source
    assert interp.provenance == "model assumption"
    assert interp.applicability
    assert interp.uncertainty


def test_phase_one_states_the_landfill_model_does_not_strictly_apply():
    """HH-1 is an anaerobic landfill model; phase I is aerobic."""
    interp = comp.interpret_phase(8.0)
    assert "aerobic" in interp.applicability.lower()
    mature = comp.interpret_phase(24.0 * 365 * 5)
    assert "aerobic" not in mature.applicability.lower()
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement** `PhaseInterpretation` and `interpret_phase`;
  add `phase_interpretation` to `Generation`, populated in `generate()`; the
  numbers still never read it.

- [ ] **Step 4: Run to verify they pass.**

- [ ] **Step 5: Commit.**

---

### Task 3 (T-232): the interpretation reaches the UI and the manifest

**Files:** `src/scentinel/core/history.py`, `src/scentinel/ui/batch_panel.py`,
`resources/locales/{en,id}.json`, `tests/unit/test_history.py`,
`tests/ui/test_batch_panel.py`

**Interfaces:**
- Produces: `RUN_FORMAT_VERSION = 6`; generation block gains `phase_source`,
  `phase_applicability`, `phase_uncertainty`; batch panel phase readout appends
  the applicability.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_version_5_manifest_is_rejected_naming_both_versions(tmp_path):
    record = _begin(tmp_path)
    _rewrite(record, lambda p: p.__setitem__("format_version", 5))
    with pytest.raises(HistoryError, match="5"):
        history.load_run(record.run_dir)


def test_the_manifest_records_the_phase_interpretation(tmp_path):
    record = _begin(tmp_path)
    chemistry = _manifest(record)["project"]["scenario"]["generation"]
    assert chemistry["phase_provenance"] == "model assumption"
    assert chemistry["phase_applicability"]
    assert chemistry["phase_uncertainty"]
```

```python
def test_the_phase_readout_states_the_model_basis(panel):
    panel._age_h.setValue(8.0)
    assert "aerobic" in _text(panel, "phase").lower()
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement**: bump `RUN_FORMAT_VERSION`, extend
  `GenerationRecord`, `_GENERATION_KEYS`, `_snapshot_project`, the encoder, and
  `_decode_generation`; render the applicability in the panel.

- [ ] **Step 4: Run to verify they pass.**

- [ ] **Step 5: Commit.**

---

### Task 4: docs and status

**Files:** `docs/gas-composition-basis.md`, `docs/ARCHITECTURE.md`,
`docs/TASKS.md`, `docs/ROADMAP.md`, `README.md`, `CHANGELOG.md`

- [ ] **Step 1:** Label the boundaries `model assumption` in the basis doc;
  document the applicability gap (HH-1 is anaerobic, phase I is aerobic).
- [ ] **Step 2:** Mark T-230…T-232 DONE; update the module map, current-position
  text, README, and CHANGELOG; manifest v6.
- [ ] **Step 3:** Run the full suite and lint.
- [ ] **Step 4:** Commit.

## Self-review

- **Spec coverage:** T-230 (Task 1), T-231 (Task 2), T-232 (Task 3). Exit gate —
  the phase label changes no number (Phase 2 test, re-asserted) and every
  boundary has a provenance label.
- **Type consistency:** `PhaseModel`, `PhaseInterpretation`, `interpret_phase`,
  `phase_interpretation`, `phase_provenance`, `phase_applicability`,
  `phase_uncertainty` are used with the same names across tasks.
