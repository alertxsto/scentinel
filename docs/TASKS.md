# Scentinel — Task Breakdown

**Version:** 0.2.2 · **Last updated:** 2026-09-19

Every task with its status, the files it touches, and its acceptance test. Phase
context is in [ROADMAP.md](ROADMAP.md).

> **Active program:** the 20-phase hardening program in
> [superpowers/plans/2026-09-19-hardening-program.md](superpowers/plans/2026-09-19-hardening-program.md)
> (tasks T-200…T-294) is the work queue. Its tasks absorb T-122 (→ T-212/T-250),
> T-141 (→ T-292), T-143 (→ T-291/T-292), and rework T-020/T-021/T-022/T-120/
> T-121/T-130/T-131/T-132/T-142/T-106/T-107. Status of each program task is
> tracked here as it lands; the entries below remain the detailed record of what
> shipped in 0.2.x.

Legend: **DONE** · **TODO** · **BLOCKED**

---

## Program tasks (2026-09-19 hardening program)

#### T-200 Baseline freeze · DONE — 2026-09-19
Files: `docs/ROADMAP.md`, `docs/TASKS.md`, `docs/superpowers/plans/2026-09-19-hardening-program.md`
Acceptance met: the program plan exists with every task contract; the docs
describe the repository as it is (no stale status or number); tag
`v0.2.2-audit` marks the baseline commit.
Note: scope is frozen — new work enters only through an explicit edit to the
program plan.

### Phase 2 — Gas generation definitions

#### T-220 Three generation quantities · DONE — 2026-09-19
Files: `src/scentinel/core/generation.py`, `tests/unit/test_generation.py`
Acceptance met: `ultimate_ch4_kg` (and `ultimate_ch4_kg_per_t`),
`ch4_cumulative_kg`/`co2_cumulative_kg`, and
`ch4_rate_kg_per_h`/`co2_rate_kg_per_h` are separate outputs; the rate is the
analytical derivative of the cumulative mass (asserted numerically within
1e-6); cumulative is monotone in age; carbon closes between CH4 and CO2 within
0.2%.

#### T-221 UI truth-in-labelling · DONE — 2026-09-19
Files: `src/scentinel/ui/batch_panel.py`, `src/scentinel/core/pipeline.py`,
`resources/locales/{en,id}.json`, `tests/ui/test_batch_panel.py`,
`tests/unit/test_pipeline.py`
Acceptance met: the `gas_now` readout is replaced by `gas_cumulative` (kg) and
`gas_rate` (kg/h) with units in both; the summary states both quantities; no
string describes cumulative mass as "produced now".

#### T-222 Continuity across age · DONE — 2026-09-19
Files: `tests/unit/test_generation.py`
Acceptance met: generation is continuous at 48 h, 90 d, and 365 d (the step
across a boundary equals the rate times the interval); no CH4 step remains.

#### T-223 Phase is interpretation, not a switch · DONE — 2026-09-19
Files: `src/scentinel/core/generation.py`, `src/scentinel/core/scenario.py`,
`tests/unit/test_generation.py`, `tests/unit/test_scenario.py`
Acceptance met: monkeypatching `phase_for` changes no generation number; the
II→III CH4 jump is gone; the generated gas is the regulation's `F = 0.5` split
(40 CFR 98.343 Table HH-1) at every age, so a fresh load reads ~500 000 ppmv
CH4 by volume and the age moves the rate, not the share. The AP-42 55/40/5 mix
is retained as a ceiling/comparison only.
Note: this is a deliberate change of the mixture basis from AP-42 55/40/5 to
the regulation's F = 0.5, agreed before implementation. The CO2 phase-I refusal
from the previous session is retired — the CO2 share is now cited (F basis).

#### T-224 Manifest v6 · DONE — 2026-09-19
Files: `src/scentinel/core/history.py`, `tests/unit/test_history.py`
Acceptance met: `RUN_FORMAT_VERSION` is 5 (the program's "v6" is the fifth
bump in this repository's numbering — see note); the scenario generation block
records ultimate, cumulative, and rate separately; a version 4 manifest is
rejected naming both versions.
Note: the master program expected Phase 1 to land manifest v5 first. Gas work
ran first, so this is v5 and Phase 1's material composition will be v6. The
numbering is by repository sequence, not by program label.

### Phase 3 — Phase model

#### T-230 Cutoffs as assumptions · DONE — 2026-09-19
Files: `src/scentinel/core/composition.py`, `tests/unit/test_composition.py`
Acceptance met: `PhaseModel(boundaries_h, provenance, basis, uncertainty)` and
`DEFAULT_PHASE_MODEL` carry the 48 h / 90 d / 365 d boundaries with provenance
`model assumption`; `phase_for()` takes the model as a parameter, so a custom
model moves the boundaries and no code path treats them as measured.

#### T-231 Stage separated from decay · DONE — 2026-09-19
Files: `src/scentinel/core/composition.py`, `src/scentinel/core/generation.py`,
`tests/unit/test_generation.py`
Acceptance met: `interpret_phase()` returns a `PhaseInterpretation` with
source, provenance, applicability, and uncertainty; `Generation` carries it;
monkeypatching `phase_for` changes no generation number (Phase 2 test,
re-asserted). Phase I's applicability states that HH-1 is an anaerobic model
extrapolated into the aerobic phase.

#### T-232 Phase provenance in output · DONE — 2026-09-19
Files: `src/scentinel/core/history.py`, `src/scentinel/ui/batch_panel.py`,
`resources/locales/{en,id}.json`, `tests/unit/test_history.py`,
`tests/ui/test_batch_panel.py`
Acceptance met: `RUN_FORMAT_VERSION` is 6; the generation block records
`phase_provenance`, `phase_applicability`, `phase_uncertainty`; a version 5
manifest is rejected naming both; the batch panel's phase readout states the
applicability.

### Phase 4 — Fresh-waste model

#### T-106 Extract fresh-waste VOC data · DONE (partial — see note) — 2026-09-19
Files: `docs/data/fresh_waste_references.json` (new),
`docs/references/statheropoulos_2005_urban_bins.txt` (new),
`docs/references.md`, `docs/gas-composition-basis.md`,
`tests/unit/test_fresh_waste_data.py` (new)
Acceptance met: the artifact records a status for each of the three named
sources with retrieval metadata; Statheropoulos 2005 is extracted with units and
references (median µg/m³); the two inaccessible sources are recorded
`unavailable` with the HTTP reason, and no value is estimated in their place.
Note: the primary source (Waste Manag. 2017) is paywalled and NIOSH 3900 returns
403; the extraction is partial by access, not by effort. The Statheropoulos
values are mass concentrations and have not been converted to a source strength.

#### T-107 Phase-I gas set · DONE — 2026-09-19
Files: `src/scentinel/core/gas_data.py`, `src/scentinel/ui/setup_panel.py`,
`src/scentinel/ui/main_window.py`, `src/scentinel/ui/workspace.py`,
`tests/unit/test_gas_data.py`, `tests/ui/test_setup_panel.py`,
`tests/ui/test_setup_panel_layout.py`
Acceptance met: `GasApplicability(phases, source, uncertainty)` and
`offered_gases(age_h)` gate the catalogue by the age's phase; methane is not
offered for a fresh load (its row is hidden, not disabled) and reappears when
the load ages; every offered gas carries a source and an uncertainty; the setup
panel filters its rows by holding time and `gas_sources()` cannot leak a
non-applicable gas. The setup dock's floor is preserved so hiding a row cannot
collapse the panel.
Note: CO2 is a generated gas, not a selectable catalogue source, so it is not in
`offered_gases`; it is reported as a generated mass/share.

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

#### T-056 Sandbox publishes its readings · SUPERSEDED (record corrected 2026-09-19)
Files: `src/scentinel/ui/sensor_lab.py`, `tests/ui/test_main_window.py`
Original claim: the replay writes into the same results table a solve fills
(`TVOC`, `GROUND_TRUTH`, `INTERFERENCE`); reset clears both the state and the
table.
**Correction:** `sensor_sandbox.py` no longer exists and the replay updates the
lab's own telemetry, not the results table. `ResultsPanel.set_virtual_sensor_summary()`
has no caller, and the TVOC summary row reads "requires sensor hardware" for
every run.
What is true today: the lab reads the project's sensors and the latest run
readings, and `_on_run_finished` pushes a finished solve's readings into it via
the `results_changed` signal. Resurrecting the table-publishing behaviour is open
work, tracked with T-140/T-141.

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
Note: this changes the plan from the design spec's §4.2/§4.3 `fixedValue`
concentration boundary, which is what shipped. The spec's gas-source field
comment left the basis open (`kg/m2/s or ppm basis`); T-020 resolves it toward a
flux. Until it lands, every concentration output is classified
`screening_estimate` and no decision output may claim more confidence than the
transport underneath it.

#### T-021 Mesh-independence gate · BLOCKED on T-020
Files: `tests/verification/test_mesh_independence.py`
Current state: the test measures the deviation and asserts it is *still* above 10%, so it fails loudly once the fix lands and forces a convergence assertion to replace it.
Acceptance: asserts <10% and the trend is monotone with refinement.

### Phase 5 — CFD mass-flux source

#### T-020 Mass-flux source term · PARTIAL — 2026-09-19
Files: `src/scentinel/core/geometry.py`, `src/scentinel/core/casegen.py`,
`src/scentinel/core/history.py`, `src/scentinel/core/project.py`,
`src/scentinel/ui/setup_panel.py`, `tests/unit/test_geometry.py`,
`tests/unit/test_casegen.py`, `tests/unit/test_history.py`,
`tests/unit/test_project.py`, `tests/ui/test_setup_panel.py`
Why: the `fixedValue` concentration boundary made sampled values depend on the
first cell height, so mesh independence failed and did not converge.
Change: the source is now an emission mass flux. `BinGeometry.width_m` gives the
emitting area (mound profile × width); `casegen.emission_rate_kg_per_s` derives
the batch's rate from the generation model; `emission_flux_kg_per_m2_s` spreads
it over the area; `source_gradient_ppmv_per_m` converts it to the `fixedGradient`
the scalar boundary imposes. Project format is v2 (adds `width_m`, v1 migrates);
manifest is v7 (records `emitting_area_m2` and `emission_flux_kg_per_m2_s`).
Acceptance met for the mechanism: the boundary is a flux, tonnage and age move
it, and the mesh deviation fell from ~87% to ~63% (worst probe, 2026-09-19).
**Not met for the gate:** probe deviation is still >10%. Measured root cause:
the k-epsilon velocity field itself differs between meshes (S1: 0.236 vs
0.116 m/s) and is not mesh-converged at 431/907 cells; the scalar, carried with
molecular diffusivity only, follows it. Raising molecular D made it worse, so
the remaining error is the missing turbulent scalar transport (T-240) and the
unresolved velocity field (T-021), not the source boundary. The gate test
remains asserted-as-failing with this evidence recorded.
Note: this changes the design spec's §4.2/§4.3 `fixedValue` concentration
boundary; the spec's gas-source field comment left the basis open
(`kg/m2/s or ppm basis`), and this resolves it toward a flux.

### Phase 6 — Turbulent scalar transport

#### T-240 Turbulent scalar diffusivity · DONE (mechanism) — 2026-09-19
Files: `src/scentinel/core/casegen.py`, `src/scentinel/core/history.py`,
`tests/unit/test_casegen.py`, `tests/unit/test_history.py`,
`tests/verification/test_mesh_independence.py`
Why: the scalar was carried with molecular diffusivity alone, so it followed
streamlines the momentum solver resolves only partly at these cell counts.
Change: `scalarTransport` now writes `alphaD`/`alphaDt` and omits both `D` and
`nut`, which is the only form that makes OpenFOAM use its
`alphaD*nu + alphaDt*nut` branch (verified against the v2512 `scalarTransport.C`
source in the container). `TURBULENT_SCHMIDT_NUMBER = 0.7`, labelled a model
assumption with its RANS basis. Manifest v8 records the number and provenance.
Acceptance met for the mechanism: `D_eff = D + nu_t/Sc_t` reaches the case, and
the worst-probe mesh deviation fell from ~63% to ~19%.
**Not met for the gate:** still >10% and not monotone. Measured cause: the
k-epsilon velocity field is itself mesh-dependent (S1: 0.236 vs 0.116 m/s).
Lowering Sc_t shrinks the deviation but outside the cited 0.7–0.9 range; Sc_t
stays 0.7 rather than being tuned to pass.
Note: `tests/verification/test_analytical_benchmarks.py`'s bin-probe test now
uses an in-air probe; its old "floor" probe at (0.5, 0.2) was buried in the
mound, which is the sensor-containment defect T-242 addresses.

#### T-021 Mesh-independence gate · BLOCKED on a mesh-converged velocity field
Files: `tests/verification/test_mesh_independence.py`
Current state: the test measures the deviation and asserts it is *still* above
10%, recording the measured cause and the two reworks that reduced it
(87% → 63% → 19%).
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

#### T-100 Waste composition model · DONE (record corrected 2026-09-19)
Files: `src/scentinel/core/composition.py`, `tests/unit/test_composition.py`
Acceptance met: `WasteComposition` carries the eight Table HH-1 fractions, each
with its cited `DOC` and `k` range; the six stream presets are normalised and
round-trip through `Project`; an invalid sum raises naming the gap.
Note: this task was carried as TODO while the code existed. Corrected so the
record matches the repository.

#### T-101 Holding-time and phase model · DONE (record corrected 2026-09-19)
Files: `src/scentinel/core/composition.py`, `tests/unit/test_composition.py`
Acceptance met: `Scenario.age_h` selects phase I–IV via `phase_for()`, and
`PHASE_GASES` gates which gases a phase can produce; a fresh load reports no
methane. Note: the phase boundaries (48 h, 90 d, 1 yr) are the AP-42 narrative
expressed as a decision rule, stated as such in the module.

#### T-102 Methane generation engine (Eq. HH-1) · DONE (record corrected 2026-09-19)
Files: `src/scentinel/core/generation.py`, `tests/unit/test_generation.py`
Acceptance met: ultimate yield for DOC = 0.31 is 103.33 kg CH₄/t; the 24-hour
decay fraction is below 0.06% for every Table HH-1 `k`; the methane volume
fraction is capped by the cited 55% steady-state ceiling and asserted, not
clamped. Note: the pre-methanogenic CO₂ **volume share** is refused as uncited
(`scenario.generated_source_ppmv`); the CO₂ mass stays in the batch report.

#### T-103 Replace linear scaling in the source path · DONE (record corrected 2026-09-19)
Files: `src/scentinel/core/scenario.py`, `src/scentinel/core/casegen.py`,
`tests/unit/test_scenario.py`, `tests/unit/test_casegen.py`
Acceptance met: `auto` sources route through `generation.py`; `ORGANIC_REFERENCE`,
`ORGANIC_SCALE_GASES`, and the linear rule are deleted; `green-waste` reports the
cited 55% share instead of 85%.

#### T-104 Make moisture a real input · DONE — corrected 2026-09-19
Files: `src/scentinel/core/generation.py`, `src/scentinel/core/composition.py`,
`tests/unit/test_generation.py`, `tests/unit/test_scenario.py`
Change: moisture selects `k` within the Table HH-1 range (endpoints
`DRY_REFERENCE=0.15`, `WET_REFERENCE=0.65`, linear interpolation between), which
is this model's stated choice — the table's own footnote c governs
evapotranspiration vs precipitation, not moisture directly.
Acceptance met for the *mass*: two scenarios differing only in moisture produce
different `k` and different gas mass (2.16× on the measured example).
**Correction:** the original acceptance test asserted the moisture *source
concentration* moved, which passed only on float noise (549999.9999999999 vs
550000.0). The steady-state share is cited at 55% and is not a moisture
function; the honest assertion is on `ch4_kg`, and the test now says so.

#### T-105 Manifest version 4 · DONE — 2026-09-19
Files: `src/scentinel/core/history.py`, `tests/unit/test_history.py`
Change: `RUN_FORMAT_VERSION` is 4; the scenario block records `tonnage_t`, the
eight composition fractions, and a `generation` block (phase, DOC, k,
decay_fraction, methane_fraction, ch4_kg, co2_kg) captured from the model at
reservation time. Version 3 manifests are rejected rather than misread.
Acceptance met: a version 3 manifest raises naming the expected version; the new
manifest round-trips; `_decode_composition` re-validates through
`WasteComposition`, so a hand-edited manifest cannot hold a composition the
model would refuse.

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

#### T-110 Batch mass balance · DONE (record corrected 2026-09-19)
Files: `src/scentinel/core/massbalance.py`, `tests/unit/test_massbalance.py`
Acceptance met: moisture leaves as its own stream; every material is routed and
the total closes on the input; `yield_fraction()` reports each stream's share.
Correction: the original acceptance said "zero tonnage raises". Zero is a valid
empty batch and returns zeros; *negative* tonnage raises. The test asserts the
behaviour the model actually guarantees.

#### T-111 Route split fractions · DONE — corrected 2026-09-19
Files: `src/scentinel/core/massbalance.py`, `docs/references.md`
Acceptance met: routing is an explicit parameter with per-material provenance;
defaults are labelled `user assumption`.
**Correction:** the first implementation labelled *any* caller-supplied routing
table `cited`. Supplying a table is not evidence that anyone published it, so the
default label is now `user assumption` in every case; only an explicit
`provenance` mapping can mark a material `cited`.
Remaining gap: the fractions are still model assumptions — no source in the
repository supports a specific split — so they remain labelled as such rather
than presented as citations.

#### T-112 Process-parameter sensitivity · TODO
Files: `src/scentinel/core/massbalance.py`, `src/scentinel/ui/`
Change: recompute the balance on parameter change and report the delta against the
previous setting, labelled a sensitivity, not a prediction.
Acceptance: changing one split fraction reports the tonnage delta for every stream
it touches, naming which parameter moved.

### W2 — Quality and suitability

#### T-120 RDF quality parameters · TODO — **partially blocked on lab data**
Files: `src/scentinel/core/quality.py` (new), `tests/unit/test_quality.py` (new)
Status note: `suitability.QualityInputs` and `fuel_grade()` already implement the
three-mode contract (measured / correlated / unavailable) and refuse to invent a
class; a dedicated `quality.py` module is still the planned home for it.
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

#### T-122 Fix the decorative RDF block · TODO — still open
Files: `src/scentinel/core/assessment.py`, `src/scentinel/ui/results_panel.py`,
`tests/unit/test_assessment.py`
Why: measured — `halogen_load()` takes no `scenario`, so `mixed-msw`,
`rdf-feedstock`, and `dry-recyclables` produce byte-identical output.
Change: make halogen and sulfur loading a function of composition and the selected
trace species, scaled by batch tonnage. If the composition cannot support it, say so.
Acceptance: two compositions produce different loading; the value changes when
tonnage changes; the panel text names the composition it used.
Note: `evaluate()` now accepts `moisture_fraction` and the summary labels the
moisture row "waste stream input", but the halogen block itself is unchanged.

#### T-123 Suitability scoring · DONE (record corrected 2026-09-19)
Files: `src/scentinel/core/suitability.py`, `tests/unit/test_suitability.py`
Acceptance met: each route has a stated rule over named inputs, exposed with the
score; a route whose inputs are absent is reported rather than given a number;
a dry high-paper batch outranks a wet food-heavy one for RDF.
Note: the scores are *stated heuristics*, not standard classifications, and the
module says so in its own notes. They are not EN 15359 / ISO 21640 classes.

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

#### T-133 Decision recommendation · DONE — 2026-09-19
Files: `src/scentinel/core/recommend.py`, `tests/unit/test_recommend.py`
Acceptance met: one recommendation naming the route, the rule behind its score,
the projected yield, and every input it rested on; an unscoreable batch yields
"not enough information" plus the missing list; a zero-tonnage batch is refused;
the screening caveat is carried by default and dropping it is a deliberate
argument (`screening=False`).
Note: a below-threshold best route is still named — a load that physically
exists has to go somewhere — with the shortfall stated as a caveat.

### W4 — UI for the decision flow

#### T-140 Characterization panel · DONE (record corrected 2026-09-19)
Files: `src/scentinel/ui/batch_panel.py`, `src/scentinel/ui/main_window.py`,
`tests/ui/test_batch_panel.py`, `tests/ui/test_main_window.py`
Acceptance met: `BatchPanel` carries the composition fractions, age, tonnage, and
moisture, and recomputes the whole chain live without a solve; it emits
`assessed(BatchAssessment)`, and the window mirrors those inputs into the
scenario so the run and the assessment describe the same batch.
Note: the module was planned as `characterization_panel.py`; the shipped name is
`batch_panel.py`.

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
