# Phase 7 — CFD Verification Gates: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the four verification gates into automated checks: mesh
independence is measured (and honestly reported while it fails), mass balance is
computed from the solver's own flux, convergence is parsed from the solver's
own residual output, and no sensor is ever sampled from a cell that does not
contain it.

**Architecture:** Two defects found by the Phase 5/6 audit drive this phase.
`casegen._functions` writes a `residuals` function object that OpenFOAM v2512
does not have (the solver logs `Unknown function type residuals` and continues),
and `post.mass_balance_error` looks for `phi_{gas}` arrays that
`foamToVTK -surfaceFields` never writes (it writes `phi` under
`VTK/surface-fields/`). Both gates are therefore currently evaluating nothing.
The fix is to use the mechanisms v2512 actually provides — `solverInfo` for
residuals and `surfaceFieldValue` for patch fluxes — and to parse their `.dat`
output.

**Tech Stack:** Python 3.12+ (CI), pytest, OpenFOAM v2512 in Podman, PyVista.

**Spec:** `docs/superpowers/plans/2026-09-19-hardening-program.md` (Phase 7,
T-021/T-022/T-241/T-242). Design spec:
`docs/superpowers/specs/2026-09-18-scentinel-design.md` §7 (gates).

## Global Constraints

1. A value without a citation does not enter the model; a gap is stated.
2. Provenance labels: `cited`, `derived`, `model assumption`, `user input`,
   `laboratory`, `unavailable`.
3. TDD: failing test → run → minimal implementation → green → commit.
4. Baseline after the audit fix: `613 passed`; ruff 67, no new findings.
5. Persisted-schema change bumps the version and rejects the old naming both.
   Manifest v8 is current.
6. i18n: en/id keys for any user-visible string.
7. Container gates: `pytest -m verification`.
8. **Exit code 0 must never be read as convergence.** `quality.convergence`
   stays `not_evaluated` unless the solver's own residual file was parsed.

## Verified facts (do not re-derive)

Measured on OpenFOAM v2512 in the container on 2026-09-19:

- `residuals` is **not** a valid function type; the solver logs
  `--> FOAM Warning : Unknown function type residuals` and carries on. Valid
  names include `solverInfo`.
- `solverInfo` with `fields (p U k epsilon CO)` writes
  `postProcessing/solverInfo/0/solverInfo.dat` with a header line of column
  names and one row per time. The file exists at time 0 and is appended each
  write interval.
- `foamToVTK -latestTime -surfaceFields` writes a single
  `VTK/surface-fields/surfaceFields_<time>.vtp` carrying one `phi` array over
  the whole boundary — **not** `phi_<gas>` per patch under `boundary/`. The
  `boundary/*.vtp` patches carry `CO`, `p`, `U`, `k`, `epsilon`, `nut`.
- `surfaceFieldValue` with `fields (phi); operation sum; regionType patch;
  name source; weightField CO;` writes
  `postProcessing/sourceFlux/0/surfaceFieldValue.dat`. **`operation sum` ignores
  `weightField`** — it returned the identical value with and without it. To
  weight, the operation must be `weightedSum`. `name` accepts **one** patch
  name; a regex like `"(openLeft|openRight)"` makes the solver fail. Two
  entries are needed for the two open sides.
- **Third defect, found while validating the mass-balance mechanism: the
  source patch's `nut` is `calculated`, so the imposed flux is ~1789x the
  intended one.** `scalarTransport` uses `D = alphaD*nu + alphaDt*nut` at the
  face, and the source patch's `nut` boundary is `calculated` with a cell value
  ~0.0234 m^2/s. Measured, on the same case and end time:

  | `source` nut BC | `nut` at the wall | outlet/source flux ratio |
  |---|---|---|
  | `calculated` (current) | 2.336e-02 | **1789x** |
  | `nutkWallFunction` | 2.664e-04 | 21.3x |
  | `fixedValue 0` | 0 | **1.027x** |

  With `fixedValue uniform 0` the mass balance closes to 2.7%, and the analytic
  identity `outlet == D_mol * gradient * area` holds. This is a Phase 6
  regression: before it, the function object used a constant `D`, so the wall
  flux was `D_mol * gradient` by construction. `nut` on a solid wall physically
  is zero, so `fixedValue 0` is the correct boundary, not a workaround.
- `grid.find_containing_cell(point)` returns `-1` for a point inside the solid
  mound (verified: `(0.5, 0.2)` with `mound_height_at = 0.457` -> `-1`), while
  `find_closest_cell` returns a wall cell (412) with an absurd value. This is
  the mechanism T-242 needs.
- The mesh-independence deviation is scale-invariant: it measured 19.56% worst
  probe after the unit fix, unchanged from before it.

---

### Task 0 (T-020c): the source patch's nut is zero, not calculated

This is the prerequisite for the mass-balance gate: with `nut=calculated` the
imposed flux is 1789x too high, so no mass balance can close.

**Files:**
- Modify: `src/scentinel/core/casegen.py` (`_field_nut`)
- Test: `tests/unit/test_casegen.py`

**Interfaces:**
- Consumes: `PatchRole.kind` (existing).
- Produces: `_field_nut` writes `fixedValue uniform 0` on `source` patches (a
  solid wall), keeping `nutkWallFunction` on the bin walls and `calculated` on
  the open/top patches.

- [ ] **Step 1: Write the failing test**

```python
def test_the_source_wall_has_zero_turbulent_viscosity(tmp_path, mesh):
    """``scalarTransport`` uses ``D = alphaD*nu + alphaDt*nut`` at the face.

    A ``calculated`` nut on the solid source patch carries the first cell's
    value (~0.023) into the wall flux, inflating the imposed emission ~1789x
    (measured). ``nut`` is physically zero at a solid wall, and only then does
    ``D_face == D_mol`` so ``gradient * D_mol`` is the flux the manifest claims.
    """
    case = write_case(
        Scenario(gas_sources={"CO": "auto"}), mesh, tmp_path / "case",
        geom=BinGeometry(),
    )
    nut = (case / "0" / "nut").read_text()
    source = nut.split("source")[1].split("}")[0]
    assert "fixedValue" in source
    assert "uniform 0" in source
    assert "calculated" not in source
    # The bin walls keep their wall function.
    wall = nut.split("wallLeft")[1].split("}")[0]
    assert "nutkWallFunction" in wall
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_casegen.py::test_the_source_wall_has_zero_turbulent_viscosity -v`
Expected: FAIL — the source block says `calculated`.

- [ ] **Step 3: Write minimal implementation**

In `_field_nut`, give `source` its own branch before the generic else:

```python
    for name, role in roles.items():
        if role.kind == "empty":
            lines.append(f"    {name}\n    {{\n        type            empty;\n    }}\n")
        elif role.kind == "wall":
            lines.append(f"    {name}\n    {{\n        type            nutkWallFunction;\n        value           uniform 0;\n    }}\n")
        elif role.kind == "source":
            # Solid wall: nut is zero, so the scalar's face diffusivity is the
            # gas's molecular D and ``gradient * D`` is the imposed flux.
            lines.append(f"    {name}\n    {{\n        type            fixedValue;\n        value           uniform 0;\n    }}\n")
        else:
            lines.append(f"    {name}\n    {{\n        type            calculated;\n        value           uniform 0;\n    }}\n")
```

- [ ] **Step 4: Run the tests and the mass-balance probe**

Run: `.venv/bin/pytest tests/unit/test_casegen.py -q`
Expected: PASS.

Then re-run the controlled three-way measurement to confirm the fix closes
the balance:

```bash
.venv/bin/python /tmp/opencode/nut_wf.py   # or the equivalent inline script
```
Expected: the `fixedValue` row reports `ratio` near 1.0.

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/casegen.py tests/unit/test_casegen.py
git commit -m "fix(casegen): zero nut on the source wall so the flux is D_mol*gradient"
```

---

### Task 1 (T-241a): the case writes a function object that exists

**Files:**
- Modify: `src/scentinel/core/casegen.py:816-846` (`_functions`)
- Test: `tests/unit/test_casegen.py`

**Interfaces:**
- Consumes: `resolve_sources(scenario)` → `dict[str, float]` (existing).
- Produces: `_functions(sources)` writes `solverInfo` (not `residuals`) plus
  one `scalarTransport` per gas. `casegen.RESIDUALS_FUNCTION_NAME = "solverInfo"`.

- [ ] **Step 1: Write the failing test**

```python
def test_the_residual_function_object_exists_in_v2512(tmp_path, mesh):
    """``residuals`` is not a valid function type in v2512.

    The solver logs ``Unknown function type residuals`` and continues, so the
    old block was silently doing nothing. ``solverInfo`` is the v2512 name and
    is the object whose output T-241 parses.
    """
    case = write_case(
        Scenario(gas_sources={"CO": "auto"}), mesh, tmp_path / "case", geom=BinGeometry()
    )
    functions = (case / "system" / "functions").read_text()
    assert "solverInfo" in functions
    assert "\nresiduals\n" not in functions
    assert "type            solverInfo;" in functions
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_casegen.py::test_the_residual_function_object_exists_in_v2512 -v`
Expected: FAIL — the block says `residuals`.

- [ ] **Step 3: Write minimal implementation**

In `_functions`, replace the residuals block:

```python
    return (
        _header("dictionary", "functions")
        + "solverInfo\n{\n    type            solverInfo;\n"
        + "    libs            (utilityFunctionObjects);\n"
        + "    fields          (p U k epsilon"
        + "".join(f" {gas}" for gas in sources)
        + ");\n}\n\n"
        + body
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_casegen.py -q`
Expected: PASS. Check for other tests asserting `residuals`:
`rg -n "residuals" tests/ src/` — update any that assert the block name
(`tests/unit/test_casegen.py` has `test_control_dict_names_the_solver`-style
checks; only the block name changes, not `residual_targets`).

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/casegen.py tests/unit/test_casegen.py
git commit -m "fix(casegen): write solverInfo, not the nonexistent residuals object"
```

---

### Task 2 (T-241b): parse solverInfo into a convergence state

**Files:**
- Modify: `src/scentinel/core/post.py` (add `solver_residuals`)
- Modify: `src/scentinel/core/history.py` (`finish_run` accepts the parsed state)
- Test: `tests/unit/test_post.py` (create if absent), `tests/unit/test_history.py`

**Interfaces:**
- Produces:
  - `post.solver_residuals(case_dir: Path) -> dict[str, list[tuple[float, float]]]`
    — field name → list of `(time, initial_residual)`, from
    `postProcessing/solverInfo/*/solverInfo.dat`. Returns `{}` when absent.
  - `post.residual_targets_met(case_dir, targets: dict[str, float]) -> tuple[bool, str]`
    — compares the last initial residual of each target field against its
    target; returns `(met, reason)`. `reason` is a human string naming the
    worst field and both numbers.
- Consumes: `casegen.residual_targets(sources)` (existing) — keys are field
  names like `p`, `U`, `"(k|epsilon)"`, `"(CO|CH4)"`; the parenthesised,
  pipe-joined form is how `fvSolution` writes them, so parsing must strip the
  quotes and split on `|`.

- [ ] **Step 1: Write the failing tests**

A hand-written 25-column row is error-prone, so capture a real file once with
the container, commit it as a fixture, and parse that:

```bash
.venv/bin/python - <<'EOF'
from pathlib import Path
import tempfile
from scentinel.core import casegen, runner
from scentinel.core.geometry import BinGeometry
from scentinel.core.mesh import generate_mesh
from scentinel.core.scenario import Scenario
root = Path(tempfile.mkdtemp(dir="/tmp/opencode"))
mesh = generate_mesh(BinGeometry(), 1.0, root/"mesh")
case = casegen.write_case(Scenario(gas_sources={"CO": "auto"}), mesh,
                          root/"case", geom=BinGeometry(), end_time=20)
assert runner.run_case(case).ok
src = next((case/"postProcessing"/"solverInfo").rglob("solverInfo.dat"))
Path("tests/fixtures").mkdir(exist_ok=True)
Path("tests/fixtures/solverInfo.dat").write_text(src.read_text())
print(src.read_text()[:400])
EOF
```

Create `tests/unit/test_post.py`:

```python
from pathlib import Path

from scentinel.core import post

FIXTURE = Path(__file__).parent.parent / "fixtures" / "solverInfo.dat"


def test_solver_residuals_reads_initial_residuals_per_field():
    residuals = post.solver_residuals_from_file(FIXTURE)
    assert "p" in residuals
    assert "Ux" in residuals
    assert residuals["p"]
    time, value = residuals["p"][-1]
    assert isinstance(time, float)
    assert isinstance(value, float)


def test_residual_targets_met_reports_the_worst_field():
    residuals = {"p": [(1.0, 0.5)], "Ux": [(1.0, 1e-5)]}
    met, reason = post.residual_targets_met_from_residuals(
        residuals, {"p": 1e-3, "U": 1e-4}
    )
    assert met is False
    assert "p" in reason
    assert "0.5" in reason


def test_residual_targets_met_passes_when_every_field_is_under():
    residuals = {"p": [(1.0, 1e-4)], "Ux": [(1.0, 1e-5)]}
    met, reason = post.residual_targets_met_from_residuals(
        residuals, {"p": 1e-3, "U": 1e-4}
    )
    assert met is True


def test_residual_targets_met_ignores_a_field_with_no_rows():
    """A target the log never reports cannot silently count as met."""
    met, reason = post.residual_targets_met_from_residuals(
        {"p": [(1.0, 1e-4)]}, {"p": 1e-3, "U": 1e-4}
    )
    assert met is True  # nothing to compare against; only p is present
    assert reason
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_post.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'solver_residuals_from_file'`.

- [ ] **Step 3: Write minimal implementation**

In `post.py`:

```python
def solver_residuals_from_file(path: Path) -> dict[str, list[tuple[float, float]]]:
    """Initial residuals per solver field, from a ``solverInfo.dat``.

    The header names the columns (``# Time  U_solver  Ux_initial  ...``); the
    first column is time and each ``<field>_initial`` column is that field's
    initial residual. Vector fields are reported per component (``Ux``,
    ``Uy``), so a caller matching the target ``U`` must accept the prefix.
    """
    text = Path(path).read_text()
    header: list[str] = []
    for line in text.splitlines():
        if line.startswith("#") and "Time" in line:
            header = line.lstrip("#").split()
            break
    if not header:
        raise ValueError(f"{path} has no solverInfo header")
    columns = {
        name.removesuffix("_initial"): index
        for index, name in enumerate(header)
        if name.endswith("_initial")
    }
    parsed: dict[str, list[tuple[float, float]]] = {name: [] for name in columns}
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cells = line.split()
        if len(cells) < len(header):
            continue
        time = float(cells[0])
        for name, index in columns.items():
            parsed[name].append((time, float(cells[index])))
    return parsed


def solver_residuals(case_dir: Path) -> dict[str, list[tuple[float, float]]]:
    """The newest ``solverInfo.dat`` under ``case_dir``, or ``{}`` when absent."""
    files = sorted(
        Path(case_dir).glob("postProcessing/solverInfo/*/solverInfo.dat")
    )
    return solver_residuals_from_file(files[-1]) if files else {}


def residual_targets_met_from_residuals(
    residuals: dict[str, list[tuple[float, float]]],
    targets: dict[str, float],
) -> tuple[bool, str]:
    """Compare each target's last initial residual against its ``fvSolution`` value.

    ``targets`` keys are the written field patterns: ``p``, ``U``, and the
    parenthesised ``"(k|epsilon)"``. A pattern matches a column when the column
    equals one of its names or starts with it (``U`` matches ``Ux``/``Uy``).
    A target with no matching column is not evidence of convergence, so it is
    skipped — the reason string says so when nothing was compared.
    """
    offenders: list[tuple[float, str, float, float]] = []
    compared = 0
    for pattern, target in targets.items():
        for name in pattern.strip('"()').split("|"):
            for field, series in residuals.items():
                if (field == name or field.startswith(name)) and series:
                    compared += 1
                    value = series[-1][1]
                    if value > target:
                        offenders.append((value / target, field, value, target))
    if not compared:
        return True, "no residual columns matched the targets; nothing to compare"
    if not offenders:
        return True, "every residual target met at the last iteration"
    _, field, value, target = max(offenders)
    return (
        False,
        f"{field} initial residual {value:.3g} exceeds its target {target:.3g}",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_post.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/post.py tests/unit/test_post.py tests/fixtures/solverInfo.dat
git commit -m "feat(post): parse solverInfo residuals and compare to the targets"
```

---

### Task 3 (T-241c): the manifest records the parsed convergence state

**Files:**
- Modify: `src/scentinel/core/history.py` (`finish_run`, `QualityRecord`)
- Modify: `src/scentinel/ui/main_window.py:544-575` (`_finalize_run`)
- Test: `tests/unit/test_history.py`, `tests/ui/test_main_window.py`

**Interfaces:**
- Consumes: `post.solver_residuals(case_dir)`,
  `post.residual_targets_met_from_residuals(...)`,
  `casegen.residual_targets(sources)`.
- Produces: `finish_run(..., convergence: str = GATE_NOT_EVALUATED,
  convergence_reason: str = "")`. `quality.convergence` becomes
  `"residual_targets_met"` or `"residual_targets_not_met"`;
  `execution.solver_termination` becomes `"residual_targets_met"` when met,
  else stays `"end_time_reached"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_finish_run_records_a_parsed_convergence_state(tmp_path):
    record = _begin(tmp_path, _project())
    finished = _finish(
        record,
        convergence="residual_targets_not_met",
        convergence_reason="p initial residual 0.5 exceeds its target 0.001",
    )
    assert finished.quality.convergence == "residual_targets_not_met"
    assert "p initial residual" in finished.quality.convergence_reason
    assert finished.execution.solver_termination == "end_time_reached"


def test_finish_run_records_met_targets_as_termination(tmp_path):
    record = _begin(tmp_path, _project())
    finished = _finish(
        record,
        convergence="residual_targets_met",
        convergence_reason="every residual target met at the last iteration",
    )
    assert finished.execution.solver_termination == "residual_targets_met"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_history.py -k convergence -v`
Expected: FAIL — `finish_run() got an unexpected keyword argument 'convergence'`.

- [ ] **Step 3: Write minimal implementation**

Add `convergence_reason: str` to `QualityRecord` (empty string default),
extend `finish_run`'s signature and the `_QUALITY_KEYS`/encode/decode pair, and
derive `solver_termination` from the convergence state. Wire the UI:
`_finalize_run` reads `outcome.case_dir`, calls `post.solver_residuals`, and
passes the parsed values through. When `case_dir` is `None` or the file is
absent, pass `not_evaluated` and the reason
`"no solverInfo.dat was written for this run"`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_history.py tests/ui/test_main_window.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/history.py src/scentinel/ui/main_window.py tests/unit/test_history.py tests/ui/test_main_window.py
git commit -m "feat(history): persist the parsed convergence state and its reason"
```

---

### Task 4 (T-242a): sensor containment at sampling

**Files:**
- Modify: `src/scentinel/core/post.py:104-142` (`sample_sensors`)
- Test: `tests/unit/test_post.py`

**Interfaces:**
- Produces: `SensorReading.contained: bool` (new field, default `True`) and
  `SensorReading.reason: str` (default `""`). `sample_sensors` uses
  `grid.find_containing_cell`; a sensor outside the fluid returns a reading
  with `contained=False`, empty `values`, and a reason.
- Consumes: nothing new.

- [ ] **Step 1: Write the failing test**

```python
def test_a_buried_sensor_is_rejected_not_snapped(tmp_path):
    """A point inside the mound has no containing cell.

    ``find_closest_cell`` returns the nearest wall cell, which reads the
    near-wall value as if it were the probe's — the defect the audit found in
    the bin benchmark's old floor probe. ``find_containing_cell`` returns -1,
    which must become an explicit rejection.
    """
    grid = pv.ImageData(dimensions=(3, 3, 3))
    grid.cell_data["CO"] = np.zeros(8)
    # A point outside the grid has no containing cell.
    readings = post.sample_sensors_from_grid(
        grid, [Sensor("outside", 99.0, 99.0)]
    )
    assert readings[0].contained is False
    assert readings[0].values == {}
    assert readings[0].reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_post.py::test_a_buried_sensor_is_rejected_not_snapped -v`
Expected: FAIL — `sample_sensors_from_grid` does not exist.

- [ ] **Step 3: Write minimal implementation**

Refactor `sample_sensors` to read the grid once and delegate to
`sample_sensors_from_grid(grid, sensors)`; in the loop use
`grid.find_containing_cell(point)` and, when it is `-1`, return the rejected
reading. Keep the mid-plane depth.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_post.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/post.py tests/unit/test_post.py
git commit -m "fix(post): sample the containing cell or reject, never snap to nearest"
```

---

### Task 5 (T-242b): containment at placement, with a reason

**Files:**
- Modify: `src/scentinel/ui/viewport.py:91-105` (`is_placeable`, `add_sensor`)
- Modify: `src/scentinel/core/geometry.py` (add `placement_problem`)
- Test: `tests/unit/test_geometry.py`, `tests/ui/test_viewport.py`

**Interfaces:**
- Produces: `geometry.placement_problem(geom, x, y) -> str` — `""` when
  placeable, else a user-facing reason (`"outside the bin"`,
  `"inside the waste mound"`). `is_placeable` delegates to it.
- Consumes: `mound_height_at` (existing).

- [ ] **Step 1: Write the failing tests**

```python
def test_placement_problem_names_why_a_point_is_rejected():
    geom = BinGeometry(length_m=6.0, height_m=2.5, mound_shape="mounded",
                       mound_fill_fraction=0.45)
    assert geometry.placement_problem(geom, 3.0, 2.6) == ""
    assert "outside" in geometry.placement_problem(geom, -0.1, 1.0)
    assert "mound" in geometry.placement_problem(geom, 0.5, 0.2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_geometry.py -k placement -v`
Expected: FAIL — no attribute `placement_problem`.

- [ ] **Step 3: Write minimal implementation**

Add `placement_problem` to `geometry.py`; make `viewport.is_placeable` call it.
The viewport's rejection stays silent for a click (the point simply does not
add a sensor), but the function is the single source of the rule so the reason
can be surfaced later.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_geometry.py tests/ui/test_viewport.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/geometry.py src/scentinel/ui/viewport.py tests/unit/test_geometry.py tests/ui/test_viewport.py
git commit -m "feat(geometry): one placement rule with a stated reason"
```

---

### Task 6 (T-022): the mass-balance gate

**Depends on Task 0**: with `nut=calculated` on the source patch the flux is
1789x too high and no balance can close. Do Task 0 first.

**Files:**
- Modify: `src/scentinel/core/casegen.py` (`_functions` — add the flux FO)
- Modify: `src/scentinel/core/post.py` (`mass_balance_error`)
- Create: `tests/verification/test_mass_balance.py`
- Test: `tests/unit/test_casegen.py`, `tests/unit/test_post.py`

**Interfaces:**
- Consumes: `surfaceFieldValue` output at
  `postProcessing/<name>/*/surfaceFieldValue.dat`.
- Produces:
  - `post.patch_fluxes(case_dir) -> dict[str, float]` — the last value per
    `postProcessing/*/surfaceFieldValue.dat`, keyed by the function object
    name (`outletFluxLeft`, `outletFluxRight`).
  - `post.mass_balance_error(case_dir, gas) -> float` rewritten to
    `(outlet - source) / |source|`, where `source` is the **analytic** flux the
    case imposes (`D_mol * gradient * emitting_area`, from the case's own
    `applied_physics`) and `outlet` is the CFD flux. Raises
    `FileNotFoundError` when the outlet file is missing.
- Note: the source patch cannot measure its own flux with `surfaceFieldValue`,
  because its `phi` is zero (no-slip wall) and its flux is diffusive. The
  reference is therefore the analytic value, which Task 0 makes exact; the gate
  checks that the CFD carries it out of the domain.

- [ ] **Step 1: Write the failing tests**

```python
def test_mass_balance_error_compares_outlet_to_the_analytic_source(tmp_path):
    (tmp_path / "postProcessing" / "outletFluxLeft" / "0").mkdir(parents=True)
    (tmp_path / "postProcessing" / "outletFluxLeft" / "0" / "surfaceFieldValue.dat").write_text(
        "# Region type : patch openLeft\n1\t-0.5\n"
    )
    (tmp_path / "postProcessing" / "outletFluxRight" / "0").mkdir(parents=True)
    (tmp_path / "postProcessing" / "outletFluxRight" / "0" / "surfaceFieldValue.dat").write_text(
        "# Region type : patch openRight\n1\t0.5\n"
    )
    error = post.mass_balance_error(tmp_path, "CO", source_flux=1.0)
    assert abs(error) < 1e-9


def test_mass_balance_error_is_negative_when_the_outlet_loses_flux(tmp_path):
    (tmp_path / "postProcessing" / "outletFluxRight" / "0").mkdir(parents=True)
    (tmp_path / "postProcessing" / "outletFluxRight" / "0" / "surfaceFieldValue.dat").write_text(
        "# Region type : patch openRight\n1\t0.5\n"
    )
    error = post.mass_balance_error(tmp_path, "CO", source_flux=1.0)
    assert error == pytest.approx(-0.5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_post.py -k mass_balance -v`
Expected: FAIL — the current signature has no `source_flux` and looks for
`phi_CO` under `VTK/.../boundary/`.

- [ ] **Step 3: Write minimal implementation**

Add the two outlet `surfaceFieldValue` entries to `_functions` (one per open
patch; `operation weightedSum`, `weightField <gas>`), and rewrite
`mass_balance_error` to read the last row of each `.dat` and compare against
`source_flux`. The caller computes `source_flux` from
`applied_physics(scenario, geom)["emission_flux_kg_per_m2_s"][gas]` times
`emitting_area_m2`, converted to the fraction basis with `Vm/MW` (the same
conversion as `casegen.source_gradient`, but not divided by `D`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/test_post.py tests/unit/test_casegen.py -q`
Expected: PASS.

- [ ] **Step 5: Write the verification test**

`tests/verification/test_mass_balance.py`:

```python
import pytest

from scentinel.core import casegen, gas_data, post, runner
from scentinel.core.geometry import BinGeometry, emission_area_m2
from scentinel.core.mesh import generate_mesh
from scentinel.core.scenario import Scenario

pytestmark = pytest.mark.verification


def test_mass_balance_on_a_solved_bin_case(tmp_path):
    if not runner.image_available():
        pytest.skip(f"{casegen.IMAGE} not pulled")
    geom = BinGeometry(length_m=6.0, height_m=2.5, mound_shape="mounded",
                       mound_fill_fraction=0.45)
    scenario = Scenario(gas_sources={"CO": "auto"}, tonnage_t=10.0,
                        age_h=24 * 365 * 3)
    mesh = generate_mesh(geom, 0.5, tmp_path / "mesh")
    case = casegen.write_case(scenario, mesh, tmp_path / "case", geom=geom,
                              end_time=500)
    result = runner.run_case(case)
    assert result.ok, runner.stage_log(case, result.failed_stage or "simpleFoam")[-2000:]

    # The analytic source the case imposes, in volume-fraction * m^2/s.
    flux = casegen.emission_flux_kg_per_m2_s(scenario, geom, "CO")
    mw = gas_data.get_gas("CO").mw_g_mol / 1000.0
    source = flux * (casegen.MOLAR_VOLUME_M3_PER_MOL / mw) * emission_area_m2(geom)
    error = post.mass_balance_error(case, "CO", source_flux=source)
    assert abs(error) < 0.05, f"mass balance error {error:.1%}"
```

- [ ] **Step 6: Run the verification test**

Run: `.venv/bin/pytest -m verification tests/verification/test_mass_balance.py -q`
Expected: PASS (<5%). The controlled measurement with Task 0 in place closed
to 2.7%; if the number is larger, record it in `docs/TASKS.md` T-022 rather
than loosening the bound.

- [ ] **Step 7: Commit**

```bash
git add src/scentinel/core/casegen.py src/scentinel/core/post.py tests/unit/test_post.py tests/unit/test_casegen.py tests/verification/test_mass_balance.py
git commit -m "feat(post): compute mass balance from weightedSum outlet flux"
```

---

### Task 7 (T-021): record the measured gate state, do not flip it

**Files:**
- Modify: `tests/verification/test_mesh_independence.py`
- Modify: `docs/TASKS.md`, `docs/ROADMAP.md`

- [ ] **Step 1: Re-measure with the audit fix in place**

Run the measurement script from the audit and record the worst probe:

```bash
.venv/bin/python - <<'EOF'
# same three probes and two meshes as the gate test
EOF
```

Expected: ~19.6% worst probe (scale-invariant). If the number moved, record the
new one and why.

- [ ] **Step 2: Decide by the rule, not by hope**

The gate flips to `assert worst < 10.0` **only if** the measurement is <10% and
monotone. It is neither, so the test keeps
`assert worst > 10.0` with the measured number and the cause in its docstring.
No change to `Sc_t`; the plan's model decision forbids tuning it to pass.

- [ ] **Step 3: Update the docs**

`docs/TASKS.md` T-021: state the post-audit measurement and that the remaining
cause is the velocity field. `docs/ROADMAP.md`: same number in the table.

- [ ] **Step 4: Commit**

```bash
git add tests/verification/test_mesh_independence.py docs/TASKS.md docs/ROADMAP.md
git commit -m "docs(gates): record the post-audit mesh deviation"
```

---

## Self-review

- **Spec coverage:** T-020c (new, the nut regression) → Task 0; T-021 →
  Task 7; T-022 → Task 6; T-241 → Tasks 1–3; T-242 → Tasks 4–5. The program's
  exit gate ("both numeric gates pass; convergence and containment are
  automated and persisted") is reachable: mass balance closes to 2.7% once
  Task 0 is in, convergence and containment become automated and persisted,
  and the mesh gate reports its measured state honestly while T-021's root
  cause (the velocity field) is unresolved.
- **Placeholder scan:** no "TBD"; Task 2's fixture is generated by a concrete
  command.
- **Type consistency:** `solver_residuals`, `solver_residuals_from_file`,
  `residual_targets_met_from_residuals`, `patch_fluxes`,
  `mass_balance_error(case_dir, gas, source_flux=...)`, `placement_problem`,
  `SensorReading.contained`, `SensorReading.reason`, `convergence_reason` are
  used with the same signatures in every task that mentions them.
- **Risk:** `solverInfo` writes once per write interval; a case with
  `writeInterval == endTime` writes one row. The parser handles a single row.
  `surfaceFieldValue` writes at time 0 too, where the flux is 0; the parser
  takes the **last** row, which is the converged value. The `source` patch
  cannot measure its own flux (no-slip `phi = 0`, diffusive flux), so the gate
  compares the CFD outlet against the analytic source; Task 0 is what makes
  that analytic value exact.
- **Order:** Task 0 must run before Task 6. The other tasks are independent.
