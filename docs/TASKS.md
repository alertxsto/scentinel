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
Files: `src/scentinel/core/casegen.py`, `src/scentinel/ui/setup_panel.py`
Why: `Scenario.ventilation_on` is stored, round-trips through the project file, and never reaches the case.
Change: either model it (an inlet at the bin rim) or remove it from the UI and the data model. Deciding is the task; carrying a dead flag is not acceptable.
Acceptance: toggling the flag changes the generated case, or the flag no longer exists.

### F3 — Comparison and reporting

#### T-030 Run history manager · TODO
Files: `src/scentinel/core/history.py` (new), `tests/unit/test_history.py`
Change: persist a record per run (id, project name, timestamp, case directory, probe summary) next to the project.
Acceptance: records survive a reload; a run can be looked up by id.

#### T-031 Comparison view · TODO
Files: `src/scentinel/ui/comparison_view.py` (new), `tests/ui/test_comparison_view.py`
Change: pick two or more recorded runs, show probe values side by side with a difference column.
Acceptance: a difference column appears and matches the underlying readings.

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
