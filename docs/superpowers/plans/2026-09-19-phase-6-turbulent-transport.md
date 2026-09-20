# Phase 6 — Turbulent Scalar Transport: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Carry the passive scalars with an effective diffusivity
`D_eff = D_molecular + ν_t/Sc_t` instead of molecular `D` alone, with `Sc_t` a
named, cited constant, so dispersion reflects the turbulent flow the momentum
solver already computes.

**Architecture:** `scalarTransport` supports this natively: when its `D` entry
is absent it uses `alphaD*nu + alphaDt*nut`, where `Sc_t = 1/alphaDt`
(verified against OpenFOAM v2512 `scalarTransport.C`). The case writer stops
emitting `D` and emits `alphaD`/`alphaDt` instead; `applied_physics` records
`Sc_t` and the per-gas molecular `D` that still enters the balance.

**Tech Stack:** Python 3.12+ (CI), pytest, OpenFOAM v2512 in Podman.

**Spec:** `docs/superpowers/plans/2026-09-19-hardening-program.md` (Phase 6,
T-240). Manifest v7 → v8 (records `turbulent_schmidt_number` and the
`alphaDt` actually written).

## Global Constraints

1. A value without a citation does not enter the model; a gap is stated.
2. Provenance labels: `cited`, `derived`, `model assumption`, `user input`,
   `laboratory`, `unavailable`.
3. TDD: failing test → run → minimal implementation → green → commit.
4. Baseline: `607 passed`; ruff 67, no new findings.
5. Persisted-schema change bumps the version and rejects the old naming both.
6. i18n: en/id keys for any user-visible string.
7. Container gates: `pytest -m verification`.

## Model decision (recorded)

`Sc_t = 0.7` (turbulent Schmidt number), a **model assumption** with the
standard RANS range 0.7–0.9 as its basis. The code carries it as a named
constant with that provenance; it is not measured for this geometry, and the
uncertainty is stated. The gate test is the check on whether it is adequate.

---

### Task 1 (T-240a): the case carries turbulent diffusivity

**Files:** `src/scentinel/core/casegen.py`, `tests/unit/test_casegen.py`

**Interfaces:**
- Produces: `TURBULENT_SCHMIDT_NUMBER = 0.7`,
  `TURBULENT_SCHMIDT_PROVENANCE`, `ALPHA_D = 1.0`;
  `_functions()` writes `alphaD`/`alphaDt` and no `D`.

- [ ] **Step 1: failing tests**

```python
def test_the_scalar_carries_turbulent_diffusivity(tmp_path, mesh):
    case = write_case(Scenario(gas_sources={"CO": "auto"}), mesh,
                      tmp_path / "case", geom=BinGeometry())
    functions = (case / "system" / "functions").read_text()
    block = functions.split("COTransport\n")[1]
    assert "alphaDt" in block
    assert "nut" in block
    # The molecular-only path is gone: with D present OpenFOAM ignores nut.
    assert "\n    D " not in block


def test_the_schmidt_number_is_a_labelled_assumption():
    assert 0.5 <= casegen.TURBULENT_SCHMIDT_NUMBER <= 1.0
    assert casegen.TURBULENT_SCHMIDT_PROVENANCE == "model assumption"
```

- [ ] **Step 2: run → fail.**
- [ ] **Step 3: implement** the constant and the `_functions` body:
  `diffusivity` entry removed; `alphaD 1; alphaDt <1/Sc_t>; nut nut;`.
- [ ] **Step 4: run → pass.**
- [ ] **Step 5: commit.**

---

### Task 2 (T-240b): the manifest records Sc_t

**Files:** `src/scentinel/core/history.py`, `tests/unit/test_history.py`

- [ ] **Step 1:** failing test for v8 (reject v7 naming both) and
  `applied["turbulent_schmidt_number"] == 0.7`.
- [ ] **Step 2:** run → fail.
- [ ] **Step 3:** `RUN_FORMAT_VERSION = 8`; extend `AppliedPhysicsRecord`,
  `_APPLIED_PHYSICS_KEYS`, `applied_physics()`, encode/decode.
- [ ] **Step 4:** run → pass.
- [ ] **Step 5:** commit.

---

### Task 3 (T-240c): benchmark and sensitivity

**Files:** `tests/verification/test_analytical_benchmarks.py`

- [ ] **Step 1:** add a test that the 1D duct benchmark still matches the closed
  form when the turbulent path is active (the duct has uniform `nut`, so the
  effective D is still a constant and the exponential solution holds).
- [ ] **Step 2:** run `pytest -m verification -q`.
- [ ] **Step 3:** if it fails, the `alphaD`/`alphaDt` wiring is wrong.
- [ ] **Step 4:** commit.

---

### Task 4 (T-240d): re-measure the mesh-independence gate

**Files:** `tests/verification/test_mesh_independence.py`, docs.

- [ ] **Step 1:** measure the deviation with turbulent transport on.
- [ ] **Step 2:** if <10% and monotone, flip the gate to assert convergence.
  If not, record the new numbers and the remaining cause honestly (do not
  loosen the gate).
- [ ] **Step 3:** update ROADMAP/ARCHITECTURE/README/CHANGELOG/TASKS.
- [ ] **Step 4:** commit.

## Self-review

- **Spec coverage:** T-240a–d map to the task's deliverables (turbulent term,
  Sc_t recorded, benchmark, gate).
- **Type consistency:** `TURBULENT_SCHMIDT_NUMBER`, `alphaDt`,
  `turbulent_schmidt_number` used consistently.
- **Risk:** Sc_t = 0.7 is a model assumption; if the gate still fails, the
  fallback is to report it and point at the velocity field (T-021), not to tune
  Sc_t to pass.
