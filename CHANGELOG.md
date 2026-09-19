# Changelog

All notable changes to Scentinel are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Two things are worth knowing before reading:

- **`screening_estimate` is not a formality.** Absolute concentrations are not
  mesh-converged (measured: 56.4% / 87.2% / 8.5% deviation under a 2× refinement),
  so every concentration-derived figure is relative until that gate passes.
- **A value without a citation does not enter the model.** Where no cited value
  exists, the output states the gap instead of filling it. This is why several
  fields read "requires laboratory characterisation" rather than showing a number.

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
  counterpart: it is an element, not a gas.
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

[0.2.1]: https://github.com/alertxsto/scentinel/releases/tag/v0.2.1
[0.2.0]: https://github.com/alertxsto/scentinel/releases/tag/v0.2.0
[0.1.0]: https://github.com/alertxsto/scentinel/releases/tag/v0.1.0
