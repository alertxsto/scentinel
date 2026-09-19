# Phase 5 — CFD Mass-Flux Source: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Replace the `fixedValue` surface-concentration source with an emission
mass flux (kg/m²/s) driven by the batch's generation rate, so tonnage and age
actually move the CFD and the near-wall flux no longer scales with the first
cell height.

**Architecture:** The chain is `batch → emission rate kg/s → emitting area m² →
kg/m²/s → scalar boundary gradient`. The scalar field keeps its existing display
units (ppmv-equivalent), so sampling, the manifest, and the UI are unchanged;
only the *boundary condition type* changes from a value to a gradient, which is
what removes the mesh dependence. The flux is derived from the generation
model's rate, not from the 55% mole fraction.

**Tech Stack:** Python 3.12+ (CI), pytest, OpenFOAM in Podman.

**Spec:** `docs/superpowers/plans/2026-09-19-hardening-program.md` (Phase 5,
T-020). This phase bumps project format v1 → v2 (adds `width_m`) and manifest
v6 → v7.

## Global Constraints

1. A value without a citation does not enter the model; a gap is stated.
2. Provenance labels: `cited`, `derived`, `model assumption`, `user input`,
   `laboratory`, `unavailable`.
3. TDD: failing test → run → minimal implementation → green → commit.
4. Baseline: `591 passed`; ruff 67, no new findings.
5. Persisted-schema change bumps the version and rejects/migrates the old.
6. i18n: en/id keys for every user-visible string.
7. Container gates: `pytest -m verification` (podman + image available).

## Model decisions (recorded, not inferred)

- **`width_m` is a new geometry input** (default 2.4 m, a collection-truck bin
  width). The case is a 2D cross-section; the emitting area is the mound profile
  length times `width_m`. Without it the rate cannot become a per-area flux.
- **Total gas rate = CH4 rate + CO2 rate** from the generation model. Each
  gas's emission rate is `total_rate × mixture_fraction`, where a generated
  gas's fraction is its F-based share and a trace gas's is its cited ppmv × 1e-6.
  A fresh load therefore emits little of *every* gas, which is the physics.
- **Field units are unchanged (ppmv-equivalent).** The transport equation is
  linear, so imposing the flux in concentration units is equivalent to imposing
  it in mass units; the conversion is `J_C = J_mass × (Vm/MW) × 1e6` at 25 °C,
  1 atm. This keeps sampling, manifest, and UI untouched.
- **Boundary type: `fixedGradient`** with `gradient = J_C / D`. The flux is
  imposed directly, independent of the first cell height — the actual fix.

---

### Task 1 (T-020a): geometry width and emitting area

**Files:** `src/scentinel/core/geometry.py`, `src/scentinel/core/project.py`,
`tests/unit/test_geometry.py`, `tests/unit/test_project.py`

**Interfaces:**
- Produces: `BinGeometry.width_m: float = 2.4`;
  `emission_area_m2(geom) -> float` = mound profile length × `width_m`;
  `FORMAT_VERSION = 2` with a v1 migration that defaults `width_m`.

- [ ] **Step 1: failing tests**

```python
def test_emission_area_is_the_profile_length_times_the_width():
    geom = BinGeometry(length_m=6.0, height_m=2.5, mound_shape="flat",
                       mound_fill_fraction=0.5, width_m=2.0)
    # flat mound: profile is a single 6 m segment, times 2 m width
    assert emission_area_m2(geom) == pytest.approx(12.0)


def test_width_defaults_and_must_be_positive():
    assert BinGeometry().width_m == pytest.approx(2.4)
    with pytest.raises(ValueError, match="width_m"):
        BinGeometry(width_m=0.0)


def test_a_version_1_project_loads_with_a_default_width(tmp_path):
    ...  # write a v1 payload without width_m, load, assert width_m == 2.4
```

- [ ] **Step 2: run → fail.**
- [ ] **Step 3: implement** `width_m`, `emission_area_m2`, and the v1→v2
  migration.
- [ ] **Step 4: run → pass.**
- [ ] **Step 5: commit.**

---

### Task 2 (T-020b): emission rate and flux

**Files:** `src/scentinel/core/casegen.py`, `tests/unit/test_casegen.py`

**Interfaces:**
- Produces: `emission_rate_kg_per_s(scenario, gas) -> float`;
  `emission_flux_kg_per_m2_s(scenario, geom, gas) -> float`;
  `source_gradient_ppmv_per_m(scenario, geom, gas) -> float`.
- Consumes: `gen.generate(...)`, `geometry.emission_area_m2`,
  `gas_data.get_gas(...).mw_g_mol`, `scalar_diffusivity(gas)`.

- [ ] **Step 1: failing tests**

```python
def test_the_flux_is_the_rate_over_the_emitting_area():
    s = Scenario(gas_sources={"CH4": "auto"}, tonnage_t=10.0, age_h=24*365*3)
    g = BinGeometry(width_m=2.0)
    rate = casegen.emission_rate_kg_per_s(s, "CH4")
    flux = casegen.emission_flux_kg_per_m2_s(s, g, "CH4")
    assert flux == pytest.approx(rate / geometry.emission_area_m2(g))


def test_tonnage_and_age_change_the_flux():
    g = BinGeometry()
    light = Scenario(gas_sources={"CH4": "auto"}, tonnage_t=1.0, age_h=24*365*3)
    heavy = Scenario(gas_sources={"CH4": "auto"}, tonnage_t=10.0, age_h=24*365*3)
    assert (casegen.emission_flux_kg_per_m2_s(heavy, g, "CH4")
            > 10.0 * casegen.emission_flux_kg_per_m2_s(light, g, "CH4") * 0.9)
    fresh = Scenario(gas_sources={"CH4": "auto"}, tonnage_t=10.0, age_h=8.0)
    aged = Scenario(gas_sources={"CH4": "auto"}, tonnage_t=10.0, age_h=24*365*3)
    assert casegen.emission_flux_kg_per_m2_s(aged, g, "CH4") > \
           casegen.emission_flux_kg_per_m2_s(fresh, g, "CH4")
```

- [ ] **Step 2: run → fail.**
- [ ] **Step 3: implement** the rate (generated gases from HH-1; trace gases from
  the total rate times their cited fraction), the flux, and the gradient
  (`J_C = J_mass × Vm/MW × 1e6`; gradient = `J_C / D`).
- [ ] **Step 4: run → pass.**
- [ ] **Step 5: commit.**

---

### Task 3 (T-020c): the case writes a gradient source

**Files:** `src/scentinel/core/casegen.py`, `tests/unit/test_casegen.py`

**Interfaces:**
- Produces: `write_case` uses `fixedGradient` on the source patch; `case.json`
  and `applied_physics` record `emission_flux_kg_per_m2_s` per gas and
  `emitting_area_m2`.

- [ ] **Step 1: failing tests**

```python
def test_the_source_patch_imposes_a_gradient_not_a_value(tmp_path, mesh):
    case = write_case(Scenario(gas_sources={"CO": "auto"}, tonnage_t=10.0),
                      mesh, tmp_path / "case", geom=BinGeometry())
    field = (case / "0" / "CO").read_text()
    source_block = field.split("source")[1]
    assert "fixedGradient" in source_block
    assert "gradient" in source_block
    assert "fixedValue" not in source_block


def test_applied_physics_records_the_flux_and_area(tmp_path, mesh):
    case = write_case(Scenario(gas_sources={"CO": "auto"}), mesh,
                      tmp_path / "case", geom=BinGeometry())
    applied = casegen.applied_physics(Scenario(gas_sources={"CO": "auto"}), BinGeometry())
    assert applied["emitting_area_m2"] > 0
    assert applied["emission_flux_kg_per_m2_s"]["CO"] > 0
```

- [ ] **Step 2: run → fail.**
- [ ] **Step 3: implement** `_field_scalar` with a gradient, thread `geom` into
  the field writer, and extend `applied_physics`/`case.json`.
- [ ] **Step 4: run → pass.**
- [ ] **Step 5: commit.**

---

### Task 4 (T-020d): manifest v7 and UI exposure

**Files:** `src/scentinel/core/history.py`, `src/scentinel/ui/setup_panel.py`,
`resources/locales/{en,id}.json`, tests.

- [ ] **Step 1:** failing tests for v7 (reject v6 naming both) and the flux row.
- [ ] **Step 2:** run → fail.
- [ ] **Step 3:** bump `RUN_FORMAT_VERSION` to 7; record the applied flux and
  emitting area; show the source strength in the setup panel with its citation.
- [ ] **Step 4:** run → pass.
- [ ] **Step 5:** commit.

---

### Task 5 (T-020e): flip the verification gate

**Files:** `tests/verification/test_mesh_independence.py`

- [ ] **Step 1:** rewrite the test to assert <10% deviation and a monotone
  trend (the old test asserted failure).
- [ ] **Step 2:** run `pytest -m verification -q`.
- [ ] **Step 3:** if it fails, the flux conversion or the boundary is wrong;
  debug with the systematic-debugging skill, not by loosening the gate.
- [ ] **Step 4:** commit.

---

### Task 6: docs and status

`gas-composition-basis.md`, `ARCHITECTURE.md`, `TASKS.md`, `ROADMAP.md`,
`README.md`, `CHANGELOG.md`: record the flux basis, the width input, and the
project v2 / manifest v7 bumps.

## Self-review

- **Spec coverage:** T-020a–e map to the task's deliverables (mass-flux source,
  UI exposure, verification gate). Exit gate is Task 5.
- **Type consistency:** `width_m`, `emission_area_m2`,
  `emission_rate_kg_per_s`, `emission_flux_kg_per_m2_s`,
  `source_gradient_ppmv_per_m`, `emitting_area_m2` are used consistently.
- **Risk:** the trace-gas share model (Task 2) is a stated choice; if the gate
  fails it is the first suspect, and the fallback is to state the gap rather
  than tune a number.
