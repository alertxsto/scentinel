# Scentinel — Task Breakdown

**Version:** 0.1.0 · **Last updated:** 2026-09-19

Every task with its status, the files it touches, and its acceptance test. Phase
context is in [ROADMAP.md](ROADMAP.md).

Legend: **DONE** · **TODO** · **BLOCKED**

---

## Done

### F0 — Foundation

#### T-001 Project scaffolding · DONE
Files: `.gitignore`, `pyproject.toml`, `src/scentinel/__init__.py`, `tests/conftest.py`
Acceptance: package imports; `pytest` collects; `QT_QPA_PLATFORM=offscreen` set for headless UI tests.

#### T-002 Container setup script · DONE
Files: `scripts/setup_container.sh`
Acceptance: script pulls the image and verifies `gmshToFoam`, `changeDictionary`, `simpleFoam`, `foamToVTK` all resolve inside the container.

#### T-003 Podman runner · DONE
Files: `src/scentinel/core/runner.py`, `tests/unit/test_runner.py`
Acceptance: streams output line by line; reports which stage failed via exit code; cancels the whole process tree, not just the direct child.
Tests: 9 unit.

#### T-004 Main window, setup panel, and i18n · DONE
Files: `src/scentinel/ui/main_window.py`, `src/scentinel/ui/setup_panel.py`, `src/scentinel/ui/i18n.py`, `resources/locales/{en,id}.json`
Acceptance: window opens; menus retranslate on language switch; project lifecycle (new/open/save/save-as) with dirty tracking; the setup panel emits `changed(geom, scenario)` without spamming on programmatic loads, and the `auto` gas checkbox disables the manual value.
Tests: 9 UI (window) + 11 (setup panel) + 5 (i18n).

### F1 — Geometry, mesh, placement

#### T-005 2D geometry builder · DONE
Files: `src/scentinel/core/geometry.py`, `tests/unit/test_geometry.py`
Acceptance: requested fill fraction is met for all three mound shapes; mound never leaves the bin; height query matches the outline.
Note: `mound_surface` (open polyline) is distinct from `mound_polygon` (closed outline) — conflating them makes a flat mound produce a self-touching mesh outline.
Tests: 15 unit.

#### T-006 gmsh meshing · DONE
Files: `src/scentinel/core/mesh.py`, `tests/unit/test_mesh.py`
Acceptance: MSH 2.2 written; volume cells present; ≥99% hexahedral; all seven patches tagged; every mound shape meshes.
Tests: 14 unit.

#### T-007 OpenFOAM case writer · DONE
Files: `src/scentinel/core/casegen.py`, `tests/unit/test_casegen.py`
Acceptance: `auto` sources resolve to cited AP-42 defaults; wind direction swaps inlet/outlet; every patch gets a boundary condition in every field; `changeDictionaryDict` types the special patches.
Tests: 17 unit.

#### T-008 Viewport with sensor placement · DONE
Files: `src/scentinel/ui/viewport.py`, `tests/ui/test_viewport.py`
Acceptance: clicks inside the free air place a sensor; clicks in the mound or outside the bin are rejected; raising the mound evicts buried sensors; ids are not reused.
Tests: 9 UI.

#### T-009 Project save/load · DONE
Files: `src/scentinel/core/project.py`, `tests/unit/test_project.py`
Acceptance: round-trip equality; unknown `format_version` rejected.
Tests: 4 unit.

#### T-010 End-to-end single-gas run · DONE
Files: `tests/integration/test_e2e_scenario.py`
Acceptance: mesh converts, patch types are corrected, solver converges without `FOAM FATAL`, VTK is written, a probe near the waste reads a positive concentration below the source strength.
Tests: 6 integration (the 7th `integration`-marked test is the podman-availability check in `test_runner.py`).

### F2 — Multi-gas and probes

#### T-011 Gas data loader · DONE
Files: `src/scentinel/core/gas_data.py`, `tests/unit/test_gas_data.py`
Acceptance: four gases with physical properties and cited defaults; `msw-only` vs `co-disposal` regimes; CH₄ fraction converted to ppmv.
Tests: 8 unit.

#### T-012 Multi-gas case generation · DONE
Files: `src/scentinel/core/casegen.py` (per-gas `0/<gas>`, `scalarTransport`, `div(phi,<gas>)`, solver entry)
Acceptance: one field and one function object per selected gas; concentration stays below the source at every probe.

#### T-013 Post-processing and probes · DONE
Files: `src/scentinel/core/post.py`
Acceptance: latest time directory found; cell data sampled (not point data); `TimeValue` metadata excluded from scalar fields.

#### T-014 Results panel · DONE
Files: `src/scentinel/ui/results_panel.py`, `tests/ui/test_main_window.py`
Acceptance: table fills with one row per sensor and one column per gas in ppmv; CSV export writes the same numbers.

#### T-015 Solver worker · DONE
Files: `src/scentinel/ui/solver_worker.py`
Acceptance: pipeline runs off the GUI thread; log streams to the panel; cancel stops a running solve and the app can run again afterwards.
Note: meshing is delegated to a child process because gmsh installs a `SIGINT` handler, which Python forbids outside the main thread.

### F3 — Comparison and reporting

#### T-030 Run history manager · DONE
Files: `src/scentinel/core/history.py` (new), `tests/unit/test_history.py` (new),
`src/scentinel/core/casegen.py`, `src/scentinel/ui/main_window.py`,
`src/scentinel/ui/solver_worker.py`, `resources/locales/{en,id}.json`,
`tests/ui/test_main_window.py`, `tests/unit/test_casegen.py`
Acceptance: every attempt reserves a never-reused `run-NNN` directory and writes
one versioned `run.json` before the solver starts; `finish_run()` replaces it
atomically for succeeded, failed, and cancelled attempts, and a crash leaves an
honest `incomplete` record. Records survive a restart and can be looked up by id
through `list_runs()` / `get_run()`.
Note: manifest format version 2 holds four separated things — the requested
inputs, the applied numerical experiment, the execution outcome, and the
evidence quality.
- *Requested:* project snapshot, per-gas mode/resolved ppmv/provenance, and the
  ventilation request qualified as `{"requested_on": …, "modelled": false}`,
  because the case generator ignores the flag.
- *Applied:* `inlet_speed_at_rim_m_s` after the wind profile, the profile type,
  exponent and reference height, `nu_m2_s`, per-gas `scalar_diffusivity_m2_s`
  as actually written, the linear-solver tolerances, residual targets,
  relaxation factors, and a SHA-256 digest of the declared case inputs. The
  values come from `casegen` constants that also render the case files, so a
  manifest cannot claim a setting the case does not use.
- *Execution:* `execution_status`, requested end iteration, solver/image,
  output metadata, and `solver_termination` (never inferred from exit code 0).
- *Quality:* `screening_estimate` plus closed-enum `convergence`,
  `mesh_independence`, `mass_balance`, and `experimental_validation` states,
  all non-passing for an ordinary run, and separate verification/validation
  metric arrays that stay empty — an empty array never means "passed".

Readings are validated against the frozen sensor snapshot (ids, coordinates,
order, gas keys) at finalization *and* on load; the worker samples a frozen
project copy rather than the live model. Allocation uses `mkdir(exist_ok=False)`
as the concurrency authority and scans the highest existing `run-NNN`, so a
restart cannot reuse an id. `core.history` imports without the optional `cfd`
extra, so the read API works on a machine without gmsh. No comparison view
reads the history yet (T-031).
Tests: 80 unit (core) + 21 UI orchestration.

#### T-030a Applied-physics evidence and gate states · DONE
Files: `src/scentinel/core/casegen.py`, `src/scentinel/core/history.py`,
`tests/unit/test_casegen.py`, `tests/unit/test_history.py`
Why: the first T-030 manifest recorded the *requested* controls, not the
applied experiment, and left `succeeded` as the only per-run gate state. Two
records with identical manifests could describe different boundary conditions
or transport coefficients, and a successful process could be rendered as
converged or verified.
Change: added the `applied_physics` block with the case-input digest, renamed
the top-level status to `execution_status`, qualified ventilation, added the
closed-enum gate states, and required `geom` in `write_case()` so the inlet
speed and the persisted reference height cannot diverge.
Acceptance: each persisted applied value is asserted against the generated case
files; a changed applied constant changes the digest at identical UI inputs;
exit code 0 leaves every scientific gate non-passing; a reading-less clean exit
is `failed` with an explicit reason; readings that do not match the frozen
sensors are rejected.

---

## TODO

### Blocking

#### T-020 Mass-flux source term · TODO — **blocks T-021**
Files: `src/scentinel/core/casegen.py`, `src/scentinel/ui/setup_panel.py`, `docs/references.md`
Why: the current `fixedValue` concentration makes sampled values depend on the first cell height, so mesh independence fails at 76.5% and does not converge.
Change: impose emission as kg/m²/s on the `source` patch; convert to a wall concentration using molecular weight and a mass-transfer coefficient; expose the source strength in the UI with its citation.
Acceptance: `pytest -m verification` shows probe deviation <10% between mesh sizes 0.5 m and 0.25 m, with the trend decreasing.
Note: this restores what the design spec originally described (§4.2, §4.3).

#### T-021 Mesh-independence gate · BLOCKED on T-020
Files: `tests/verification/test_mesh_independence.py`
Current state: the test measures the deviation and asserts it is *still* above 10%, so it fails loudly once the fix lands and forces a convergence assertion to replace it.
Acceptance: asserts <10% and the trend is monotone with refinement.

### F2 remainder

#### T-022 Mass-balance check · TODO
Files: `src/scentinel/core/post.py` (`mass_balance_error` exists but is unused), `tests/verification/test_mass_balance.py`
Why: the spec gate is <5%; a hand-rolled estimate currently reads ~8%.
Change: re-run `foamToVTK -surfaceFields` in the pipeline, then compare the integrated source flux against the outlet flux.
Acceptance: automated test asserting <5% for a converged case.

#### T-023 Analytical 1D diffusion benchmark · TODO
Files: `tests/verification/test_1d_diffusion.py`
Why: the spec gate is R² > 0.99 against the erfc solution. It validates the scalar transport setup independently of the bin geometry.
Change: run a 1D case with a fixed concentration at one end, compare the profile to `erfc(x / 2√(Dt))`.
Acceptance: R² > 0.99.

#### T-024 Field visualisation · TODO
Files: `src/scentinel/ui/field_view.py` (new), `src/scentinel/ui/main_window.py`, `src/scentinel/core/casegen.py`
Why: results are currently a table of numbers; the spec asks for concentration fields and streamlines.
Change: add `cutPlaneSurface` and `streamlinesLine` function objects to the case; render the resulting VTK with pyvista in a dock widget beside the viewport; add a gas selector and a colour bar.
Acceptance: after a run, the selected gas renders as a colour field with streamlines overlaid, and switching gas updates the view.

#### T-025 Ventilation flag · TODO
Files: `src/scentinel/core/casegen.py`, `src/scentinel/ui/setup_panel.py`, `src/scentinel/core/history.py`
Why: `Scenario.ventilation_on` is stored, round-trips through the project file, and never reaches the case. The manifest now records it as `{"requested_on": …, "modelled": false}` and `load_run()` rejects `modelled: true`, so the flag cannot be mistaken for applied physics in the meantime.
Change: either model it (an inlet at the bin rim) or remove it from the UI and the data model. Deciding is the task; carrying a dead flag is not acceptable. Modelling it must also flip the `modelled` invariant and the `VentilationRecord` docstring deliberately.
Acceptance: toggling the flag changes the generated case, or the flag no longer exists.

### F3 — Comparison and reporting

#### T-031 Comparison view · TODO
Files: `src/scentinel/ui/comparison_view.py` (new), `tests/ui/test_comparison_view.py`
Change: pick two or more recorded runs, show probe values side by side with a difference column.
Constraints from T-030: consume the strict `load_run()` contract and report corrupt records individually rather than hiding valid ones; refuse to compare runs whose `case_input_digest` differs unless the mismatch is explicit; never group or difference by `ventilation.requested_on` while `ventilation.modelled` is false; display `screening_estimate` and every gate state beside each compared result.
Acceptance: a difference column appears and matches the underlying readings, and a digest mismatch blocks the comparison.

#### T-032 PDF report · TODO
Files: `src/scentinel/core/report.py` (new), `tests/unit/test_report.py`
Change: a report with the geometry, scenario, cited gas defaults, probe table, and a field image.
Acceptance: a valid `%PDF` file is written and contains the probe values.

### F4 — 3D and transient

#### T-040 3D geometry and meshing · TODO
Change: extrude the 2D cross-section to the bin width; `checkMesh` must pass.
Acceptance: a 3D case solves.

#### T-041 Transient settings · TODO
Change: `ddtSchemes { default backward; }`, adjustable `deltaT`, probe time series.
Acceptance: a transient run writes a time series at each probe.

#### T-042 Response-delay analysis · TODO
Files: `src/scentinel/core/delay.py` (new)
Change: time to reach 50% and 90% of steady state per sensor.
Acceptance: matches a synthetic first-order response.

---

## Backlog

| Item | Why it is deferred |
|---|---|
| Lid-driven cavity benchmark | Superseded by the e2e case, which exercises more of the pipeline |
| Restore `docs/Scentinel_Project_Overview_V1.pdf` build | `scripts/build_pdf.py` needs `weasyprint`; PDF is in the repo already |
| Remove the leaked header rows in `gas_defaults.py` | `AP42_TRACE_COMPOUNDS["Compound"]` and `AP42_TABLE_2_4_2[0]` are column headers, not data; harmless but sloppy |
| Type the string `conc_ppmv` values | `'110e'`, `'4.0x10-3'` etc. break `float()`; they are footnote-marked AP-42 entries |
| Wayland + VTK smoke test | The spec flags it as a risk; pyvista is not used in the UI yet, so it is untested |
| Unsaved-project run namespace | Unsaved projects share `<cwd>/runs`; allocation is collision-safe and each run keeps its own snapshot, so there is no pairing corruption. Decide save-before-run versus per-session namespacing when history UI semantics are designed |
| First-cell height in the verification record | Needed for credible mesh-convergence/GCI evidence, not for ordinary run persistence. Add it to a future verification-record schema once it is measured |
| Probe containment diagnostics | `find_closest_cell` can hide invalid probe positions. Address with containment/distance diagnostics in post-processing verification, then persist the diagnostic; do not fake it in T-030 |
| Reproducible Scrapling acquisition manifest | `scripts/scrape_references.py` saves raw pages but no acquisition record (canonical URL, retrieval UTC, HTTP status/headers, content SHA-256, raw artifact path, tool/parser versions, repository revision, extraction-rule version, structured-output hash, failure history). Deferred to the next provenance architecture; keep raw responses immutable and make `build_gas_data.py` reproducible offline from checksummed artifacts |
| Residual/termination parsing | Required before `solver_termination` or `quality.convergence` can ever report anything but `not_evaluated`. Parse the `residuals` function object output and record the reason; never infer it from exit code 0 |
