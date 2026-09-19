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
Tests: 83 unit (core) + 11 UI orchestration.

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

## Done (continued — 2026-09-19 session)

#### T-050 Gas catalogue expansion · DONE
Files: `scripts/build_gas_data.py`, `src/scentinel/core/gas_defaults.py`,
`src/scentinel/core/gas_data.py`, `docs/references.md`, `tests/unit/test_gas_data.py`
Acceptance met: ten cited AP-42 species (CO, CH₄, VOC, H₂S, ethane, benzene,
toluene, vinyl chloride, methyl mercaptan, dimethyl sulfide). The generator reads
each value, rating, and basis out of the workbook rather than transcribing it,
and cross-checks molecular weights against the source row.
Note: ammonia was **excluded** — zero hits across all six workbook sheets. No
value was invented; the omission is recorded in `docs/references.md` §1.2.

#### T-051 Per-gas diffusivity · DONE
Files: `scripts/build_gas_data.py`, `src/scentinel/core/casegen.py`,
`tests/unit/test_casegen.py`, `tests/unit/test_history.py`
Why: the case applied one hard-coded diffusivity to every gas.
Change: Fuller-Schettler-Giddings for all ten gases (uniform method, no mixed
published values), T = 298.15 K, P = 1.01325 bar, atomic volumes from
Reid/Prausnitz/Poling 4th ed. Table 11-1, −18.3 per aromatic ring.
`casegen.scalar_diffusivity(gas)` is now the single source, the `scalarTransport`
D is per gas, and `applied_physics` persists exactly that mapping.
Acceptance: anchors verified — CO 1.87e-5, H₂S 1.71e-5, hexane proxy 7.66e-6 m²/s.
`SCALAR_DIFFUSIVITY_M2_S` deleted; every reference updated.

#### T-052 Waste stream model · DONE
Files: `src/scentinel/core/scenario.py`, `src/scentinel/ui/setup_panel.py`,
locale files, `tests/unit/test_scenario.py`, `tests/ui/test_setup_panel.py`
Acceptance met: six streams select the AP-42 regime and their default gases;
selecting a stream applies its gases and fractions without emitting spurious
changes on project load; `waste_type`/`organic_fraction`/`moisture_fraction`
round-trip through `.scentinel`.
**Known defect, see W0:** the organic-fraction scaling is uncited and can exceed
the physical CH₄ ceiling. This task records what shipped, not that it is correct.

#### T-053 Unified shell: top toolbar, one project · DONE
Files: `src/scentinel/ui/home_window.py`, `src/scentinel/ui/sensor_sandbox.py`,
`src/scentinel/ui/theme.py`, `tests/ui/test_home_window.py`
Acceptance met: the left navigation rail is gone; Dashboard / Simulation /
Sandbox live on a top toolbar; studio and sandbox share one editor and one
`.scentinel` file; recent projects restore geometry, sensors, lab settings, and
the last run; opening by path alone loads the project.

#### T-054 Container setup from the GUI, isolated storage · DONE
Files: `src/scentinel/core/container.py` (new), `src/scentinel/core/runner.py`,
`src/scentinel/ui/main_window.py`, `scripts/setup_container.sh`,
`tests/unit/test_container.py`
Why: the user asked for a GUI trigger and explicitly did not want the desktop
user's environment polluted.
Change: Podman storage lives under `~/.scentinel/containers/` (`SCENTINEL_HOME`
overrides); every podman call goes through `container.podman_env()`; **Run → Set
up OpenFOAM container** and a toolbar action pull and verify the image off the
GUI thread.
Note: the generated `storage.conf` selects `fuse-overlayfs` with
`ignore_chown_errors`. Without it, `--userns=keep-id` fails with "creating an
ID-mapped copy of layer" against a private graphroot — measured, then fixed.
Acceptance: image pulled into the isolated store (1.7 GB); the user's default
container storage was left untouched; all four pipeline tools verified.

#### T-055 RDF and exposure assessment · DONE (partial — see W2)
Files: `src/scentinel/core/assessment.py` (new), `src/scentinel/ui/results_panel.py`,
`tests/unit/test_assessment.py`
Acceptance met: peak-versus-limit checks against published limits (NIOSH REL,
methane LEL) with the exceedance ratio and the peak sensor; peak-to-mean as a
placement-coverage indicator; gas-phase chlorine and sulfur loading from the
AP-42 Table 2.4-1 trace species with the largest carrier named; gases without a
published limit reported as unchecked rather than given an invented one.
**Known defect, see T-122:** `halogen_load()` takes no scenario argument, so the
RDF block produces byte-identical output for every waste type. It is decorative.

#### T-056 Sandbox publishes its readings · DONE
Files: `src/scentinel/ui/sensor_sandbox.py`, `tests/ui/test_home_window.py`
Acceptance met: the replay writes into the same results table a solve fills
(`TVOC`, `GROUND_TRUTH`, `INTERFERENCE`); each sensor's CFD VOC is the ground
truth when a run result exists, with the lab fallback otherwise; reset clears
both the state and the table.

#### T-057 Analytical solver benchmarks · DONE
Files: `tests/verification/test_analytical_benchmarks.py` (new),
`src/scentinel/core/runner.py` (`BLOCKMESH_SCRIPT`)
Acceptance met: four benchmarks pass. Pure advection error **0.0000**; axial
diffusion within **0.0552** of the closed form at Pe = 5; bin probes stay inside
[0, source] and read positive above the mound.
Note: `BLOCKMESH_SCRIPT` was added because the default pipeline always runs
`gmshToFoam`, which cannot convert a `blockMesh` case. Three harness bugs were
found and fixed while building these: a reversed exact solution, a Peclet number
too high to resolve, and `diffusivity constant <D>;` — a form OpenFOAM silently
ignores, which made the first diffusion run read a flat profile.

#### T-058 Research basis document · DONE
Files: `docs/gas-composition-basis.md` (new), `docs/references.md`, `README.md`
Acceptance met: the document records the basis mismatch with citations, the
steady-state 55/40/5 ceiling, 40 CFR §98.343(a)(1) Equation HH-1, Table HH-1
DOC/k per material, and the decay-fraction table showing a 24-hour holding time
reaches below 0.06% of ultimate methane yield. Arithmetic independently
re-verified (ultimate yield 103.3 kg CH₄/Mg = 144 m³/Mg).

#### T-059 Release packaging · DONE
Files: `packaging/`, `scripts/build_linux_packages.sh`, `scripts/build_windows.ps1`,
`.github/workflows/release.yml`, `LICENSE`, `pyproject.toml`
Acceptance met: pushing a `v*` tag publishes `.deb`, `.rpm`, an Arch prefix
`.tar.gz` with `PKGBUILD`, and a Windows `.exe`. v0.2.0 is live.
Note: the first run failed because the nfpm asset name was wrong and `tar`
unpacked an HTML error page; fixed to `Linux_x86_64` with `curl -fsSL` and
`gzip -t`.

---

## TODO

### Blocking

#### T-020 Mass-flux source term · TODO — **blocks T-021**
Files: `src/scentinel/core/casegen.py`, `src/scentinel/ui/setup_panel.py`, `docs/references.md`
Why: the current `fixedValue` concentration makes sampled values depend on the first cell height, so mesh independence fails and does not converge. Measured 2026-09-19 with the analytical-benchmark harness: **56.4% (S1), 87.2% (S2), 8.5% (S3)** deviation between mesh sizes 0.50 m and 0.25 m on CO. The earlier 76.5% figure came from a different sensor set; both are far outside the 10% gate.
Change: impose emission as kg/m²/s on the `source` patch; convert to a wall concentration using molecular weight and a mass-transfer coefficient; expose the source strength in the UI with its citation.
Acceptance: `pytest -m verification` shows probe deviation <10% between mesh sizes 0.5 m and 0.25 m, with the trend decreasing.
Note: this restores what the design spec originally described (§4.2, §4.3). Until it lands, every concentration output is classified `screening_estimate` and no decision output may claim more confidence than the transport underneath it.

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

#### T-024 Field visualisation · DONE (record corrected 2026-09-19)
Files: `src/scentinel/ui/field_view.py`, `src/scentinel/core/post.py`
Acceptance met: `post.render_concentration_field()` renders the real OpenFOAM
cell field to PNG with sensor and hotspot overlays, and `FieldResultView`
provides the gas selector, statistics line, and colour-mapped view in the
results tab. The cut-plane and streamline function objects named in the original
task were not needed: `foamToVTK` already writes the 2D cell field that the view
renders directly.
Note: this task was carried as TODO while the code existed. Corrected so the
record matches the repository.

#### T-024a pyvista Plotter import race · DONE
Files: `src/scentinel/core/post.py`, `tests/ui/test_main_window.py`
Why: `pv.Plotter` goes through pyvista's module `__getattr__`, which imports
`pyvista.plotting` on first access. When the solver thread imports that submodule
concurrently, the lookup runs against a partially initialised module and raises
`AttributeError: module 'pyvista' has no attribute 'Plotter'`.
Change: import `Plotter` by name from the submodule, which is served from
`sys.modules`. A field-render failure is now logged as a warning and never aborts
`_finalize_run`, because rendering is a view of the run, not part of it — the
previous behaviour left a succeeded solve recorded as `incomplete`.
Acceptance: `test_a_field_render_failure_still_finalizes_the_run` passes.

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

## W — Waste Intelligence Layer

**Plan:** [superpowers/plans/2026-09-19-waste-intelligence.md](superpowers/plans/2026-09-19-waste-intelligence.md)
**Basis:** [gas-composition-basis.md](gas-composition-basis.md)

Why this phase exists: Scentinel answers *"what concentration does each sensor
see?"* but not *"what should we do with this waste?"* — the question the team is
actually asked. Four defects were measured, not inferred: the generation basis is
AP-42 landfill data driving a fresh-bin model; the organic-fraction scaling is
uncited and can exceed the physical CH₄ ceiling; `moisture_fraction` is a dead
input; and the RDF block produces byte-identical output for every waste type.

**Governing rule:** a value without a citation does not enter the model. Where no
cited value exists, the output states the gap rather than filling it.

### W0 — Composition and generation model

#### T-100 Waste composition model · TODO
Files: `src/scentinel/core/composition.py` (new), `tests/unit/test_composition.py` (new)
Change: `WasteComposition` with seven mass fractions (food, garden, paper, wood,
textile, diaper, inert), each carrying its Table HH-1 `DOC` and `k` range.
Preset compositions for the six existing streams so nothing regresses.
Acceptance: fractions sum to 1.0 ± 1e-6 and an invalid sum is rejected naming the
offending value; every preset's fractions match its cited source in the basis
document §3.1; a preset round-trips through `Project`.

#### T-101 Holding-time and phase model · TODO
Files: `src/scentinel/core/composition.py`, `tests/unit/test_composition.py`
Why: `age` is the parameter separating a truck bin (hours, aerobic, no CH₄) from
a landfill (years, anaerobic, 55% CH₄). AP-42 §2.4.4 defines four phases by time;
the app models none.
Change: `age_h` on the scenario; `phase()` returns I/II/III/IV from the AP-42
§2.4.4 description; the phase gates which gases are generated at all.
Acceptance: `age_h=8` → phase I, `age_h=8760` → phase IV; a phase-I batch
produces CH₄ below 0.1% of ultimate yield (the decay table in the basis document
§3.1 is the expected value).

#### T-102 Methane generation engine (Eq. HH-1) · TODO
Files: `src/scentinel/core/generation.py` (new), `tests/unit/test_generation.py` (new)
Why: the linear rule is uncited and can exceed the 55% physical ceiling.
Change: implement 40 CFR §98.343(a)(1) Equation HH-1 with `DOC_F = 0.5`,
`F = 0.5`, `MCF` from the stream type, and composition-weighted `DOC`/`k`. Cap
the CH₄ volume fraction at the AP-42 steady-state ceiling.
Acceptance: ultimate yield for DOC = 0.31 is 103.3 kg CH₄/Mg (basis document
§3.2); the 24-hour decay fraction is below 0.06% for every Table HH-1 `k`; CH₄
never exceeds 550 000 ppmv for any composition or age.

#### T-103 Replace linear scaling in the source path · TODO
Files: `src/scentinel/core/scenario.py`, `src/scentinel/core/casegen.py`,
`tests/unit/test_scenario.py`, `tests/unit/test_casegen.py`
Why: `auto_concentration_ppmv()` is the function producing the impossible 85% CH₄.
Change: route `auto` sources through `generation.py`; delete `ORGANIC_REFERENCE`,
`ORGANIC_SCALE_GASES`, and the linear rule outright — no alias, no fallback.
Acceptance: `green-waste` at its preset no longer yields 850 000 ppmv; every
generated source is traceable to HH-1 or a Table 2.4-1 row;
`grep -r ORGANIC_SCALE_GASES src/` returns nothing.

#### T-104 Make moisture a real input · TODO
Files: `src/scentinel/core/generation.py`, `src/scentinel/core/scenario.py`,
`tests/unit/test_generation.py`
Why: `moisture_fraction` is persisted, displayed, and never used — verified by
`inspect.getsource`. AP-42 p.2.4-5 states the decay rate depends on waste moisture.
Change: moisture selects `k` within its cited range and adjusts the dry-mass basis
for `DOC`. Use the table's own range endpoints and interpolate linearly between
them, stating that choice in the docstring; do not invent a curve.
Acceptance: two scenarios differing only in moisture produce different `k` and
therefore different generation; the mapping's endpoints match Table HH-1.

#### T-105 Manifest version 4 · TODO
Files: `src/scentinel/core/history.py`, `tests/unit/test_history.py`
Why: a version 3 manifest cannot say which composition produced its concentrations.
Change: bump `RUN_FORMAT_VERSION` to 4; record the seven fractions, `age_h`, the
derived phase, and the resolved `DOC`/`k` per material; reject version 3 rather
than misread it.
Acceptance: a version 3 manifest raises naming both versions; the new manifest
round-trips; `applied_physics` gains the generation inputs so a manifest cannot
claim a composition the engine did not use.

#### T-106 Extract fresh-waste VOC data · TODO — **research, blocks T-107**
Files: `docs/data/` (new artifacts), `docs/references.md`, `scripts/scrape_references.py`
Why: phase I has no cited composition in the repo. The basis document §5.1 names
three sources; none are extracted. Without this, phase I cannot be populated
honestly.
Change: extract and record, with retrieval metadata (canonical URL, UTC, artifact
SHA-256), from: Waste Manag. 2017 68:677-687 DOI `10.1016/j.wasman.2017.07.015`;
Statheropoulos et al. 2005 (Atmos. Environ.); NIOSH NMAM Method 3900 (analyte
list — method only, not values).
Acceptance: each extracted value carries a page/table reference and a rating; a
source that cannot be extracted is recorded as unavailable with the reason, and no
value is estimated in its place.

#### T-107 Phase-I gas set · TODO — blocked by T-106
Files: `src/scentinel/core/generation.py`, `src/scentinel/core/gas_data.py`,
`docs/references.md`
Change: derive the phase-I gas set from T-106: CO₂, H₂S, mercaptans, dimethyl
sulfide, and the measured VOC species. Offer CH₄ only above the phase threshold.
Acceptance: a phase-I scenario cannot select CH₄ (the checkbox is absent, not
merely disabled); CO₂ appears with a cited default; the gas list is a function of
`age_h`.

### W1 — Mass balance and yield

#### T-110 Batch mass balance · TODO
Files: `src/scentinel/core/massbalance.py` (new), `tests/unit/test_massbalance.py` (new)
Why: the expected output is tonnage per stream ("10 t in → 6.4 t RDF"). No mass
model exists today (`tonnage` has zero hits in `src/`).
Change: `Batch(tonnage_t, composition, moisture)` → per-stream mass. Moisture
leaves as a separate stream, not folded into the product.
Acceptance: streams sum to the input within 0.1%; zero tonnage raises rather than
returning zeros.

#### T-111 Route split fractions · TODO — **needs cited basis**
Files: `src/scentinel/core/massbalance.py`, `docs/references.md`
Why: how much of each material goes to RDF vs recycling vs composting is a
process property, not a physical constant.
Change: routing as an explicit, editable process parameter with a cited default
where one exists and an explicit `user input` provenance where one does not.
Never present an assumption as a citation.
Acceptance: each split fraction displays its provenance in the UI and records it
in the manifest.

#### T-112 Process-parameter sensitivity · TODO
Files: `src/scentinel/core/massbalance.py`, `src/scentinel/ui/`
Change: recompute the balance on parameter change and report the delta against the
previous setting, labelled a sensitivity, not a prediction.
Acceptance: changing one split fraction reports the tonnage delta for every stream
it touches, naming which parameter moved.

### W2 — Quality and suitability

#### T-120 RDF quality parameters · TODO — **partially blocked on lab data**
Files: `src/scentinel/core/quality.py` (new), `tests/unit/test_quality.py` (new)
Why: NCV, ash, and fuel-basis chlorine are what an offtaker buys; the basis
document §6.4 states they cannot be derived from the gas phase.
Change: three explicit input modes, never mixed — measured (provenance
`laboratory`), correlated (only with a cited correlation, or record its absence),
unknown (reported as needing laboratory data).
Acceptance: with no lab input the fields read "requires laboratory
characterisation" and no grade is claimed; with lab input they show the entered
values and provenance; no path produces a number with provenance `None`.

#### T-121 EN 15359 / ISO 21640 class assignment · TODO — blocked by T-120
Files: `src/scentinel/core/quality.py`, `docs/references.md`
Change: map NCV/Cl/ash to the standard's class grid only when all three are
measured or correlated with a citation; otherwise state which input is missing.
Acceptance: a complete input set yields a class and the standard clause; an
incomplete set names the missing parameter and yields no class.

#### T-122 Fix the decorative RDF block · TODO
Files: `src/scentinel/core/assessment.py`, `src/scentinel/ui/results_panel.py`,
`tests/unit/test_assessment.py`
Why: measured — `halogen_load()` takes no `scenario`, so `mixed-msw`,
`rdf-feedstock`, and `dry-recyclables` produce byte-identical output.
Change: make halogen and sulfur loading a function of composition and the selected
trace species, scaled by batch tonnage. If the composition cannot support it, say so.
Acceptance: two compositions produce different loading; the value changes when
tonnage changes; the panel text names the composition it used.

#### T-123 Suitability scoring · TODO
Files: `src/scentinel/core/suitability.py` (new), `tests/unit/test_suitability.py` (new)
Why: scores per route were requested (RDF 87%, recycling 42%, composting 18%).
Change: score each route from composition, moisture, and quality parameters; each
score carries its inputs and the rule that produced it. A score missing inputs is
`insufficient_data`, never a number.
Acceptance: a dry high-paper batch scores higher for RDF than a wet food-heavy
one; a batch missing a required parameter yields `insufficient_data`; every score
exposes its rule.

### W3 — Interpretation, forecasting, recommendation

#### T-130 Sensor interpretation layer · TODO
Files: `src/scentinel/core/interpret.py` (new), `tests/unit/test_interpret.py` (new)
Change: map measured and simulated values to stated interpretations with their
basis. An interpretation names the threshold or mechanism it rests on and never
asserts a cause the data cannot show.
Acceptance: a TVOC above the configured limit produces a stated interpretation
citing the limit; a below-detection value produces "no exposure detected", not a
trend claim; interpretations are translatable (en/id).

#### T-131 Batch history persistence · TODO
Files: `src/scentinel/core/batchhistory.py` (new), `tests/unit/test_batchhistory.py` (new)
Change: append-only batch records beside the project, same discipline as
`history.py` (immutable, never-reused ids, strict load). Reuse the manifest
patterns rather than inventing a second scheme.
Acceptance: records survive a restart; a corrupt record is reported individually;
ordering is stable.

#### T-132 Tonnage forecasting · TODO — blocked by T-131
Files: `src/scentinel/core/forecast.py` (new), `tests/unit/test_forecast.py` (new)
Change: forecast from recorded history with an explicitly named method and its
error. With too few records, report that rather than extrapolating from noise.
Acceptance: a synthetic linear series is recovered within a stated tolerance;
fewer than N records yields `insufficient_history`; method and sample count appear
in the output.

#### T-133 Decision recommendation · TODO — blocked by T-123, T-130
Files: `src/scentinel/core/recommend.py` (new), `tests/unit/test_recommend.py` (new)
Why: the user called this the most important output — e.g. "recommended for RDF
after moisture reduction".
Change: rank routes by suitability score and produce one recommendation with its
reason and caveats. Refuse to recommend when inputs are insufficient, and carry
the screening caveat while mesh independence fails.
Acceptance: the recommendation names the route, the reason, and every input it
rested on; an insufficient batch yields "not enough information" plus the missing
list; the text never presents a screening estimate as a measurement.

### W4 — UI for the decision flow

#### T-140 Characterization panel · TODO
Files: `src/scentinel/ui/characterization_panel.py` (new), `src/scentinel/ui/home_window.py`
Change: a panel for composition, age, tonnage, and moisture emitting a `Batch`,
with the derived phase and generation preview shown live.
Acceptance: editing a fraction updates the preview without a solve; the panel
emits a valid `Batch` or names the invalid field.

#### T-141 Decision panel · TODO — blocked by T-133
Files: `src/scentinel/ui/decision_panel.py` (new)
Change: one panel showing characterization → suitability → yield → quality →
recommendation, each row traceable to its inputs.
Acceptance: every displayed number carries its provenance or its "needs lab"
state; nothing shows a placeholder that looks like a result.

#### T-142 Scenario comparison · TODO
Files: `src/scentinel/ui/comparison_view.py` (new), `tests/ui/test_comparison_view.py` (new)
Change: compare recorded runs and batches side by side with a difference column,
consuming the strict `load_run()` contract and refusing to compare runs whose
`case_input_digest` differs unless the mismatch is explicit; never difference by
`ventilation.requested_on` while `ventilation.modelled` is false.
Acceptance: a difference column matches the underlying values; a digest mismatch
blocks the comparison; every compared row shows its quality classification.
Note: supersedes T-031, which covered runs only.

#### T-143 Layout redesign · TODO
Files: `src/scentinel/ui/theme.py`, `src/scentinel/ui/home_window.py`, locale files
Why: the current shell was built around a CFD form; the user explicitly permitted
a redesign.
Change: restructure the shell around the decision flow, keeping the top toolbar
and the single shared project. Every user-visible string goes through
`Translator.t` with keys in both locales.
Acceptance: the flow is navigable end to end without a solve; the offscreen UI
suite passes; no string is hardcoded.

### W — prerequisite gates

#### T-150 Mesh-independence gate for W output · BLOCKED on T-021
Why: no output from the waste layer may claim more confidence than the transport
underneath it. Until T-021 passes, every concentration-derived figure stays
`screening_estimate`.
Acceptance: the decision output carries the screening caveat, asserted by test.

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
