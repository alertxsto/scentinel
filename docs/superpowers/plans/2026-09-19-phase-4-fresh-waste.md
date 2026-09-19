# Phase 4 — Fresh-Waste Model: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Give phase I (fresh waste) its own cited gas basis and applicability,
instead of offering landfill trace defaults as if they were equivalent, and make
the offered gas set a function of holding time.

**Architecture:** A research artifact records what could and could not be
extracted, with retrieval metadata and an explicit `unavailable` reason where a
source is paywalled. A curated applicability layer in `gas_data.py` states, per
gas, which phases it applies to, its source, and its uncertainty. The setup
panel offers a gas only when the current age's phase allows it.

**Tech Stack:** Python 3.12+ (CI), pytest, PySide6.

**Spec:** `docs/superpowers/plans/2026-09-19-hardening-program.md` (Phase 4,
T-106/T-107). Manifest: this phase changes no persisted schema (the gas set is
derived from `age_h`, which is already recorded).

## Global Constraints

1. A value without a citation does not enter the model; where no cited value
   exists the output states the gap. A paywalled source is recorded
   `unavailable` with the reason — never filled with a guess.
2. Provenance labels: `cited`, `derived`, `model assumption`, `user input`,
   `laboratory`, `unavailable`.
3. TDD: failing test → run → minimal implementation → green → commit.
4. Suite baseline after Phase 3: `580 passed`; ruff 67, no new findings.
5. i18n: en/id keys for every user-visible string.

---

### Task 1 (T-106): fresh-waste research artifact

**Files:** `docs/data/fresh_waste_references.json` (new),
`docs/references.md`, `tests/unit/test_fresh_waste_data.py` (new)

**Interfaces:**
- Produces: a JSON artifact `{source, canonical_url, retrieved_utc,
  artifact_sha256, status, values|reason}` per source.

- [ ] **Step 1: Write the failing test**

```python
def test_the_artifact_records_extraction_status_for_every_source():
    data = json.loads(FRESH.read_text())
    assert set(data) == {"statheropoulos_2005", "waste_management_2017", "niosh_3900"}
    for name, entry in data.items():
        assert entry["status"] in ("extracted", "unavailable")
        if entry["status"] == "extracted":
            assert entry["values"] and entry["canonical_url"]
        else:
            assert entry["reason"]


def test_extracted_values_carry_a_unit_and_a_reference():
    entry = json.loads(FRESH.read_text())["statheropoulos_2005"]
    for value in entry["values"]:
        assert value["unit"]
        assert value["reference"]
        assert value["median_ug_per_m3"] > 0
```

- [ ] **Step 2: Run to verify they fail** — file missing.

- [ ] **Step 3: Create the artifact.** Statheropoulos 2005 (extracted, medians
  in µg/m³); Waste Management 2017 and NIOSH 3900 (unavailable, with the HTTP
  reason). Record `retrieved_utc` and a SHA-256 of the artifact.

- [ ] **Step 4: Run to verify they pass.**

- [ ] **Step 5: Commit.**

---

### Task 2 (T-107a): per-gas applicability metadata

**Files:** `src/scentinel/core/gas_data.py`, `tests/unit/test_gas_data.py`

**Interfaces:**
- Produces: `GasApplicability(phases, source, uncertainty)` and
  `applicability(gas_key) -> GasApplicability`; `offered_gases(age_h)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_every_offered_gas_has_an_applicability():
    for key in data.available_gases():
        app = data.applicability(key)
        assert app.phases
        assert app.source
        assert app.uncertainty


def test_methane_is_not_offered_for_a_fresh_load():
    assert "CH4" not in data.offered_gases(8.0)
    assert "CH4" in data.offered_gases(24.0 * 365 * 5)


def test_phase_one_offers_only_phase_one_gases():
    offered = data.offered_gases(8.0)
    assert "CO2" in offered
    assert all("I" in data.applicability(g).phases for g in offered)
```

- [ ] **Step 2: Run to verify they fail.**

- [ ] **Step 3: Implement** the mapping (headline + trace gases → phases),
  citing each phase-I gas's source and its uncertainty. `offered_gases` unions
  the phase's gases.

- [ ] **Step 4: Run to verify they pass.**

- [ ] **Step 5: Commit.**

---

### Task 3 (T-107b): the setup panel gates the list by age

**Files:** `src/scentinel/ui/setup_panel.py`,
`tests/ui/test_setup_panel.py`

- [ ] **Step 1: Write the failing test**

```python
def test_a_fresh_holding_time_removes_methane_from_the_gas_list(panel):
    panel._age_h.setValue(8.0)
    assert "CH4" not in panel.offered_gas_keys()
    panel._age_h.setValue(24.0 * 365 * 5)
    assert "CH4" in panel.offered_gas_keys()
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement** `offered_gas_keys()` on the panel and rebuild the
  gas checkboxes when `age_h` changes; a gas not offered is absent, not merely
  disabled.

- [ ] **Step 4: Run to verify it passes.**

- [ ] **Step 5: Commit.**

---

### Task 4: docs and status

- [ ] **Step 1:** `references.md` and `gas-composition-basis.md` record the
  extracted Statheropoulos values and the two `unavailable` sources with reasons.
- [ ] **Step 2:** Mark T-106/T-107 in `TASKS.md` (T-106 partly: extraction done
  where accessible, rest recorded unavailable); update ROADMAP/CHANGELOG.
- [ ] **Step 3:** Full suite + lint.
- [ ] **Step 4:** Commit.

## Self-review

- **Spec coverage:** T-106 (Task 1), T-107 (Tasks 2–3). Exit gate — a fresh bin
  reports only gases whose phase-I basis exists, each labelled.
- **Type consistency:** `applicability`, `offered_gases`, `GasApplicability`,
  `offered_gas_keys` used consistently across tasks.
- **Known limit:** the primary source (Waste Manag. 2017) is paywalled; the
  artifact records that rather than estimating its values.
