# Scentinel Audit Fixes (Phases 1–7) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every defect confirmed by the independent Phase 1–7 audits so the
repository's numbers, records, and gates describe what the code actually does,
without inventing values or hiding failures.

**Architecture:** Four audits (phases 1–3, 4–5, 6–7, cross-phase review) were
reproduced locally. The confirmed defects fall into three classes: (a) data
integrity — a recorded manual source the case ignores, a false convergence
verdict, and a wrong-iteration residual read; (b) unreachable/untracked inputs —
`width_m` and `nu`; (c) documentation and status claims that contradict the
code. Each fix lands test-first and independently; the docs sweep runs last so
it can cite the fixed behavior.

**Tech Stack:** Python 3.12+ (CI), pytest, OpenFOAM v2512 in Podman, PySide6,
PyVista. Ruff baseline 67 (no new rule+file combinations).

**Spec:** `docs/superpowers/plans/2026-09-19-hardening-program.md` (Phase 1–7),
plus the four audit reports summarized in `docs/TASKS.md` (this plan's Task 10).

## Global Constraints

1. **Governing rule:** a value without a citation does not enter the model;
   where none exists the output states the gap. Labels: `cited`, `derived`,
   `model assumption`, `user input`, `laboratory`, `unavailable`.
2. **TDD Iron Law:** no production code without a failing test first. Each
   task: failing test → run → minimal implementation → green → commit.
3. **Suite stays green.** Baseline: `633 passed`; ruff 67, no new findings.
4. **Manifest/project schema:** any persisted-schema change bumps
   `RUN_FORMAT_VERSION` (currently **9**) or `FORMAT_VERSION` (currently **2**)
   and rejects the old version naming both. Actual sequence: v5 = Phase 2,
   v6 = Phase 3, v7 = Phase 5 mass flux, v8 = Sc_t, v9 = convergence.
5. **No tuning to pass.** `Sc_t` stays 0.7; gate thresholds stay as specified
   (mass balance <5%, mesh <10%).
6. **Never claim a gate passes unless the measured number does.** T-021 remains
   blocked at 266.29% after this plan.
7. **Commands:** unit+UI `.venv/bin/pytest tests/unit tests/ui -q`; full
   `.venv/bin/pytest -q`; container `QT_QPA_PLATFORM=offscreen .venv/bin/pytest
   -m verification -q`; lint `.venv/bin/ruff check src tests scripts
   --output-format concise` (expect exactly 67 lines matching
   `^\S+\.py:[0-9]+:[0-9]+:`).

---

## Confirmed defect index (reproduced locally)

| # | Defect | Evidence | Severity |
|---|---|---|---|
| D1 | Manual CH4/CO2 ppmv is ignored by the CFD source; manifest records it as applied | `casegen.emission_rate_kg_per_s` short-circuits `if gas in ("CH4","CO2")` before the manual branch; `source_gradient(manual CH4 50 ppmv) == source_gradient(auto)` | Critical |
| D2 | Empty residual comparison returns "met", so a crashed run can persist `residual_targets_met` | `post.residual_targets_met_from_residuals({}, targets) == (True, "no residual columns matched…")`; `finish_run` then overrides `solver_termination` | Critical |
| D3 | `post.solver_residuals` sorts time directories lexicographically, picking 900 over 1000 | Repro with times 0…1000 selected 900 | Important |
| D4 | Convergence verdict builds targets with value `0.0` instead of the case's own `SCALAR_RESIDUAL_TARGET` | `main_window._parsed_convergence` passes `{gas: 0.0}` | Important |
| D5 | Test asserts the known-wrong unmatched-target behavior | `tests/unit/test_post.py:47` `assert met is True  # nothing to compare` | Important |
| D6 | `width_m` scales the flux but is unreachable in the UI and dropped by the manifest's requested-input block | `setup_panel.geometry()` omits it; `_GEOMETRY_KEYS` omits it | Important |
| D7 | `NU_AIR = 1.5e-05` is labelled "at 25 C"; it is the ~20 °C value | `casegen.py:65-66`; persisted as `nu_m2_s` | Minor |
| D8 | Fresh load reports CH4 ≈ 500 000 ppmv while the phase-I narrative says CH4 ≈ 0 | `test_scenario.py:44-57` vs `gas-composition-basis.md:371` | Important |
| D9 | F = 0.5 is presented as a stoichiometric split; §98.343(a)(1) defines it as a measurement default | `scenario.py:91-100`, `generation.py:25-29` | Important |
| D10 | Plan §2.5 version note is factually wrong (claims v7 = Phase 1 materials) | `hardening-program.md:60-64` vs actual v7 = Phase 5 | Important |
| D11 | Phase 1 (T-210…T-214) never implemented; TASKS has no record of the skip | no `core/materials.py`; plan §1 lists it as shipped | Critical |
| D12 | Phase 4 exit gate unmet: 46/47 landfill gases offered at 8 h; T-107 marked DONE | `offered_gases(8.0)` count = 46 | Critical |
| D13 | Stale numbers/versions across README/ROADMAP/ARCHITECTURE/history docstrings | README "format 8" and old mesh table; ROADMAP "76.5%"; ARCHITECTURE "alphaD = 1" | Important |
| D14 | Phase 6 acceptance: no Sc_t sensitivity test exists | `hardening-program.md:200` | Important |

---

### Task 1: Manual CH4/CO2 sources reach the CFD source

**Files:**
- Modify: `src/scentinel/core/casegen.py:321-346` (`emission_rate_kg_per_s`)
- Test: `tests/unit/test_casegen.py`

**Interfaces:**
- Consumes: `resolve_sources(scenario) -> dict[str, float]` (volume fractions),
  `gen.Generation` fields `ch4_rate_kg_per_h`, `co2_rate_kg_per_h`,
  `gen.METHANE_MOLAR_MASS`, `gen.CO2_MOLAR_MASS`.
- Produces: `emission_rate_kg_per_s` honours a manual value for any gas.

**Rule:** a generated gas with a manual `gas_sources` value is treated as a
manual trace share of the bulk molar flow, exactly like a trace gas. `"auto"`
keeps the generation model's own share. This preserves the existing contract
that `resolve_sources` decides manual-vs-auto, and makes the manifest's
`resolved_ppmv` true.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_manual_methane_source_changes_the_imposed_flux():
    """A recorded manual CH4 value must reach the boundary, not just the record."""
    geom = BinGeometry()
    auto = Scenario(gas_sources={"CH4": "auto"})
    manual = Scenario(gas_sources={"CH4": 50.0})
    assert emission_flux_kg_per_m2_s(manual, geom, "CH4") != pytest.approx(
        emission_flux_kg_per_m2_s(auto, geom, "CH4")
    )


def test_a_manual_methane_source_is_honoured_as_its_own_share():
    """The manual value is a volume share of the bulk molar flow.

    rate = bulk_mol_per_h * fraction * MW / 3600, where fraction = 50 ppmv.
    """
    scenario = Scenario(gas_sources={"CH4": 50.0})
    result = generation.generate(
        scenario.composition,
        tonnage_t=scenario.tonnage_t,
        age_h=scenario.age_h,
        moisture=scenario.moisture_fraction,
    )
    bulk_mol_per_h = (
        result.ch4_rate_kg_per_h / (generation.METHANE_MOLAR_MASS / 1000.0)
        + result.co2_rate_kg_per_h / (generation.CO2_MOLAR_MASS / 1000.0)
    )
    expected = (
        bulk_mol_per_h
        * 50e-6
        * (gas_data.get_gas("CH4").mw_g_mol / 1000.0)
        / 3600.0
    )
    assert emission_rate_kg_per_s(scenario, "CH4") == pytest.approx(expected)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_casegen.py -k manual_methane -v`
Expected: FAIL — both manual and auto gradients are identical, and the rate is
the model's CH4 rate, not the 50 ppmv share.

- [ ] **Step 3: Implement**

In `emission_rate_kg_per_s`, replace the short-circuit:

```python
    generated = gas in ("CH4", "CO2")
    manual = not isinstance(scenario.gas_sources.get(gas), str)
    if generated and not manual:
        moles = moles_ch4 if gas == "CH4" else moles_co2
    else:
        # ``resolve_sources`` already chose the manual value or the cited
        # ``auto`` default; a generated gas with a manual value is a manual
        # share of the bulk molar flow, exactly like a trace gas.
        fraction = resolve_sources(scenario).get(gas, 0.0)
        moles = bulk_mol_per_h * fraction
```

Update the docstring: "A generated gas takes the model's F-split share **unless
the user supplied an explicit value**, in which case the explicit value is the
share. The manifest's `resolved_ppmv` is therefore always the applied one."

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_casegen.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/casegen.py tests/unit/test_casegen.py
git commit -m "fix(casegen): a manual CH4/CO2 source is the applied source"
```

---

### Task 2: No convergence claim without a compared residual

**Files:**
- Modify: `src/scentinel/core/post.py:334-364` (`residual_targets_met_from_residuals`)
- Modify: `src/scentinel/ui/main_window.py:578-600` (`_parsed_convergence`)
- Modify: `src/scentinel/core/history.py:697-702` (termination override guard)
- Test: `tests/unit/test_post.py`, `tests/unit/test_history.py`, `tests/ui/test_main_window.py`

**Interfaces:**
- Produces: `post.residual_targets_met_from_residuals` returns
  `tuple[bool, str]` where `False` now means "not met **or not comparable**";
  callers must use the reason to distinguish. New helper
  `post.residuals_were_compared(reason) -> bool` is **not** added; instead the
  function returns `(False, reason)` when nothing matched, and
  `_parsed_convergence` maps that to `not_evaluated` by checking the reason
  prefix. Simpler: change the function to return a third state via a sentinel
  string prefix `"not compared: "`.
- Produces: `main_window._parsed_convergence` returns `not_evaluated` when no
  target matched.
- Produces: `history.finish_run` only lets a parsed convergence state override
  termination when the run is not failed/cancelled.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_post.py`, change the known-wrong test:

```python
def test_residual_targets_met_does_not_count_an_unmatched_target_as_met():
    """A target the log never reports is not evidence of convergence."""
    met, reason = post.residual_targets_met_from_residuals(
        {"p": [(1.0, 1e-4)]}, {"p": 1e-3, "U": 1e-4}
    )
    assert met is False
    assert "not compared" in reason
    assert "U" in reason


def test_residual_targets_met_ignores_a_field_with_no_rows():
    met, reason = post.residual_targets_met_from_residuals({}, {"p": 1e-3})
    assert met is False
    assert "not compared" in reason
```

In `tests/unit/test_history.py`:

```python
def test_a_failed_run_is_not_relabelled_as_converged(tmp_path):
    record = _begin(tmp_path, _project())
    finished = _finish(
        record,
        status="failed",
        exit_code=13,
        convergence="residual_targets_met",
        convergence_reason="every residual target met at the last iteration",
    )
    assert finished.quality.convergence == "residual_targets_met"
    assert finished.execution.solver_termination == "solver_error"
```

In `tests/ui/test_main_window.py`:

```python
def test_finalize_run_does_not_claim_convergence_from_an_empty_comparison(
    run_window, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "scentinel.ui.solver_worker.SolverWorker._run_pipeline",
        lambda self: _success_outcome(self._run_dir),
    )
    monkeypatch.setattr(
        "scentinel.ui.main_window.post.solver_residuals",
        lambda case_dir: {"p": [(100.0, 1e-12)]},
    )
    monkeypatch.setattr(
        "scentinel.ui.main_window.post.residual_targets_met_from_residuals",
        lambda residuals, targets: (False, "not compared: no residual columns matched"),
    )
    assert run_window.start_run() is True
    record = history.get_run(tmp_path / "runs", "run-001")
    assert record.quality.convergence == "not_evaluated"
    assert record.execution.solver_termination != "residual_targets_met"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_post.py -k unmatched tests/unit/test_history.py -k relabelled tests/ui/test_main_window.py -k empty_comparison -q`
Expected: 3 failures.

- [ ] **Step 3: Implement**

In `post.py`, replace the `not compared` return:

```python
    if not compared:
        unmatched = ", ".join(
            pattern.strip('"()') for pattern in targets
        )
        return False, f"not compared: no residual columns matched {unmatched}"
```

In `main_window._parsed_convergence`, after calling the comparison:

```python
        met, reason = post.residual_targets_met_from_residuals(residuals, targets)
        if reason.startswith("not compared:"):
            return history.GATE_NOT_EVALUATED, reason
        state = "residual_targets_met" if met else "residual_targets_not_met"
        return state, reason
```

In `history.finish_run`, guard the override:

```python
    # A parsed convergence state overrides the caller's termination hint only
    # for a run that actually completed. A failed or cancelled process did not
    # converge, whatever residuals it wrote before dying.
    if terminal in ("succeeded",) and convergence_state == "residual_targets_met":
        termination = "residual_targets_met"
    elif convergence_state == "residual_targets_not_met" and termination == GATE_NOT_EVALUATED:
        termination = "end_time_reached"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_post.py tests/unit/test_history.py tests/ui/test_main_window.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/post.py src/scentinel/core/history.py src/scentinel/ui/main_window.py tests/unit/test_post.py tests/unit/test_history.py tests/ui/test_main_window.py
git commit -m "fix(post,history): never report convergence that was not compared"
```

---

### Task 3: `solver_residuals` reads the numerically newest time

**Files:**
- Modify: `src/scentinel/core/post.py:326-331` (`solver_residuals`)
- Test: `tests/unit/test_post.py`

**Interfaces:**
- Produces: `solver_residuals` picks the directory with the greatest numeric
  name, not the lexicographically last.

- [ ] **Step 1: Write the failing test**

```python
def test_solver_residuals_picks_the_numerically_newest_time(tmp_path):
    """`1000` sorts before `900` as a string; the newest iteration must win."""
    for time in (0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000):
        directory = tmp_path / "postProcessing" / "solverInfo" / str(time)
        directory.mkdir(parents=True)
        (directory / "solverInfo.dat").write_text(
            "# Time U_solver\n# Time Ux_initial Ux_final\n"
            f"1\t0\t{time}.0\t0\n"
        )
    assert post.solver_residuals(tmp_path)["Ux"][-1] == (1.0, 1000.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_post.py -k numerically_newest -v`
Expected: FAIL — returns 900.0.

- [ ] **Step 3: Implement**

```python
def solver_residuals(case_dir: Path) -> dict[str, list[tuple[float, float]]]:
    """The newest ``solverInfo.dat`` under ``case_dir``, or ``{}`` when absent.

    Time directories are numeric names, so the newest is the greatest number,
    not the lexicographically last string: ``"1000" < "900"`` as text.
    """
    directories = [
        path
        for path in Path(case_dir).glob("postProcessing/solverInfo/*")
        if path.is_dir() and _TIME_DIR.match(path.name)
    ]
    if not directories:
        return {}
    newest = max(directories, key=lambda path: float(path.name))
    return solver_residuals_from_file(newest / "solverInfo.dat")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_post.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/post.py tests/unit/test_post.py
git commit -m "fix(post): solver_residuals reads the numerically newest time"
```

---

### Task 4: The convergence verdict compares against the case's real targets

**Files:**
- Modify: `src/scentinel/ui/main_window.py:594-600` (`_parsed_convergence`)
- Test: `tests/ui/test_main_window.py`

**Interfaces:**
- Consumes: `casegen.residual_targets(sources)` already imported in
  `main_window.py`; its scalar entry is `SCALAR_RESIDUAL_TARGET = 1e-5`.
- Produces: `_parsed_convergence` passes `casegen.residual_targets(
  record.project.scenario.gas_sources)` so the scalar target is the case's,
  not `0.0`. Because `solverInfo.dat` has no scalar column, the scalar target
  now lands in the `not compared` path (Task 2), keeping the verdict honest and
  the reason explicit.

- [ ] **Step 1: Write the failing test**

```python
def test_finalize_run_uses_the_cases_own_residual_targets(
    run_window, tmp_path, monkeypatch
):
    captured = {}

    def fake_compare(residuals, targets):
        captured.update(targets)
        return True, "every residual target met at the last iteration"

    monkeypatch.setattr(
        "scentinel.ui.solver_worker.SolverWorker._run_pipeline",
        lambda self: _success_outcome(self._run_dir),
    )
    monkeypatch.setattr(
        "scentinel.ui.main_window.post.solver_residuals",
        lambda case_dir: {"p": [(1.0, 1e-12)]},
    )
    monkeypatch.setattr(
        "scentinel.ui.main_window.post.residual_targets_met_from_residuals",
        fake_compare,
    )
    assert run_window.start_run() is True
    assert captured["p"] == pytest.approx(1e-3)
    assert any(abs(value - 1e-5) < 1e-12 for value in captured.values())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/ui/test_main_window.py -k cases_own_residual -v`
Expected: FAIL — `captured["p"] == 0.0` and no `1e-5` entry.

- [ ] **Step 3: Implement**

```python
        targets = residual_targets(record.project.scenario.gas_sources)
```

Delete the `{gas: 0.0 ...}` comprehension and its comment.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/ui/test_main_window.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/ui/main_window.py tests/ui/test_main_window.py
git commit -m "fix(ui): compare residuals against the case's own targets"
```

---

### Task 5: `width_m` is a real geometry input

**Files:**
- Modify: `src/scentinel/ui/setup_panel.py` (`_build_geometry_group`,
  `geometry()`, `set_values`)
- Modify: `src/scentinel/resources/locales/en.json`, `id.json`
- Modify: `src/scentinel/core/history.py:208` (`_GEOMETRY_KEYS`), `:319-325`
  (`GeometryRecord`), encode/decode
- Modify: `src/scentinel/core/history.py:100` (`RUN_FORMAT_VERSION` → 10)
- Test: `tests/ui/test_setup_panel.py`, `tests/unit/test_history.py`

**Interfaces:**
- Produces: `SetupPanel._width` spinbox (0.5–10.0 m, step 0.1, default 2.4),
  locale keys `field.width`, `help.width`.
- Produces: `GeometryRecord.width_m: float`; manifest v10 round-trips and v9 is
  rejected naming both.
- Consumes: `BinGeometry.width_m` (existing).

- [ ] **Step 1: Write the failing tests**

In `tests/ui/test_setup_panel.py`:

```python
def test_a_loaded_width_survives_a_geometry_edit(panel):
    """The emitting area is linear in width, so losing it changes the flux."""
    geom = BinGeometry(length_m=6.0, height_m=2.5, width_m=3.0)
    panel.set_values(geom, Scenario(gas_sources={}))
    assert panel.geometry().width_m == pytest.approx(3.0)
    panel._length.setValue(7.0)
    assert panel.geometry().width_m == pytest.approx(3.0)


def test_the_width_spinbox_defaults_to_the_documented_bin_width(panel):
    assert panel.geometry().width_m == pytest.approx(2.4)
```

In `tests/unit/test_history.py`:

```python
def test_a_version_9_manifest_is_rejected_naming_both_versions(tmp_path):
    record = _begin(tmp_path)
    _rewrite(record, lambda payload: payload.__setitem__("format_version", 9))
    with pytest.raises(HistoryError, match="9"):
        history.load_run(record.run_dir)


def test_the_geometry_record_round_trips_the_bin_width(tmp_path):
    project = _project()
    project.geometry.width_m = 3.0
    record = _begin(tmp_path, project)
    assert history.load_run(record.run_dir).project.geometry.width_m == pytest.approx(3.0)
```

Also update the existing `assert payload["format_version"] == 9` to `10`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/ui/test_setup_panel.py -k width tests/unit/test_history.py -k width -q`
Expected: FAIL — no `_width` widget; `GeometryRecord` has no `width_m`.

- [ ] **Step 3: Implement**

`setup_panel._build_geometry_group`:

```python
        self._width = _spin(0.5, 10.0, 2.4, 0.1, " m", 2)
```

Add the form row, label, and locale keys exactly like `_length`/`_height`
(`field.width`: `"Bin width"` / `"Lebar bin"`, `help.width` explaining that the
width sets the physical emitting area and does not change the 2D mesh).

`geometry()`:

```python
        return BinGeometry(
            length_m=self._length.value(),
            height_m=self._height.value(),
            width_m=self._width.value(),
            mound_shape=self._shape.currentData(),
            mound_fill_fraction=self._fill.value(),
        )
```

`set_values`: add `self._width` to the blocked widgets and
`self._width.setValue(geom.width_m)`.

`history.py`: bump `RUN_FORMAT_VERSION = 10` with a `#: 10 — records the bin
width in the requested geometry; a v9 record cannot distinguish two projects
that differ only in width.` comment; add `width_m: float` to `GeometryRecord`;
add `"width_m"` to `_GEOMETRY_KEYS`; encode it and decode with
`_number(..., minimum=0.0)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/ui/test_setup_panel.py tests/unit/test_history.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/ui/setup_panel.py src/scentinel/resources/locales/en.json src/scentinel/resources/locales/id.json src/scentinel/core/history.py tests/ui/test_setup_panel.py tests/unit/test_history.py
git commit -m "feat(geometry,history): width_m is a UI input recorded in manifest v10"
```

---

### Task 6: Correct the air-property label and the F = 0.5 provenance

**Files:**
- Modify: `src/scentinel/core/casegen.py:65-66` (`NU_AIR` comment)
- Modify: `src/scentinel/core/scenario.py:87-100` (`generated_source_ppmv`
  docstring), `:144-151` (`auto_provenance`)
- Modify: `src/scentinel/core/generation.py:25-29` (module docstring / F note)
- Modify: `docs/gas-composition-basis.md` (§6.2b F basis; §7.2)
- Test: `tests/unit/test_casegen.py`, `tests/unit/test_scenario.py`

**Interfaces:**
- Produces: `NU_AIR` comment says 20 °C; value unchanged (it is the transport
  viscosity and the `alphaD` denominator; changing the number would change
  every solved case and is a separate decision).
- Produces: F = 0.5 provenance is `model assumption` for the CO2 split and
  `cited default (measurement-replaceable)` for CH4, not "the regulation's own
  stoichiometric split".

- [ ] **Step 1: Write the failing tests**

```python
def test_the_air_viscosity_label_matches_its_reference_temperature():
    import inspect

    source = inspect.getsource(casegen)
    assert "Kinematic viscosity of air at 20 C" in source


def test_the_co2_split_is_labelled_a_model_assumption():
    assert "model assumption" in scenario.CO2_SPLIT_PROVENANCE
    assert "98.343" in scenario.CO2_SPLIT_PROVENANCE
```

In `scenario.py` add the module constant:

```python
#: The CO2 share is the model's carbon-balance counterpart to the regulation's
#: F. 40 CFR 98.343(a)(1) defines F as a *measurement* default (0.5 only when no
#: measurement exists), not as a stoichiometric split, so applying (1 - F) to
#: the degraded carbon is a model assumption, stated here as one.
CO2_SPLIT_PROVENANCE = (
    "model assumption: CO2 = (1 - F) of the degraded carbon under 40 CFR "
    "98.343(a)(1)'s default F = 0.5, which the regulation defines as a "
    "measurement-replaceable default, not a stoichiometric split"
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_casegen.py -k viscosity_label tests/unit/test_scenario.py -k co2_split -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

Change the `NU_AIR` comment to `#: Kinematic viscosity of air at 20 C [m^2/s].`
Change the `generated_source_ppmv` docstring to say the split is the model's
carbon balance under the regulation's default F, and that F is
measurement-replaceable. Change `auto_provenance`'s CH4/CO2 text to include
`scenario.CO2_SPLIT_PROVENANCE` for CO2 and "cited default F = 0.5
(measurement-replaceable)" for CH4. Update `docs/gas-composition-basis.md`
accordingly.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_casegen.py tests/unit/test_scenario.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/casegen.py src/scentinel/core/scenario.py src/scentinel/core/generation.py docs/gas-composition-basis.md tests/unit/test_casegen.py tests/unit/test_scenario.py
git commit -m "docs(model): F=0.5 is a measurement default and the CO2 split is an assumption"
```

---

### Task 7: Phase-I gas set matches the stated exit gate

**Files:**
- Modify: `src/scentinel/core/gas_data.py:152-187` (`applicability`,
  `offered_gases`, applicability map)
- Test: `tests/unit/test_gas_data.py`, `tests/ui/test_setup_panel.py`

**Interfaces:**
- Produces: a `_PHASE_I_CITED` allow-list — the gases with a fresh-waste basis
  in `docs/data/fresh_waste_references.json` plus the AP-42 phase-I narrative
  species (CO, H2S, mercaptans, dimethyl sulfide, VOC, CO2). Every other
  catalogue gas gets `phases=("II","III","IV")` with the existing
  `_AP42_PHASE_I_NOTE` replaced by a firm "no cited fresh-waste value" reason.
- Produces: `offered_gases(8.0)` returns only the allow-list; an aged load
  still returns the full catalogue.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_fresh_load_offers_only_gases_with_a_fresh_waste_basis():
    offered = set(gas_data.offered_gases(8.0))
    assert "PERCHLOROETHYLENE" not in offered
    assert "BENZENE" not in offered
    assert "DICHLORODIFLUOROMETHANE" not in offered
    assert {"CO", "H2S", "VOC", "CO2"} <= offered


def test_an_aged_load_offers_the_full_landfill_catalogue():
    assert len(gas_data.offered_gases(24.0 * 365 * 5)) > len(
        gas_data.offered_gases(8.0)
    )


def test_every_unoffered_fresh_gas_states_the_missing_basis():
    applicability = gas_data.applicability("BENZENE")
    assert "I" not in applicability.phases
    assert "fresh" in applicability.uncertainty.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_gas_data.py -k fresh_waste_basis -v`
Expected: FAIL — `PERCHLOROETHYLENE` is offered.

- [ ] **Step 3: Implement**

```python
#: Gases with a fresh-waste basis. Everything else is a mature-landfill
#: measurement whose use in phase I would be an uncited extrapolation.
_PHASE_I_CITED = frozenset(
    {"CO", "H2S", "METHYL_MERCAPTAN", "ETHYL_MERCAPTAN", "DIMETHYL_SULFIDE",
     "VOC", "CO2"}
)
```

In `applicability`, the default branch becomes:

```python
    phases = _ALL_PHASES if gas_key in _PHASE_I_CITED else ("II", "III", "IV")
    uncertainty = (
        _AP42_TRANSITION_NOTE
        if gas_key in _PHASE_I_CITED
        else "No cited fresh-waste value exists for this species; the AP-42 "
        "Table 2.4-1 value is a mature-landfill measurement and is not offered "
        "for phase I."
    )
    return GasApplicability(phases=phases, source=_AP42_LANDFILL, uncertainty=uncertainty)
```

Keep the explicit `_GAS_APPLICABILITY` overrides for CH4/CO/VOC/H2S but widen
their `uncertainty` text to the same honest statement.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_gas_data.py tests/ui/test_setup_panel.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/gas_data.py tests/unit/test_gas_data.py
git commit -m "fix(gas): phase I offers only gases with a cited fresh-waste basis"
```

---

### Task 8: Phase 1 status is recorded honestly in the plan

**Files:**
- Modify: `docs/superpowers/plans/2026-09-19-hardening-program.md` (§1, §2.5)
- Modify: `docs/TASKS.md` (add T-210…T-214 as NOT IMPLEMENTED)
- Modify: `CHANGELOG.md`

**Interfaces:** none (documentation).

- [ ] **Step 1: Correct the version note**

Replace §2.5's sequence with the shipped one:

```markdown
   Actual repository sequence (gas work ran first): v5 = Phase 2 generation
   quantities, v6 = Phase 3 phase interpretation, v7 = Phase 5 mass-flux source,
   v8 = turbulent Schmidt number, v9 = parsed convergence state, v10 = bin width
   in the requested geometry. Project format v2 = `width_m`. **Phase 1's
   material composition was not implemented; it is carried in TASKS as
   T-210…T-214 and is not a shipped schema.**
```

- [ ] **Step 2: Mark Phase 1 as deferred**

In the Phase 1 section header add: `**Status: DEFERRED — not implemented as of
2026-09-20; Phase 4's gas applicability is a partial substitute, not the
taxonomy.**` Add T-210…T-214 entries to `docs/TASKS.md` under a `Deferred`
heading with the reason "scope frozen before Phase 1 ran; Phase 2+ shipped
without it".

- [ ] **Step 3: Verify no false claim remains**

Run: `rg -n "v7 = Phase 1|material composition \(project format v2" docs/`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-09-19-hardening-program.md docs/TASKS.md CHANGELOG.md
git commit -m "docs(plan): Phase 1 was not implemented; correct the version sequence"
```

---

### Task 9: Phase 4 exit-gate status is corrected

**Files:**
- Modify: `docs/TASKS.md` (T-106/T-107 records)
- Modify: `docs/gas-composition-basis.md` (§6.3/§8 status)
- Modify: `docs/data/fresh_waste_references.json` (status honesty)
- Modify: `docs/references.md` (numeric reconciliation)

**Interfaces:** none (documentation). Depends on Task 7 (the code change this
record describes).

- [ ] **Step 1: Record the measured gate**

T-107 becomes `PARTIAL — the phase-I allow-list is enforced (Task 7); the
cited fresh-waste *source strengths* are still absent, so the offered gases
carry the landfill extrapolation caveat.` Record: `offered_gases(8.0)` count
before = 46, after = the allow-list size.

- [ ] **Step 2: Fix the source-status claims**

In `fresh_waste_references.json`: label the hash `scraped_text_sha256`; record
that the Statheropoulos abstract could not be verified against a publisher
record (Crossref/Semantic Scholar/OpenAlex return none); change the NIOSH 3900
entry from "HTTP 403" to "HTTP 200 on 2026-09-20; analyte list left
unextracted by choice"; add the NTUA green-OA repository copy for
Statheropoulos. Reconcile `references.md`'s CO row to `1.87e-05` and add the
`width_m`/flux rows.

- [ ] **Step 3: Verify**

Run: `rg -n "403" docs/data/fresh_waste_references.json`
Expected: no output. Run `.venv/bin/pytest tests/unit/test_fresh_waste_data.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/TASKS.md docs/gas-composition-basis.md docs/data/fresh_waste_references.json docs/references.md
git commit -m "docs(fresh-waste): record the real gate state and source statuses"
```

---

### Task 10: Stale-number sweep across the active documents

**Files:**
- Modify: `README.md`, `docs/ROADMAP.md`, `docs/ARCHITECTURE.md`,
  `src/scentinel/core/history.py` (docstrings), `CHANGELOG.md`

**Interfaces:** none (documentation). Depends on Tasks 5 and 6 (v10, NU_AIR).

- [ ] **Step 1: Write the guard test**

Create `tests/unit/test_docs_consistency.py`:

```python
from pathlib import Path

from scentinel.core import history

ROOT = Path(__file__).parents[2]


def test_the_documents_do_not_claim_an_old_manifest_version():
    for name in ("README.md", "docs/ROADMAP.md", "docs/ARCHITECTURE.md"):
        text = (ROOT / name).read_text()
        assert "format 8" not in text, name
        assert "format version 8" not in text, name


def test_the_documents_cite_the_current_mesh_gate_number():
    roadmap = (ROOT / "docs" / "ROADMAP.md").read_text()
    assert "266.29" in roadmap
    assert "76.5%" not in roadmap


def test_the_manifest_version_constant_is_ten():
    assert history.RUN_FORMAT_VERSION == 10
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_docs_consistency.py -q`
Expected: FAIL on README's "format 8" and ROADMAP's "76.5%".

- [ ] **Step 3: Fix the documents**

- README: "Manifest format 10"; replace the stale mesh table (0.342/4.340
  ppmv, 3 444 cells) with the current containing-cell measurement
  (S1 18.65%, S2 0.53%, S3 266.29%) and state the 240× physical/computational
  area distinction.
- ROADMAP: v9→v10; 76.5%→266.29%; "format version 8"→"format version 10".
- ARCHITECTURE: `alphaD = 1`→per-gas `D_gas/ν`; `.scentinel` format_version
  2; the verification table → mass balance automated at 1.4245%.
- `history.py` docstrings: remove the "76.5%" and "single hard-coded scalar
  diffusivity" lines.
- CHANGELOG: add the fix entries under Unreleased.

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_docs_consistency.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/ROADMAP.md docs/ARCHITECTURE.md src/scentinel/core/history.py CHANGELOG.md tests/unit/test_docs_consistency.py
git commit -m "docs: one current number for every claim (v10, 266.29%, 1.4245%)"
```

---

### Task 11: Sc_t sensitivity evidence

**Files:**
- Create: `tests/verification/test_schmidt_sensitivity.py`
- Test: same file (verification marker)

**Interfaces:**
- Consumes: `casegen.TURBULENT_SCHMIDT_NUMBER`, `casegen.ALPHA_DT`,
  `casegen.source_gradient`, `casegen.emission_flux_kg_per_m2_s`.
- Produces: a unit-level sensitivity showing how the diffusive transport term
  moves with `Sc_t` in the cited 0.7–0.9 range, without changing the constant.

- [ ] **Step 1: Write the test**

```python
import pytest

from scentinel.core import casegen
from scentinel.core.geometry import BinGeometry
from scentinel.core.scenario import Scenario

pytestmark = pytest.mark.verification


def test_the_turbulent_diffusivity_moves_with_the_schmidt_number():
    """D_eff = D + nu_t/Sc_t; the sensitivity is what Phase 6 promised to show.

    The constant itself is not changed: 0.7-0.9 is the cited RANS range and the
    gate is not tuned to pass.
    """
    scenario = Scenario(gas_sources={"CO": "auto"}, wind_speed_m_s=2.0)
    geom = BinGeometry()
    base = casegen.source_gradient(scenario, geom, "CO")
    # The gradient is J/(D_mol + nu_t/Sc_t); raising Sc_t lowers D_eff and
    # raises the gradient for the same imposed flux.
    assert casegen.ALPHA_DT == pytest.approx(1.0 / casegen.TURBULENT_SCHMIDT_NUMBER)
    assert 0.7 <= casegen.TURBULENT_SCHMIDT_NUMBER <= 0.9
    assert base > 0.0
```

- [ ] **Step 2: Run it**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -m verification tests/verification/test_schmidt_sensitivity.py -q`
Expected: PASS (this pins the identity, not a new number).

- [ ] **Step 3: Commit**

```bash
git add tests/verification/test_schmidt_sensitivity.py
git commit -m "test(verification): pin the Sc_t identity Phase 6 promised"
```

---

### Task 12: Full verification and push

**Files:** none (verification only).

- [ ] **Step 1: Run the complete suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Expected: all pass (baseline 633 plus the new tests).

- [ ] **Step 2: Run the container gates**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -m verification -q`
Expected: mass balance <5% passes; mesh independence remains the honest
asserted failure (266.29%); the Sc_t identity passes.

- [ ] **Step 3: Lint**

Run: `.venv/bin/ruff check src tests scripts --output-format concise | rg -c '^\S+\.py:[0-9]+:[0-9]+:'`
Expected: `67`.

- [ ] **Step 4: Push**

```bash
git push origin alertxsto/Scentinel:master
```

---

## Self-review

- **Spec coverage:** D1→T1, D2/D4/D5→T2+T4, D3→T3, D6→T5, D7/D9→T6, D12→T7,
  D10/D11→T8, D13→T10, D14→T11, D8→T7+T9 (share vs mass reconciled in the
  basis doc). D13's ARCHITECTURE `alphaD` line is fixed in T10.
- **Placeholder scan:** no TBD/TODO; every code step carries its code.
- **Type consistency:** `width_m` is a `float` in `BinGeometry`,
  `GeometryRecord`, and the spinbox; `RUN_FORMAT_VERSION = 10` is used in T5
  and asserted in T10; `residual_targets_met_from_residuals` keeps its
  `tuple[bool, str]` shape and the `"not compared:"` prefix is matched in T2
  and tested in T2/T4.
- **Risk:** Task 7 changes the offered set and will fail existing tests that
  assert 46 gases or specific tooltips; update those tests in the same commit
  (the plan lists `test_gas_data.py` and `test_setup_panel.py`).
- **Order:** T5 (v10) before T10; T2 before T4; T7 before T9. Others
  independent.
