<div align="center">

<img src="docs/logo.svg" alt="Scentinel" width="128" height="128">

# Scentinel

**CFD simulation studio for gas sensor placement in waste collection vehicles.**

*scent + sentinel — the watchful nose.*

</div>

---

Scentinel answers one question: *given this bin geometry, waste stream, wind, and
gas source strength, what concentration does each candidate sensor position see?*
It is a native PySide6 desktop app that meshes a 2D bin cross-section with gmsh,
writes an OpenFOAM case, solves it in a Podman container, and reports per-sensor
concentrations with a persisted, auditable record of every attempt.

## What it does

1. Define a 2D cross-section of a waste truck bin and a waste mound
2. Choose a waste stream (mixed MSW, co-disposal, organic-rich, green waste, RDF
   feedstock, dry recyclables) and set the organic and moisture fractions
3. Click candidate sensor positions in the viewport
4. Configure gas sources from cited EPA AP-42 defaults, or enter manual values
   (CO, CH₄, VOC, H₂S, ethane, benzene, toluene, vinyl chloride, methyl
   mercaptan, dimethyl sulfide)
5. Run CFD (airflow + passive scalar transport) in an OpenFOAM container
6. Inspect concentration fields and per-sensor values, then export CSV
7. Replay each placement through a virtual sensor model in the sensor lab

## Status

The 2D pipeline runs end to end: desktop UI → gmsh mesh → OpenFOAM case →
Podman solve → probe sampling → results table. Projects save and load, the UI
switches language at runtime, and results export to CSV.

Every attempt is recorded. Each run gets a never-reused `runs/run-NNN/`
directory holding an immutable `run.json` manifest with the requested inputs
(project snapshot, per-gas mode and provenance), the applied numerical
experiment (inlet speed at the bin rim after the wind profile, viscosity,
per-gas scalar diffusivity, solver tolerances, residual targets, relaxation
factors, and a SHA-256 digest of the generated case inputs), the requested
iteration count, solver and container identity, the terminal execution status,
and per-sensor ppmv results. Records survive restarts and are readable through
`scentinel.core.history` (`list_runs()` / `get_run()`); failed and cancelled
attempts are recorded too.

Manifest format 5 also records the batch the run solved: the composition
fractions, the tonnage, and the generation chemistry the model derived from
them — the ultimate potential, the cumulative gas produced by the recorded age,
and the instantaneous generation rate, each a separate quantity. The batch
panel and the setup form edit one scenario, so the assessment a user reads is
the waste the case actually solves.

The generated gas is split by the regulation's own default methane fraction,
`F = 0.5` (40 CFR 98.343 Table HH-1), at every age; the AP-42 55/40/5 mix is
retained as a measured mature-landfill ceiling, not as the produced mixture.
Holding time therefore moves the gas **rate and cumulative mass**, not the
volume share. The phase label (I–IV) is an interpretation of the age, not a
switch: the 48 h / 90 d / 365 d boundaries are a labelled model assumption, and
each phase states how far its model reaches — in particular that the anaerobic
HH-1 model is extrapolated into the aerobic phase I.

`execution_status: "succeeded"` means the container pipeline exited 0 and every
captured sensor was sampled. It does **not** mean the run converged, or that
mesh independence, mass balance, or experimental validation passed: each of
those is a separate gate in `quality`, recorded as `not_evaluated` or `not_run`
for an ordinary run. The `ventilation` input is recorded as
`{"requested_on": …, "modelled": false}` because the case generator ignores it.

## Roadmap

| Phase | Content | Status |
|---|---|---|
| **F0** | App skeleton, Podman runner, OpenFOAM integration | Done |
| **F1** | 2D geometry, mesh, sensor placement, project save/load | Done |
| **F2** | Multi-gas scalars, probes, results panel | Probes and field view done; **physics verification failing** |
| **F3** | Run history, comparison, reporting | History done; comparison view and PDF pending |
| **W** | Waste intelligence: composition → generation → yield → decision | Engine done; comparison/decision UI pending |
| **F4** | 3D geometry, transient solver, response-delay analysis | Not started |

**Milestones**

| Milestone | Definition of done |
|---|---|
| **M1 — Trustworthy numbers** | Mesh independence <10%; mass balance automated and <5% |
| **M2 — Inspectable results** | Concentration field and streamlines render in the app for a solved run |
| **M3 — Comparison** | Two runs side by side with a difference column; PDF report with cited defaults |
| **M4 — Review** | Results reviewed and signed off before any hardware decision |
| **M5 — 3D** | 3D mesh runs; response delay measured |

### Blocking issue: mesh independence

The design spec requires probe values to change by less than 10% when the mesh is
refined 2×. Measured on the current pipeline:

| Mesh size | Cells | S1 (ppmv) | S3 (ppmv) |
|---|---|---|---|
| 0.50 m | 3 444 | 0.342 | 4.340 |
| 0.25 m | 7 248 | 0.465 | 3.363 |
| 0.125 m | 28 016 | 0.887 | 6.358 |

Deviation is 76.5% at the first refinement, and the sequence is not converging.
The source is a `fixedValue` concentration on a diffusive patch, so the flux
entering the domain scales with the first cell height. The fix is a mass-flux
source term in kg/m²/s; until it lands, **treat absolute concentrations as
screening estimates and use results for relative comparison only.** The full
analysis and the ranked fix options are in
[docs/ROADMAP.md](docs/ROADMAP.md#blocking-issue-mesh-independence).

## Documentation

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Module map, data flow, physics setup, load-bearing implementation details |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phase plan, current position, milestones, risks |
| [docs/TASKS.md](docs/TASKS.md) | Every task with status, files, and acceptance test |
| [docs/references.md](docs/references.md) | Data provenance: every gas default and its source |
| [CHANGELOG.md](CHANGELOG.md) | Every release, with the measured accuracy figures and the known limitations |
| [docs/gas-composition-basis.md](docs/gas-composition-basis.md) | Scientific basis for gas composition: why the current basis does not fit a fresh truck bin, and the cited model that replaces it |

## Requirements

- Python 3.12+
- Podman, for the OpenFOAM solver container

## Releases

GitHub Releases ship `.deb`, `.rpm`, an Arch prefix `.tar.gz`, and a Windows
`.exe`. The GUI launches without Podman; a solve needs the container below.

```bash
sudo apt install ./scentinel_*-amd64.deb        # Debian / Ubuntu
sudo dnf install ./scentinel-*.x86_64.rpm       # Fedora
sudo tar -C / -xzf scentinel-*-x86_64.tar.gz    # Arch
```

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,cfd]"
./scripts/setup_container.sh
```

Extras: `.[cfd]` (gmsh, pyvista, VTK) is required to run simulations;
`.[report]` (Jinja2, matplotlib, pyqtgraph) is for the reporting work.

The container image can also be pulled from the app itself: **Run → Set up
OpenFOAM container**. Its Podman storage is kept under the Scentinel app home
(`~/.scentinel/containers/`, override with `SCENTINEL_HOME`) so nothing lands in
the desktop user's default container storage.

## Run

```bash
.venv/bin/scentinel
.venv/bin/scentinel path/to/project.scentinel   # open a project directly
```

In the window: pick the waste stream, set the geometry and wind, tick the gases
you want (leave **auto** checked to use the cited AP-42 defaults), click in the
viewport to place sensors, then press **Run Simulation** (F5). Runs are written
to `runs/run-NNN/` beside the project file, each with its `run.json` manifest;
cancel with Shift+F5. The next run always takes an id greater than every
existing `run-NNN` directory, so a restart never overwrites an earlier run. The
run samples a frozen copy of the project, so editing during a run cannot change
what a record claims to have measured.

**Sensor Lab** opens the same project with the virtual measurement chain: it
replays each placement through a selectable sensor model (PID, MOX,
electrochemical, NDIR, pellistor) with its own range, detection limit, response
and recovery times, noise, drift, and cross-sensitivity. The lab reads the
latest solved run's readings as ground truth (falling back to a manual value
when there is no run), and a finished solve is pushed into it automatically, so
the device model always evaluates the concentrations on screen. The replay's
output is shown in the lab's own telemetry tab; it does not write into the
results table.

## Outputs

The Summary tab reports what the pipeline can actually compute, and names what
it cannot rather than filling the gap with a guess:

| Block | Contents |
|---|---|
| Gas results | Per-gas min / mean / maximum ppmv across the sampled sensors, and the peak sensor for each gas |
| Safety and placement | Each gas's peak against a published limit (NIOSH REL, or the methane LEL), with the exceedance ratio; peak-to-mean spread as a placement-coverage indicator; gases with no published limit listed as unchecked |
| RDF suitability | Gas-phase chlorine and sulfur loading in mg/Nm³ from the AP-42 Table 2.4-1 trace species, with the largest carrier named |
| Physical TVOC | Reports "requires sensor hardware and calibration" for an ordinary run; the lab's virtual device output lives in the Sensor Lab panel |

Fuel-basis RDF class (NCV, Cl %, ash as a percentage of dry mass) needs a
laboratory analysis of the material. It is reported as needing that analysis and
is never estimated from the gas phase: the gas cannot tell you the mass of the
fuel, so any number derived from it would be fabricated.

## Container

The solver runs in a Podman container. Pull and verify it from the app — **Run →
Set up OpenFOAM container**, also on the toolbar — or from the shell:

```bash
./scripts/setup_container.sh
```

Podman storage for that image is kept inside the Scentinel app home
(`~/.scentinel/containers/`, override with `SCENTINEL_HOME`) rather than the
desktop user's default container storage. The generated `storage.conf` selects
`fuse-overlayfs` when it is installed: the run uses `--userns=keep-id` so the
container user matches the host user and the mounted case directory stays
writable, and the native overlay driver cannot serve that from a private
graphroot.

## Tests

```bash
.venv/bin/pytest -m "not integration and not verification"
.venv/bin/pytest -m integration     # needs podman + the solver image
.venv/bin/pytest -m verification    # slow; physics gates
```

UI tests run headless via `QT_QPA_PLATFORM=offscreen`, set in `tests/conftest.py`.

## Data provenance

Every simulation default (gas concentrations, molecular weights, diffusivities)
comes from a public source and is documented in
[docs/references.md](docs/references.md). The generator script is
`scripts/build_gas_data.py`; the scraper is `scripts/scrape_references.py`.

## License

MIT — see [LICENSE](LICENSE).
