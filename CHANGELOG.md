# Changelog

All notable changes to Scentinel are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Two things are worth knowing before reading:

- **`screening_estimate` is not a formality.** Absolute concentrations are not
  mesh-converged (latest containing-cell deviation: 266.29% under a 2×
  refinement), so concentration-derived figures remain screening outputs until
  that gate passes.
- **A value without a citation does not enter the model.** Where no cited value
  exists, the output states the gap instead of filling it. This is why several
  fields read "requires laboratory characterisation" rather than showing a number.

---

## [Unreleased]

## [0.2.3] — 2026-09-21

### Added

- 20-phase hardening program
  (`docs/superpowers/plans/2026-09-19-hardening-program.md`, tasks
  T-200…T-294) with the baseline tag `v0.2.2-audit`. Scope is frozen until the
  program completes; each phase gets a bite-sized execution plan at kickoff.

### Changed

- **Gas generation is one continuous curve.** Phase labels no longer switch
  methane on and off. Equation HH-1 uses the cited, measurement-replaceable
  methane default `F = 0.5`; the matching CO₂ split is explicitly a model
  assumption. AP-42 55/40/5 remains a mature-landfill comparison only.
- **Ultimate, cumulative, and rate are separate quantities.** A batch reports
  potential, gas produced by its recorded age, and instantaneous generation
  rate. Holding time moves rate and mass, not the modelled volume share.
- **Manifest format 10.** Run records include convergence evidence and bin
  width; old schemas are rejected naming the expected version. Project format
  2 persists width. Phase 1 material taxonomy remains explicitly deferred.

### Fixed

- Manual CH₄/CO₂ source entries now control the emitted flux instead of being
  overwritten by generated-gas shares.
- Solver residuals use numeric time ordering, compare the actual case targets,
  and treat missing fields as `not_evaluated`; solver failures cannot be
  relabelled converged.
- Fresh loads expose only the supported gas allow-list, while aged loads retain
  the full catalogue and unsupported fresh species state the evidence gap.
- Bin width is editable, persisted, and used in emission area and flux.
- **Linux release packages now include their Python runtime.** The previous
  packages copied a virtual environment whose interpreter was still an absolute
  symlink into the GitHub Actions tool cache. It could launch only when a user
  manually substituted another interpreter, and native extensions such as
  NumPy then failed when that interpreter's CPython ABI differed. Linux builds
  now use a PyInstaller one-directory bundle and execute an artifact-level
  native dependency smoke test before `.deb`, `.rpm`, or `.tar.gz` creation.
- Opening a project no longer aborts when its run directory contains a manifest
  from an older, incompatible history format. The project opens normally with
  empty results; strict history APIs continue to reject the obsolete manifest.


### Phase 3 — phase model

- The 48 h / 90 d / 365 d decomposition boundaries are now an explicit
  `PhaseModel` value object with provenance `model assumption`, its AP-42
  narrative basis, and an uncertainty note — not three bare numbers.
- `interpret_phase()` separates the phase *stage* (an interpretation of age)
  from the continuous decay math, and states each phase's applicability: phase I
  records that the anaerobic HH-1 model is extrapolated into the aerobic phase,
  so the output no longer presents the extrapolation as exact.
- **Manifest format 6** records `phase_provenance`, `phase_applicability`, and
  `phase_uncertainty`; version 5 manifests are rejected naming both versions.
  The batch panel's phase readout states the applicability.

### Audit fix — the source flux was 10^6 too high, and alphaD discarded each gas's diffusivity

Two defects in the Phase 5/6 source were found by auditing the units against
the OpenFOAM source and fixed:

- **`source_gradient` carried a spurious `1e6`.** The transported scalar is a
  volume *fraction* (dimensionless): `resolve_sources` returns fractions, the
  old source boundary wrote a fraction, and `post` multiplies by `1e6` only for
  display. The gradient multiplied the fraction flux by `1e6`, inflating the
  imposed flux a million-fold and producing sampled values above 1 (CO read
  2.7 as a "fraction"). The function is now `source_gradient` in fraction/m,
  and `gradient * D` returns the intended `J * (Vm/MW)`. A verification test
  pins `gradient * D_gas == fraction flux`.
- **`alphaD = 1` made every gas diffuse at air's viscosity.** OpenFOAM's
  `scalarTransport` computes `D = alphaD*nu + alphaDt*nut`; `alphaD` multiplies
  the *kinematic viscosity*, so a constant `1` replaced each gas's
  Fuller-Schettler-Giddings diffusivity with `nu_air` — a −20% (CO) to −29%
  (CH4) flux error. `alphaD` is now per gas, `D_gas / nu_air`, so the molecular
  term is the gas's own diffusivity. The manifest already recorded the real
  `scalar_diffusivity_m2_s` per gas, so it now matches the case.
- New verification benchmark: the `alphaD` path on a 1D duct reproduces the
  exponential profile within 5.5%, proving `alphaD` multiplies `nu`.
- The bin-probe benchmark's physical bound (`value < 1`) is restored; it was
  briefly dropped while the `1e6` defect was mistaken for a sampling issue.

With the corrected source, the units and imposed flux are physical. Absolute
near-mound probe values remain resolution-limited; containing-cell sampling
later exposed sign-changing numerical undershoot.

### Phase 7 — CFD verification gates

- OpenFOAM v2512 `solverInfo` replaces the nonexistent `residuals`
  functionObject. Manifest format v9 persists whether residual targets were
  met, plus the reason; exit code 0 alone is never treated as convergence.
- Sensor sampling uses `find_containing_cell`, never nearest-cell snapping.
  Placement and sampling reject invalid probes with a reason; a rejected probe
  is persisted as a failed run rather than leaving an incomplete manifest.
- Per-gas `surfaceFieldValue weightedSum(C, phi)` automates mass balance. The
  solved gate closes at 1.4245% (<5%). The analytic source integrates over the
  2D computational patch (`profile length × slab thickness`), not physical bin
  width.
- The mesh gate remains blocked. Correct containing-cell sampling measures
  266.29% because S3 changes sign at the scalar noise floor; velocity magnitude
  independently changes by up to 30.84%. `Sc_t` remains 0.7 and was not tuned.

### Phase 6 — turbulent scalar transport

- **The passive scalars are carried with `D + ν_t/Sc_t`, not molecular `D`
  alone.** `scalarTransport` writes `alphaD`/`alphaDt` and omits both `D` and
  `nut`, the only form that makes OpenFOAM use its `alphaD·ν + alphaDt·ν_t`
  branch (verified against the v2512 source in the container).
- `TURBULENT_SCHMIDT_NUMBER = 0.7`, labelled a **model assumption** with its
  RANS basis (0.7–0.9 range); it is not measured for this geometry. Manifest
  format v8 records it and its provenance; v7 is rejected naming both.
- The old nearest-cell mesh metric fell from ~63% to ~19%, but the <10% gate is
  still missed. Measured cause: the k-epsilon
  velocity field is itself mesh-dependent at these cell counts. Lowering Sc_t
  would shrink the deviation further but outside the cited range, so it was not
  tuned to pass. The remaining fix is a mesh-converged velocity field (T-021).
- The bin-probe benchmark now samples an in-air point; its old "floor" probe was
  buried in the mound (the sensor-containment defect T-242 covers).

### Phase 5 — CFD mass-flux source

- **The source is now an emission mass flux, not a surface concentration.**
  `BinGeometry.width_m` (default 2.4 m) gives the emitting area; the batch's
  generation rate is spread over it to give kg/m²/s; the scalar source patch
  imposes that flux as a `fixedGradient`. The near-wall flux is now independent
  of the first cell height, and tonnage, age, and bin width move the field.
- Project format v2 adds `width_m`; a v1 file loads with the default rather
  than being rejected. Manifest format v7 records `emitting_area_m2` and
  `emission_flux_kg_per_m2_s` per gas; v6 is rejected naming both.
- The setup panel's derived readout tooltip states the emission flux the case
  will impose.
- **Mesh independence is still not met.** The flux boundary cut the worst-probe
  deviation from ~87% to ~63%, but the gate is >10%. Measured cause: the
  k-epsilon velocity field is not mesh-converged at 431/907 cells and differs
  between meshes, and the scalar is carried with molecular diffusivity only.
  The remaining fix is turbulent scalar transport (Phase 6) plus a converged
  velocity field, not the source boundary. The gate test records this and
  remains asserted-as-failing.

### Phase 4 — fresh-waste model

- **Gas applicability is explicit.** Each catalogue gas carries
  `GasApplicability(phases, source, uncertainty)`; the AP-42 Table 2.4-1 values
  are labelled as mature-landfill measurements, so using them for a fresh
  aerobic load is stated as an extrapolation rather than presented as exact.
- **The gas list follows holding time.** A fresh load no longer offers methane
  (its row is hidden, not merely disabled); an aged load offers it again. The
  setup panel filters its rows by phase, and `gas_sources()` cannot leak a
  non-applicable gas.
- **Fresh-waste research artifact** (`docs/data/fresh_waste_references.json`):
  Statheropoulos 2005 extracted (median bin-VOC mass concentrations with
  units); Waste Management 2017 and NIOSH 3900 recorded `unavailable` with the
  HTTP reason. No value was estimated to fill the gap.
- The setup dock's declared width floor is preserved by the layout pass, so
  hiding a gas row cannot collapse the panel and clip the remaining controls.

## [0.2.2] — 2026-09-19

Audit fixes: each item below was reproduced before it was fixed, and each fix
has a test that fails on the old behaviour.

### Fixed

- **Cancellation and timeouts ignored silent processes.** `run_case()` checked
  the cancel flag only between output lines, so a solver that logs to a file —
  which the pipeline does — ran to completion before a cancel was noticed. A
  reader thread now pumps output and the wait polls, so cancel and `timeout_s`
  both take effect immediately. A cancelled process is reported with the `-2`
  sentinel rather than its raw `-15`, so it is recorded `cancelled`, not `failed`.
- **`succeeded` was not enforced against its own execution block.** The schema
  promised "exited 0 and every sensor was sampled" but only checked the second
  half, so an API caller (or a hand-edited manifest) could persist a success
  with `exit_code: 13` and `error: "solver failed"`. Both `finish_run()` and
  `load_run()` now reject a succeeded record with a non-zero exit code, an error,
  or a failed stage.
- **The sensor lab never received a finished run's readings.** `_on_run_finished`
  updated the results table but not the lab, so a replay kept using the fallback
  or an older run. The results panel now emits `results_changed` and the window
  forwards it, so the lab always evaluates the readings on screen.
- **`mesh_cells` was eight times the real cell count.** The mesh counter summed
  `len(node_tags)` from `getElements` instead of `len(element_tags)`, so a file
  with 431 cells was reported as 3444 and the inflated number was persisted as
  the run's mesh-size evidence.
- **Auto CH₄ cited a value it did not use.** The generated source resolved to
  550 000 ppmv but carried `gas_data.citation("CH4")` — "500000 ppmv — EPA LMOP".
  Generated sources now cite the generation model and state the resolved value;
  trace species keep their table citation.
- **The batch panel and the run could describe different waste.**
  `_on_batch_assessed` only stashed the assessment, so editing the fractions and
  pressing Run solved the setup panel's preset instead. The panel's composition,
  tonnage, age, moisture, and stream are now mirrored into the scenario — in
  both directions — and manifest format 4 records them.
- **Custom routing was labelled `cited`.** Any caller-supplied routing table was
  persisted as a sourced value. Supplying a table is not evidence that anyone
  published it; the default is now `user assumption`, and only an explicit
  `provenance` mapping can mark a material cited.
- **A gas could interfere with itself.** When VOC was absent the lab promoted the
  first remaining gas to ground truth and then counted it again in the
  interference sum, inflating the indicated value at non-zero cross-sensitivity.
- **Device-model parameters were silently reset.** `set_config()` → `config()`
  dropped `sensitivity`, `baseline_ppm`, and the temperature/humidity
  coefficients, so loading a project changed the replay and the next edit wrote
  the defaults back into the project.

### Changed

- **A phase-I CO₂ source concentration is refused as uncited.** The aerobic
  phase's CO₂ mass is a carbon balance; AP-42 gives no CO₂/N₂ split for it, so
  dividing by the modelled mixture reported 1 000 000 ppmv (100%). The mass stays
  in the batch report; `auto_concentration_ppmv(scenario, "CO2")` raises and names
  the gap.
- **The moisture test now asserts what moisture actually does.** The previous
  `wet > dry` assertion on the CH₄ *source* passed only on float noise
  (549999.9999999999 vs 550000.0); the steady-state share is cited at 55%. The
  test asserts the gas *mass* difference (2.16× on the measured example).
- **Manifest format 4.** The scenario block gains `tonnage_t`, the composition
  fractions, and a `generation` block captured at reservation time. Version 3
  manifests are rejected rather than misread.
- **Documentation corrected against the code.** The roadmap and task list now
  record W0–W3 as implemented, T-024's field view as done, T-056's sandbox
  table-publishing as superseded, and the module/test counts as they are.

---

## [0.2.1] — 2026-09-19

The release that makes the gas model match the thing being modelled, and adds a
waste layer that answers *what should we do with this load?* rather than only
*what does a sensor read next to it?*

### Added

**Waste intelligence layer** — simulation-driven, no editable gas numbers.

- `core/composition.py` — seven Table HH-1 mass fractions (food, garden, paper,
  wood, textile, diaper, sludge, inert) with their cited `DOC` and `k` ranges;
  decomposition phase I–IV from holding time; the Table HH-1 footnote-c rule
  that selects `k` from moisture.
- `core/generation.py` — 40 CFR §98.343(a)(1) **Equation HH-1**, with CO₂ and N₂
  tied to CH₄ at the AP-42 steady-state ratio so the methane ceiling is exactly
  55%.
- `core/massbalance.py` — every kilogram accounted: products, moisture as its own
  stream, and residue.
- `core/suitability.py` — per-route scores (RDF, recycling, composting, anaerobic
  digestion, landfill), each carrying the rule and the inputs behind it.
- `core/recommend.py` — one actionable recommendation with reasons, caveats, and
  a runner-up margin.
- `core/pipeline.py` — the whole chain in one call.
- `ui/batch_panel.py` — the live surface: editing a fraction, holding time,
  tonnage, or moisture recomputes and repaints immediately, with no solve.

**Gas catalogue** — 10 → **47 cited AP-42 species**, grouped by family
(headline, sulfur, aromatic, alkane, oxygenate, chlorinated, halocarbon). Values,
ratings, bases, and molecular weights are read out of the workbook by the
generator; none is transcribed, and each molecular weight is cross-checked
against its AP-42 row at build time.

**Container setup from the GUI** — *Run → Set up OpenFOAM container* and a
toolbar action pull and verify the image off the GUI thread. Podman storage is
kept in `~/.scentinel/containers/` (`SCENTINEL_HOME` overrides), so the desktop
user's default container storage is untouched.

**RDF and exposure assessment** — peak-versus-limit checks against published
limits (NIOSH REL, methane LEL) with the exceedance ratio and the peak sensor;
peak-to-mean as a placement-coverage indicator; gas-phase chlorine and sulfur
loading from the AP-42 Table 2.4-1 trace species.

**Analytical solver benchmarks** — `tests/verification/test_analytical_benchmarks.py`
compares the solver against closed-form solutions: pure advection (measured error
**0.0000**), axial diffusion against the exponential profile (deviation
**0.0552** at Pe = 5), and bin-probe bounds.

**Documents** — `docs/gas-composition-basis.md` (the cited scientific basis and
its gaps), `docs/superpowers/plans/2026-09-19-waste-intelligence.md` (the W-phase
plan), and `docs/logo.svg`.

### Changed

- **Gas source strengths are computed, not entered.** Methane comes from the
  decomposition model: a fresh 8-hour load reports **0 ppmv**, an aged load
  reaches the cited **550 000 ppmv**. Trace species keep their AP-42 Table 2.4-1
  values.
- **`moisture_fraction` now affects the result.** It previously round-tripped
  through the project file and changed nothing; it now selects `k` within the
  cited Table HH-1 range (measured: k 0.0377 → 0.0883 /yr, CH₄ 26 → 59 kg for the
  same load).
- **Manifest format 3** records the waste stream and `age_h`, because a record
  that cannot say which holding time produced its concentrations is not
  reproducible.
- **One dock-based workspace** replaces the three separate modes; panels are
  dockable, tabbable, and the arrangement is remembered per workspace.
- **Layout fixes**: the sensor lab is shrinkable with scrollable tabs, and the
  gas source rows no longer overflow the setup panel.

### Fixed

- **`get_gas()` could not read footnote-marked cells.** AP-42 stores some
  concentrations as `"4.0x10-3"`, `"3.0x10-2"`, and `"110e"`; a bare `float()`
  rejected all three, which silently restricted the catalogue to the gases stored
  numerically. The parser now handles both notations and raises rather than
  guessing when a cell cannot be read.
- **A field-render failure aborted run finalization.** An `AttributeError` from
  pyvista escaped before `_finalize_run`, leaving a succeeded solve recorded as
  `incomplete` — a lost audit record for a cosmetic failure. Rendering is now
  reported as a warning and never fatal.
- **`pyvista.Plotter` import race.** `pv.Plotter` goes through pyvista's module
  `__getattr__`, which imports `pyvista.plotting` on first access; with the solver
  thread importing that submodule concurrently the lookup ran against a partially
  initialised module. `Plotter` is now imported by name from the submodule.
- **`HomeWindow(path=...)` did not load the project.** A path alone now opens the
  project it points at.
- **`--userns=keep-id` failed in a private graphroot** with "creating an ID-mapped
  copy of layer". The generated `storage.conf` now selects `fuse-overlayfs` with
  `ignore_chown_errors` when it is available.
- **Run button stayed disabled without saying why.** It now surfaces the blocker.

### Removed

- **The linear organic-fraction scaling.** `organic_fraction / 0.50` had no
  citation and produced physically impossible composition: `green-waste` reached
  **85% CH₄** against a 55% ceiling. `ORGANIC_REFERENCE`, `ORGANIC_SCALE_GASES`,
  and the rule itself are deleted — no alias, no fallback. The same stream now
  reports **55.0%**, the cited steady-state value.
- **`SCALAR_DIFFUSIVITY_M2_S`** — one constant for every gas, replaced by
  `casegen.scalar_diffusivity(gas)` computed with Fuller-Schettler-Giddings.

### Known limitations

- **Mesh independence still fails**: 56.4% / 87.2% / 8.5% deviation under 2×
  refinement. The transport itself is verified against closed forms, so the error
  is in the source boundary, not the solver. Absolute concentrations stay
  `screening_estimate` until this passes.
- **No RDF fuel class.** EN 15359 / ISO 21640 class boundaries are not yet cited
  in the repository, and NCV / ash / fuel-basis chlorine cannot be derived from
  the gas phase. The code reports the three parameters and withholds the class
  rather than inventing thresholds.
- **Mercury is not selectable.** It is the only Table 2.4-1 entry with no
  counterpart in the gas catalogue: it is an element, not a compound with a
  molecular weight the FSG correlation applies to. The reason recorded earlier —
  "it is an element, not a gas" — was wrong; mercury does exist as a vapour in
  landfill gas, and its Table 2.4-1 default is 2.9×10⁻⁴ ppmv (rating E).
- **Fresh-waste VOC composition is not yet extracted.** Phase I has no cited
  composition in the repository; the three sources are identified in
  `docs/gas-composition-basis.md` §5.1 and the gap is recorded rather than filled.
- **No scenario comparison, sensor interpretation, or forecasting yet** — tasks
  T-130 to T-142 in `docs/TASKS.md`.

### Notes on accuracy

Every number below is checked by test against an independent source, not against
the code that produced it:

| Property | Value | Checked against |
|---|---|---|
| Ultimate methane yield | 103.33 kg CH₄/t | 40 CFR Equation HH-1, DOC = 0.31 |
| Fresh load (8 h) methane | exactly 0 kg | AP-42 §2.4.4: phase I is aerobic |
| Aged load (3 yr) methane share | exactly 55.000000% | AP-42 p.2.4-3 steady state |
| Mass closure, 10 t batch | 10.0000 t out, gap 0.00e+00 | conservation |
| Advection transport | error 0.0000 | exact solution |
| Axial diffusion | deviation 0.0552 at Pe = 5 | exponential profile |

---

## [0.2.0] — 2026-09-19

### Added

- Waste stream selection: six streams (mixed MSW, co-disposal, organic-rich,
  green waste, RDF feedstock, dry recyclables) selecting the AP-42 regime and
  their default gases.
- Top toolbar with Dashboard / Simulation / Sandbox; studio and sandbox share one
  editor and one `.scentinel` file; recent projects restore geometry, sensors, lab
  settings, and the last run.
- Virtual sensor lab: PID / MOX / electrochemical / NDIR / pellistor models with
  range, detection limit, response and recovery times, noise, drift, and
  cross-sensitivity; replayed readings publish into the same results table a
  solve fills.
- GitHub Releases shipping `.deb`, `.rpm`, an Arch prefix `.tar.gz` with
  `PKGBUILD`, and a Windows `.exe`.

### Fixed

- The nfpm asset name in the Linux packager was wrong, so `tar` unpacked an HTML
  error page and the build failed.

---

## [0.1.0] — 2026-09-18

Initial release. 2D bin cross-section, gmsh meshing, OpenFOAM case generation,
Podman runner, probe sampling, results table with CSV export, bilingual UI
(English / Indonesian), and persistent per-run manifests with provenance.

[0.2.3]: https://github.com/alertxsto/scentinel/releases/tag/v0.2.3
[0.2.2]: https://github.com/alertxsto/scentinel/releases/tag/v0.2.2
[0.2.1]: https://github.com/alertxsto/scentinel/releases/tag/v0.2.1
[0.2.0]: https://github.com/alertxsto/scentinel/releases/tag/v0.2.0
[0.1.0]: https://github.com/alertxsto/scentinel/releases/tag/v0.1.0
