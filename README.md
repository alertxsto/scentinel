# Scentinel

Native desktop simulation studio for gas sensor placement in waste collection
vehicles. Built with PySide6, gmsh, and OpenFOAM running in a Podman container.

> scent + sentinel — the watchful nose.

**Team:** Dwiky Candra, Gesang Hemas Bayu Sekti, Ezekiel Benedicte Felice
**Supervisor:** Pak Rijal, Head of Environmental Engineering (Kaprodi Teknik Lingkungan), President University

## What it does

1. Define a 2D cross-section of a waste truck bin and a waste mound
2. Click candidate sensor positions in the viewport
3. Configure gas source scenarios (CO / CH4 / VOC / H2S) with cited EPA AP-42 defaults
4. Run CFD (airflow + passive scalar transport) in an OpenFOAM container
5. Inspect concentration fields, streamlines, and per-sensor values
6. Compare scenarios and export a report

## Status

Steps 1–5 run end to end: the desktop UI, the gmsh mesh, the OpenFOAM case
generator, the Podman solver runner, and the probe post-processing. Pressing
**Run Simulation** meshes the bin cross-section, writes a case, solves it in
the container, and fills the results table with per-sensor concentrations.

Step 6 (scenario comparison) is not built: runs are not yet collected into a
history, and PDF reporting is missing. CSV export of the sensor table works.

**Known gap — mesh independence.** The design spec asks for <10% deviation in
probe values when the mesh is refined 2x. Measured on this pipeline the
deviation is much larger and does not decrease with refinement, so the gate
currently fails; `tests/verification/test_mesh_independence.py` records the
measured behaviour instead of asserting the target. The cause is the source
boundary: a fixed surface concentration on a diffusive patch makes the sampled
value depend on the near-wall cell height, which uniform refinement does not
resolve. Treat absolute concentrations as screening estimates, not calibrated
values.

## Requirements

- Python 3.12+
- Podman, for the OpenFOAM solver container

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,cfd]"
./scripts/setup_container.sh
```

Extras: `.[cfd]` (gmsh, pyvista, VTK) is required to run simulations;
`.[report]` (Jinja2, matplotlib, pyqtgraph) is for the reporting work.

## Run

```bash
.venv/bin/scentinel
.venv/bin/scentinel path/to/project.scentinel   # open a project directly
```

In the window: set the geometry and wind, tick the gases you want (leave
**auto** checked to use the cited AP-42 defaults), click in the viewport to
place sensors, then press **Run Simulation** (F5). Runs are written to
`runs/run-NNN/` beside the project file; cancel with Shift+F5.

## Tests

```bash
.venv/bin/pytest -m "not integration and not verification"
.venv/bin/pytest -m integration     # needs podman + the solver image
.venv/bin/pytest -m verification    # slow; physics gates
```

UI tests run headless via `QT_QPA_PLATFORM=offscreen`, set in `tests/conftest.py`.

## Data provenance

All simulation defaults (gas concentrations, physical properties) are derived
from public sources and documented in [docs/references.md](docs/references.md).
The generator script is `scripts/build_gas_data.py`; the scraper is
`scripts/scrape_references.py`.

## License

MIT
