# Scentinel — CFD Simulation Studio: Design Spec

**Date:** 2026-09-18
**Status:** Approved for planning
**Team:** Dwiky Candra, Gesang Hemas Bayu Sekti, Ezekiel Benedicte Felice — President University
**Supervisor:** Pak Rijal, Head of Environmental Engineering (Kaprodi Teknik Lingkungan)

## 1. Purpose

Scentinel is a native desktop application that simulates airflow and gas
dispersion around a waste collection vehicle bin, so the team can evaluate
where gas sensor inlets should be placed before any hardware is mounted.

The system answers: *given this bin geometry, waste mound shape, wind
conditions, and gas source strength, what concentration does each candidate
sensor position see?*

## 2. Scope

### In scope (MVP through F3)

- 2D cross-section of a truck bin (parameterized template)
- Waste mound presets: flat, mounded, irregular
- Candidate sensor placement by clicking in a 2D viewport
- Passive scalar transport for CO, CH4, VOC (and optionally H2S)
- Steady-state RANS k-epsilon airflow
- Scenario parameters: wind speed/direction, ventilation, per-gas source strength
- Visualization: velocity field, concentration fields, streamlines, per-sensor values
- Run comparison and CSV/PDF export
- Bilingual UI (English / Indonesian)

### Out of scope (later phase)

- 3D geometry (planned as F4)
- Transient response-delay analysis (planned as F4)
- Thermal/buoyancy coupling
- Physical sensor integration
- ML/AI pipeline integration

## 3. Architecture

```
┌─────────────────────────────────────────────────────┐
│  Scentinel — PySide6 Desktop App (Python 3.12+)     │
│                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │ Setup Panel │  │ 2D Viewport  │  │  Results   │  │
│  │ geometry &  │  │ click sensor │  │  Viewer    │  │
│  │ scenario    │  │ + preview    │  │  + plots   │  │
│  └─────────────┘  └──────────────┘  └────────────┘  │
│                                                     │
│  Core Engine:                                       │
│  geometry.py → mesh.py (gmsh) → casegen.py (Jinja2) │
│       → runner.py (podman subprocess) → post.py     │
│                                                     │
│  i18n: locales/en.json + id.json (runtime switch)   │
└────────────────────────┬────────────────────────────┘
                         │ podman run, mount case dir
                         ▼
        ┌────────────────────────────────┐
        │ opencfd/openfoam-default:2512  │
        │ foamRun + incompressibleFluid  │
        │ + scalarTransport (CO/CH4/VOC) │
        │ + foamToVTK                    │
        └────────────────────────────────┘
```

### 3.1 Component responsibilities

| Component | Responsibility | Depends on |
|---|---|---|
| `core/geometry.py` | Build 2D bin + mound outlines from parameters via gmsh OCC | gmsh |
| `core/mesh.py` | Generate 2D mesh, tag physical boundaries (inlet/outlet/wall/source) | gmsh |
| `core/casegen.py` | Write OpenFOAM case (`0/`, `constant/`, `system/`) from templates | jinja2, gas_defaults |
| `core/gas_data.py` | Load gas properties and source defaults with citations | gas_defaults |
| `core/runner.py` | Run `foamRun` in podman, stream logs, support cancel | podman, subprocess |
| `core/post.py` | Read VTK output, probe sensor points, mass balance check | pyvista |
| `core/project.py` | Save/load `.scentinel` project files (JSON) | json |
| `ui/setup_panel.py` | Geometry and scenario forms | PySide6 |
| `ui/viewport.py` | 2D geometry rendering, sensor click placement | PySide6 QGraphicsView |
| `ui/results_panel.py` | Field visualization, probe table/plots | pyvistaqt, pyqtgraph |
| `ui/i18n.py` | Runtime language switching | json locales |
| `app.py` | Entry point, window assembly | all above |

### 3.2 Key interfaces

```python
# core/geometry.py
@dataclass
class BinGeometry:
    length_m: float
    height_m: float
    mound_shape: str  # "flat" | "mounded" | "irregular"
    mound_fill_fraction: float  # 0..1

def build_geometry(geom: BinGeometry) -> gmsh.model: ...

# core/mesh.py
@dataclass
class MeshResult:
    msh_path: Path
    boundary_names: dict[str, int]  # name -> physical group tag

def generate_mesh(geom: BinGeometry, mesh_size_m: float, out_dir: Path) -> MeshResult: ...

# core/casegen.py
@dataclass
class Scenario:
    wind_speed_m_s: float
    wind_direction: str  # "left-to-right" | "right-to-left"
    ventilation_on: bool
    gas_sources: dict[str, float]  # gas key -> source strength (kg/m2/s or ppm basis)

def write_case(scenario: Scenario, mesh: MeshResult, out_dir: Path) -> Path: ...

# core/runner.py
@dataclass
class RunResult:
    case_dir: Path
    exit_code: int
    log_path: Path

def run_case(case_dir: Path, on_log: Callable[[str], None], cancel: threading.Event) -> RunResult: ...

# core/post.py
@dataclass
class ProbeResult:
    sensor_id: str
    position: tuple[float, float]
    values: dict[str, float]  # gas key -> concentration

def load_results(case_dir: Path, sensors: list[SensorPoint]) -> list[ProbeResult]: ...
def mass_balance(case_dir: Path, gas_key: str) -> float: ...
```

### 3.3 Data flow

```
User setup → Save .scentinel → [Run]
  → gmsh: 2D mesh + boundary tags
  → casegen: write OpenFOAM case to runs/<run-id>/
  → podman: solve (stream log to UI thread)
  → foamToVTK → pyvista: load fields
  → probe sensor points → table + plots
  → persist run results → compare with previous runs
```

## 4. Physics Setup

### 4.1 Solver

- `foamRun` with `incompressibleFluid` module (steady-state RANS)
- Turbulence: k-epsilon
- Passive scalars via `scalarTransport` function object: CO, CH4, VOC

### 4.2 Boundary conditions

| Patch | Velocity | Pressure | Scalar |
|---|---|---|---|
| inlet | fixedValue (wind) | zeroGradient | fixedValue 0 |
| outlet | zeroGradient | fixedValue 0 | zeroGradient |
| walls (bin) | noSlip | zeroGradient | zeroGradient |
| source (mound surface) | noSlip | zeroGradient | fixedValue (from AP-42) |

### 4.3 Source term basis

Default concentrations come from `gas_defaults.py`, generated from EPA AP-42
final tables (August 2024) by `scripts/build_gas_data.py`. See
`docs/references.md` for the full provenance chain.

Key values:
- CO: 105 ppmv (uncontrolled, AP-42 Final Factors)
- CH4: 50% by volume (EPA LMOP)
- VOC/NMOC: 550 ppmv as hexane (AP-42 Table 2.4-2, MSW-only 1992+)
- H2S: 36 ppmv (AP-42 Table 2.4-1)

## 5. Verification Strategy

1. **Mesh independence**: refine mesh 2× and confirm probe values change <10%
2. **Mass balance**: for steady state, scalar in/out flux ≈ source flux (error <5%)
3. **Analytical benchmark**: 1D diffusion case compared to erfc solution (R² > 0.99)
4. **Solver benchmark**: lid-driven cavity case runs to completion with expected residuals

## 6. Testing Strategy

| Layer | Tool | Coverage |
|---|---|---|
| Unit | pytest | geometry areas, boundary tag mapping, case dict validity, project round-trip |
| UI | pytest-qt | sensor click mapping, language switch, panel smoke tests |
| Integration | pytest -m integration | full case run in podman, VTK load, probe extraction |
| Verification | pytest -m verification | mesh independence, mass balance, analytical benchmark |

Integration tests skip automatically when podman or the container image is absent.

## 7. Constraints & Risks

| Constraint / Risk | Mitigation |
|---|---|
| VTK + Qt6 on Wayland | Test early in Task 0.5; fallback `QT_QPA_PLATFORM=xcb` or offscreen render |
| gmsh mesh rejected by OpenFOAM | Strict boundary tagging tests + `checkMesh` gate |
| Long solver runs freeze UI | Async log streaming via QThread from Task 0.3 |
| Source term credibility | Every default cites AP-42/LMOP in code and `docs/references.md` |
| Python 3.14 wheel availability | All deps verified to have compatible wheels or abi3 |

## 8. Acceptance Criteria

1. Full scenario (setup → run → results → save) completes in <10 min on standard mesh
2. Mass balance error <5% for steady cases
3. Probe values consistent across mesh refinement (<10% deviation)
4. 1D diffusion matches analytical solution (R² > 0.99)
5. App runs on Fedora 44 KDE Wayland with Python 3.12+

## 9. Roadmap

| Phase | Content | Exit criteria |
|---|---|---|
| F0 | App skeleton + podman OpenFOAM + cavity benchmark | Solver runs from app, results render |
| F1 | 2D geometry + mesh + sensor clicks | One scenario runs end-to-end |
| F2 | Multi-gas scalars + visualization + probes | CO/CH4/VOC visible and probed |
| F3 | Scenario comparison + report export | Compare ≥2 runs, export CSV/PDF |
| F4 | 3D + transient | 3D mesh runs, response delay measured |
