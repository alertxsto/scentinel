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

## Requirements

- Python 3.12+
- Podman (for the OpenFOAM solver container)

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
./scripts/setup_container.sh
```

## Run

```bash
.venv/bin/scentinel
```

## Tests

```bash
.venv/bin/pytest -m "not integration and not verification"
.venv/bin/pytest -m integration
.venv/bin/pytest -m verification
```

## Data provenance

All simulation defaults (gas concentrations, physical properties) are derived
from public sources and documented in [docs/references.md](docs/references.md).
The generator script is `scripts/build_gas_data.py`; the scraper is
`scripts/scrape_references.py`.

## License

MIT
