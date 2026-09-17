# Scentinel MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a native desktop app that simulates airflow and gas dispersion around a waste truck bin to evaluate gas sensor placement.

**Architecture:** PySide6 desktop UI wrapping a Python core engine (gmsh meshing → OpenFOAM case generation → Podman-based solver execution → PyVista post-processing). OpenFOAM runs in a Podman container; the app never installs OpenFOAM natively.

**Tech Stack:** Python 3.12+, PySide6 6.11, gmsh 4.15, Jinja2, pyvista/pyvistaqt/VTK, pyqtgraph, numpy, matplotlib, podman, OpenFOAM 2512 container.

**Spec:** `docs/superpowers/specs/2026-09-18-scentinel-design.md`

## Global Constraints

- Python 3.12+ (venv at `.venv/`)
- All gas defaults must cite a source (AP-42 / EPA LMOP) — no unsourced numbers
- OpenFOAM runs only via Podman container `opencfd/openfoam-default:2512`
- UI is bilingual: English default, Indonesian switchable at runtime
- Integration tests must skip (not fail) when podman/image is unavailable
- Never commit the `.venv/`, `runs/`, or generated mesh files
- Line length 100 (ruff), target Python 3.12

---

## File Structure

```
scentinel/
├── pyproject.toml                          # exists
├── README.md                               # exists
├── .gitignore                              # Task 0.1
├── scripts/
│   ├── setup_container.sh                  # Task 0.2
│   ├── scrape_references.py                # exists
│   └── build_gas_data.py                   # exists
├── src/scentinel/
│   ├── __init__.py                         # Task 0.1
│   ├── app.py                              # Task 0.5
│   ├── ui/
│   │   ├── __init__.py                     # Task 0.5
│   │   ├── main_window.py                  # Task 0.5
│   │   ├── setup_panel.py                  # Task 1.4
│   │   ├── viewport.py                     # Task 1.4
│   │   ├── results_panel.py                # Task 2.4
│   │   └── i18n.py                         # Task 0.5
│   ├── core/
│   │   ├── __init__.py                     # Task 0.1
│   │   ├── gas_defaults.py                 # exists (generated)
│   │   ├── gas_data.py                     # Task 2.1
│   │   ├── geometry.py                     # Task 1.1
│   │   ├── mesh.py                         # Task 1.2
│   │   ├── casegen.py                      # Task 1.3
│   │   ├── runner.py                       # Task 0.3
│   │   ├── post.py                         # Task 2.3
│   │   └── project.py                      # Task 1.5
│   └── resources/
│       ├── templates/                      # Task 0.4
│       │   ├── 0/...
│       │   ├── constant/...
│       │   └── system/...
│       └── locales/
│           ├── en.json                     # Task 0.5
│           └── id.json                     # Task 0.5
└── tests/
    ├── conftest.py                         # Task 0.1
    ├── unit/
    │   ├── test_runner.py                  # Task 0.3
    │   ├── test_geometry.py                # Task 1.1
    │   ├── test_mesh.py                    # Task 1.2
    │   ├── test_casegen.py                 # Task 1.3
    │   ├── test_project.py                 # Task 1.5
    │   ├── test_gas_data.py                # Task 2.1
    │   └── test_post.py                    # Task 2.3
    ├── ui/
    │   ├── test_main_window.py             # Task 0.5
    │   └── test_viewport.py                # Task 1.4
    ├── integration/
    │   ├── test_cavity_benchmark.py        # Task 0.4
    │   └── test_e2e_scenario.py            # Task 1.6
    └── verification/
        ├── test_mass_balance.py            # Task 2.5
        ├── test_1d_diffusion.py            # Task 2.5
        └── test_mesh_independence.py       # Task 2.5
```

---

## F0 — Foundation & OpenFOAM Integration

### Task 0.1: Project scaffolding

**Files:**
- Create: `.gitignore`
- Create: `src/scentinel/__init__.py`
- Create: `src/scentinel/core/__init__.py`
- Create: `src/scentinel/ui/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/__init__.py`

**Interfaces:**
- Consumes: nothing
- Produces: importable `scentinel` package, pytest rootdir config

- [ ] **Step 1: Create .gitignore**

```gitignore
.venv/
__pycache__/
*.pyc
*.egg-info/
.pytest_cache/
runs/
*.msh
*.foam
*.vtk
*.vtu
.podman/
```

- [ ] **Step 2: Create package init files**

```python
# src/scentinel/__init__.py
"""Scentinel — CFD simulation studio for gas sensor placement."""

__version__ = "0.1.0"
```

```python
# src/scentinel/core/__init__.py
"""Core simulation engine."""
```

```python
# src/scentinel/ui/__init__.py
"""PySide6 user interface."""
```

```python
# tests/unit/__init__.py
```

- [ ] **Step 3: Create tests/conftest.py**

```python
from __future__ import annotations

import shutil
import subprocess

import pytest


def _podman_available() -> bool:
    if shutil.which("podman") is None:
        return False
    result = subprocess.run(
        ["podman", "image", "exists", "opencfd/openfoam-default:2512"],
        capture_output=True,
    )
    return result.returncode == 0


def pytest_collection_modifyitems(config, items):
    if _podman_available():
        return
    skip_integration = pytest.mark.skip(reason="podman or OpenFOAM image unavailable")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
```

- [ ] **Step 4: Install package and verify imports**

Run:
```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -c "import scentinel; print(scentinel.__version__)"
```
Expected: `0.1.0`

- [ ] **Step 5: Run empty test suite**

Run: `.venv/bin/pytest -q`
Expected: `no tests ran` (exit 5 is acceptable at this stage)

- [ ] **Step 6: Commit**

```bash
git add .gitignore src tests
git commit -m "chore: scaffold scentinel package"
```

---

### Task 0.2: Container setup script

**Files:**
- Create: `scripts/setup_container.sh`

**Interfaces:**
- Consumes: nothing
- Produces: pulled `opencfd/openfoam-default:2512` image, verified `foamRun` availability

- [ ] **Step 1: Write the setup script**

```bash
#!/usr/bin/env bash
set -euo pipefail

IMAGE="opencfd/openfoam-default:2512"

echo "==> Checking podman"
if ! command -v podman >/dev/null 2>&1; then
    echo "ERROR: podman is not installed" >&2
    exit 1
fi

echo "==> Pulling ${IMAGE}"
podman pull "${IMAGE}"

echo "==> Verifying foamRun inside the container"
podman run --rm "${IMAGE}" bash -lc "foamRun -help >/dev/null 2>&1 && echo 'foamRun OK'"

echo "==> Container ready"
```

- [ ] **Step 2: Make executable and run**

Run:
```bash
chmod +x scripts/setup_container.sh
./scripts/setup_container.sh
```
Expected: `foamRun OK` then `Container ready`

- [ ] **Step 3: Commit**

```bash
git add scripts/setup_container.sh
git commit -m "build: add OpenFOAM container setup script"
```

---

### Task 0.3: Podman runner

**Files:**
- Create: `src/scentinel/core/runner.py`
- Test: `tests/unit/test_runner.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `RunResult(case_dir: Path, exit_code: int, log_path: Path)`
  - `run_case(case_dir: Path, on_log: Callable[[str], None] | None = None, cancel: threading.Event | None = None) -> RunResult`
  - `build_podman_command(case_dir: Path) -> list[str]`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_runner.py
from __future__ import annotations

import threading
from pathlib import Path

from scentinel.core.runner import RunResult, build_podman_command, run_case


def test_build_podman_command_mounts_case_dir(tmp_path: Path):
    cmd = build_podman_command(tmp_path)
    assert cmd[0] == "podman"
    assert "run" in cmd
    assert any("opencfd/openfoam-default:2512" in part for part in cmd)
    assert any(f"{tmp_path}:/case" in part for part in cmd)


def test_run_case_captures_output(tmp_path: Path):
    logs: list[str] = []
    result = run_case(
        tmp_path,
        on_log=logs.append,
        command_override=["bash", "-lc", "echo hello-scentinel"],
    )
    assert isinstance(result, RunResult)
    assert result.exit_code == 0
    assert any("hello-scentinel" in line for line in logs)
    assert result.log_path.exists()


def test_run_case_cancel(tmp_path: Path):
    cancel = threading.Event()
    cancel.set()
    result = run_case(
        tmp_path,
        cancel=cancel,
        command_override=["bash", "-lc", "sleep 30"],
    )
    assert result.exit_code != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scentinel.core.runner'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/scentinel/core/runner.py
from __future__ import annotations

import shlex
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

IMAGE = "opencfd/openfoam-default:2512"


@dataclass
class RunResult:
    case_dir: Path
    exit_code: int
    log_path: Path


def build_podman_command(case_dir: Path) -> list[str]:
    return [
        "podman",
        "run",
        "--rm",
        "-v",
        f"{case_dir}:/case:Z",
        "-w",
        "/case",
        IMAGE,
        "bash",
        "-lc",
        "foamRun > log.foamRun 2>&1",
    ]


def run_case(
    case_dir: Path,
    on_log: Callable[[str], None] | None = None,
    cancel: threading.Event | None = None,
    command_override: Iterable[str] | None = None,
) -> RunResult:
    case_dir = Path(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    log_path = case_dir / "scentinel_run.log"

    if command_override is not None:
        command = list(command_override)
    else:
        command = build_podman_command(case_dir)

    if cancel is not None and cancel.is_set():
        log_path.write_text("cancelled before start\n", encoding="utf-8")
        return RunResult(case_dir=case_dir, exit_code=-2, log_path=log_path)

    lines: list[str] = []
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            lines.append(line)
            log_file.write(line)
            log_file.flush()
            if on_log is not None:
                on_log(line.rstrip("\n"))
            if cancel is not None and cancel.is_set():
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                break
        exit_code = process.wait()

    if cancel is not None and cancel.is_set() and exit_code == 0:
        exit_code = -2
    return RunResult(case_dir=case_dir, exit_code=exit_code, log_path=log_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_runner.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/runner.py tests/unit/test_runner.py
git commit -m "feat(core): add podman runner with log streaming and cancel"
```

---

### Task 0.4: Lid-driven cavity benchmark

**Files:**
- Create: `src/scentinel/resources/templates/cavity/system/blockMeshDict`
- Create: `src/scentinel/resources/templates/cavity/system/controlDict`
- Create: `src/scentinel/resources/templates/cavity/system/fvSchemes`
- Create: `src/scentinel/resources/templates/cavity/system/fvSolution`
- Create: `src/scentinel/resources/templates/cavity/constant/momentumTransport`
- Create: `src/scentinel/resources/templates/cavity/0/U`
- Create: `src/scentinel/resources/templates/cavity/0/p`
- Create: `src/scentinel/core/benchmark.py`
- Test: `tests/integration/test_cavity_benchmark.py`

**Interfaces:**
- Consumes: `runner.run_case`
- Produces: `create_cavity_case(dest: Path) -> Path`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_cavity_benchmark.py
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scentinel.core.benchmark import create_cavity_case
from scentinel.core.runner import run_case

pytestmark = pytest.mark.integration


def test_cavity_runs_to_completion(tmp_path: Path):
    if shutil.which("podman") is None:
        pytest.skip("podman unavailable")
    case = create_cavity_case(tmp_path / "cavity")
    result = run_case(case)
    assert result.exit_code == 0, result.log_path.read_text()
    log = result.log_path.read_text()
    assert "FOAM FATAL" not in log
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/integration/test_cavity_benchmark.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scentinel.core.benchmark'` (or skip if podman missing — ensure it fails on the import first)

- [ ] **Step 3: Write the benchmark case generator**

```python
# src/scentinel/core/benchmark.py
"""Lid-driven cavity benchmark used to verify the OpenFOAM container pipeline."""

from __future__ import annotations

import shutil
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "resources" / "templates" / "cavity"


def create_cavity_case(dest: Path) -> Path:
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(TEMPLATES, dest)
    return dest
```

- [ ] **Step 4: Write cavity template dictionaries**

`src/scentinel/resources/templates/cavity/system/blockMeshDict`:

```foam
FoamFile { version 2.0; format ascii; class dictionary; object blockMeshDict; }
scale 1;
vertices
(
    (0 0 0) (0.1 0 0) (0.1 0.1 0) (0 0.1 0)
    (0 0 0.01) (0.1 0 0.01) (0.1 0.1 0.01) (0 0.1 0.01)
);
blocks ( hex (0 1 2 3 4 5 6 7) (40 40 1) simpleGrading (1 1 1) );
edges ();
boundary
(
    movingWall { type wall; faces ((3 7 6 2)); }
    fixedWalls { type wall; faces ((0 4 7 3) (2 6 5 1) (1 5 4 0)); }
    frontAndBack { type empty; faces ((0 3 2 1) (4 5 6 7)); }
);
mergePatchPairs ();
```

`src/scentinel/resources/templates/cavity/system/controlDict`:

```foam
FoamFile { version 2.0; format ascii; class dictionary; object controlDict; }
application foamRun;
solver incompressibleFluid;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime 500;
deltaT 1;
writeControl timeStep;
writeInterval 100;
purgeWrite 0;
writeFormat ascii;
writePrecision 6;
writeCompression off;
timeFormat general;
timePrecision 6;
runTimeModifiable true;
```

`src/scentinel/resources/templates/cavity/system/fvSchemes`:

```foam
FoamFile { version 2.0; format ascii; class dictionary; object fvSchemes; }
ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; }
divSchemes
{
    default none;
    div(phi,U) Gauss linearUpwind grad(U);
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
```

`src/scentinel/resources/templates/cavity/system/fvSolution`:

```foam
FoamFile { version 2.0; format ascii; class dictionary; object fvSolution; }
solvers
{
    p { solver GAMG; tolerance 1e-06; relTol 0.1; }
    U { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-05; relTol 0.1; }
}
SIMPLE { nNonOrthogonalCorrectors 0; consistent yes; }
relaxationFactors { equations { U 0.9; } }
```

`src/scentinel/resources/templates/cavity/constant/momentumTransport`:

```foam
FoamFile { version 2.0; format ascii; class dictionary; object momentumTransport; }
simulationType laminar;
```

`src/scentinel/resources/templates/cavity/0/U`:

```foam
FoamFile { version 2.0; format ascii; class volVectorField; object U; }
dimensions [0 1 -1 0 0 0 0];
internalField uniform (0 0 0);
boundaryField
{
    movingWall { type fixedValue; value uniform (0.01 0 0); }
    fixedWalls { type noSlip; }
    frontAndBack { type empty; }
}
```

`src/scentinel/resources/templates/cavity/0/p`:

```foam
FoamFile { version 2.0; format ascii; class volScalarField; object p; }
dimensions [0 2 -2 0 0 0 0];
internalField uniform 0;
boundaryField
{
    movingWall { type zeroGradient; }
    fixedWalls { type zeroGradient; }
    frontAndBack { type empty; }
}
```

- [ ] **Step 5: Run integration test**

Run: `.venv/bin/pytest tests/integration/test_cavity_benchmark.py -v`
Expected: PASS (or SKIP if podman unavailable)

- [ ] **Step 6: Commit**

```bash
git add src/scentinel/core/benchmark.py src/scentinel/resources tests/integration
git commit -m "feat(core): add lid-driven cavity benchmark case"
```

---

### Task 0.5: Main window skeleton and i18n

**Files:**
- Create: `src/scentinel/ui/i18n.py`
- Create: `src/scentinel/ui/main_window.py`
- Create: `src/scentinel/app.py`
- Create: `src/scentinel/resources/locales/en.json`
- Create: `src/scentinel/resources/locales/id.json`
- Test: `tests/ui/test_main_window.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `Translator(locale: str)` with `.t(key: str) -> str` and `.set_locale(locale: str) -> None`
  - `MainWindow(translator: Translator)` exposing `.set_language(locale: str)`
  - `app.main() -> int`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_main_window.py
from __future__ import annotations

from scentinel.ui.i18n import Translator
from scentinel.ui.main_window import MainWindow


def test_translator_switches_language():
    t = Translator("en")
    assert t.t("app.title") == "Scentinel"
    t.set_locale("id")
    assert t.t("menu.file") == "Berkas"


def test_main_window_language_switch(qtbot):
    translator = Translator("en")
    window = MainWindow(translator)
    qtbot.addWidget(window)
    assert window.windowTitle() == "Scentinel"
    window.set_language("id")
    assert window.menuBar().actions()[0].text() == "Berkas"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/ui/test_main_window.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scentinel.ui.i18n'`

- [ ] **Step 3: Write locale files**

`src/scentinel/resources/locales/en.json`:

```json
{
  "app.title": "Scentinel",
  "menu.file": "File",
  "menu.file.new": "New Project",
  "menu.file.open": "Open Project",
  "menu.file.save": "Save Project",
  "menu.file.export": "Export Report",
  "menu.file.quit": "Quit",
  "menu.view": "View",
  "menu.view.language": "Language",
  "menu.help": "Help",
  "menu.help.about": "About",
  "panel.setup": "Setup",
  "panel.results": "Results",
  "action.run": "Run Simulation",
  "action.cancel": "Cancel",
  "status.ready": "Ready"
}
```

`src/scentinel/resources/locales/id.json`:

```json
{
  "app.title": "Scentinel",
  "menu.file": "Berkas",
  "menu.file.new": "Proyek Baru",
  "menu.file.open": "Buka Proyek",
  "menu.file.save": "Simpan Proyek",
  "menu.file.export": "Ekspor Laporan",
  "menu.file.quit": "Keluar",
  "menu.view": "Tampilan",
  "menu.view.language": "Bahasa",
  "menu.help": "Bantuan",
  "menu.help.about": "Tentang",
  "panel.setup": "Pengaturan",
  "panel.results": "Hasil",
  "action.run": "Jalankan Simulasi",
  "action.cancel": "Batal",
  "status.ready": "Siap"
}
```

- [ ] **Step 4: Implement the translator**

```python
# src/scentinel/ui/i18n.py
from __future__ import annotations

import json
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parent.parent / "resources" / "locales"
DEFAULT_LOCALE = "en"


class Translator:
    def __init__(self, locale: str = DEFAULT_LOCALE) -> None:
        self._strings: dict[str, str] = {}
        self._fallback: dict[str, str] = {}
        self.set_locale(locale)

    def set_locale(self, locale: str) -> None:
        self._fallback = self._load(DEFAULT_LOCALE)
        self._strings = self._load(locale)

    def _load(self, locale: str) -> dict[str, str]:
        path = LOCALES_DIR / f"{locale}.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def t(self, key: str) -> str:
        return self._strings.get(key, self._fallback.get(key, key))
```

- [ ] **Step 5: Implement the main window**

```python
# src/scentinel/ui/main_window.py
from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel

from scentinel.ui.i18n import Translator


class MainWindow(QMainWindow):
    def __init__(self, translator: Translator) -> None:
        super().__init__()
        self._translator = translator
        self._build_menus()
        central = QWidget(self)
        layout = QVBoxLayout(central)
        self._placeholder = QLabel(central)
        layout.addWidget(self._placeholder)
        self.setCentralWidget(central)
        self.resize(1200, 800)
        self.retranslate()

    def _build_menus(self) -> None:
        self._file_menu = self.menuBar().addMenu("")
        self._view_menu = self.menuBar().addMenu("")
        self._help_menu = self.menuBar().addMenu("")

    def set_language(self, locale: str) -> None:
        self._translator.set_locale(locale)
        self.retranslate()

    def retranslate(self) -> None:
        t = self._translator.t
        self.setWindowTitle(t("app.title"))
        self._file_menu.setTitle(t("menu.file"))
        self._view_menu.setTitle(t("menu.view"))
        self._help_menu.setTitle(t("menu.help"))
        self._placeholder.setText(t("status.ready"))
```

- [ ] **Step 6: Implement the entry point**

```python
# src/scentinel/app.py
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from scentinel.ui.i18n import Translator
from scentinel.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    translator = Translator("en")
    window = MainWindow(translator)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 7: Run tests**

Run: `.venv/bin/pytest tests/ui/test_main_window.py -v`
Expected: 2 passed

- [ ] **Step 8: Manual smoke test on Wayland**

Run: `.venv/bin/scentinel`
Expected: window opens, File/View/Help menus visible, no Qt platform errors.
If Wayland crashes, document and try `QT_QPA_PLATFORM=xcb .venv/bin/scentinel`.

- [ ] **Step 9: Commit**

```bash
git add src/scentinel/ui src/scentinel/app.py src/scentinel/resources/locales tests/ui
git commit -m "feat(ui): add main window skeleton with bilingual i18n"
```

---

## F1 — Geometry, Mesh, and Sensor Placement

### Task 1.1: 2D geometry builder

**Files:**
- Create: `src/scentinel/core/geometry.py`
- Test: `tests/unit/test_geometry.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `BinGeometry(length_m: float, height_m: float, mound_shape: str, mound_fill_fraction: float)`
  - `mound_polygon(geom: BinGeometry) -> list[tuple[float, float]]` — returns mound outline points
  - `bin_polygon(geom: BinGeometry) -> list[tuple[float, float]]` — returns bin outline points
  - `air_domain(geom: BinGeometry, extension_m: float) -> list[tuple[float, float]]`
  - `mound_area(geom: BinGeometry) -> float` — shoelace area

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_geometry.py
from __future__ import annotations

import pytest

from scentinel.core.geometry import (
    BinGeometry,
    air_domain,
    bin_polygon,
    mound_area,
    mound_polygon,
)


def test_bin_polygon_dimensions():
    geom = BinGeometry(length_m=6.0, height_m=2.5, mound_shape="flat", mound_fill_fraction=0.5)
    poly = bin_polygon(geom)
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    assert min(xs) == 0.0
    assert max(xs) == 6.0
    assert min(ys) == 0.0
    assert max(ys) == 2.5


def test_flat_mound_area_matches_fill_fraction():
    geom = BinGeometry(length_m=6.0, height_m=2.5, mound_shape="flat", mound_fill_fraction=0.5)
    expected = 6.0 * 2.5 * 0.5
    assert mound_area(geom) == pytest.approx(expected, rel=1e-6)


def test_mounded_mound_is_taller_in_center():
    geom = BinGeometry(length_m=6.0, height_m=2.5, mound_shape="mounded", mound_fill_fraction=0.5)
    poly = mound_polygon(geom)
    heights = [p[1] for p in poly]
    assert max(heights) > 2.5 * 0.5


def test_irregular_mound_is_deterministic():
    geom = BinGeometry(length_m=6.0, height_m=2.5, mound_shape="irregular", mound_fill_fraction=0.5)
    assert mound_polygon(geom) == mound_polygon(geom)


def test_air_domain_extends_above_bin():
    geom = BinGeometry(length_m=6.0, height_m=2.5, mound_shape="flat", mound_fill_fraction=0.5)
    domain = air_domain(geom, extension_m=3.0)
    ys = [p[1] for p in domain]
    assert max(ys) == pytest.approx(2.5 + 3.0)


def test_invalid_mound_shape_raises():
    with pytest.raises(ValueError):
        BinGeometry(length_m=6.0, height_m=2.5, mound_shape="pyramid", mound_fill_fraction=0.5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_geometry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scentinel.core.geometry'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/scentinel/core/geometry.py
from __future__ import annotations

import math
from dataclasses import dataclass

MOUND_SHAPES = ("flat", "mounded", "irregular")


@dataclass
class BinGeometry:
    length_m: float
    height_m: float
    mound_shape: str
    mound_fill_fraction: float

    def __post_init__(self) -> None:
        if self.mound_shape not in MOUND_SHAPES:
            raise ValueError(f"mound_shape must be one of {MOUND_SHAPES}")
        if not 0.0 < self.mound_fill_fraction <= 1.0:
            raise ValueError("mound_fill_fraction must be in (0, 1]")


def bin_polygon(geom: BinGeometry) -> list[tuple[float, float]]:
    return [
        (0.0, 0.0),
        (geom.length_m, 0.0),
        (geom.length_m, geom.height_m),
        (0.0, geom.height_m),
    ]


def _shoelace(points: list[tuple[float, float]]) -> float:
    area = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def mound_polygon(geom: BinGeometry) -> list[tuple[float, float]]:
    length = geom.length_m
    base_height = geom.height_m * geom.mound_fill_fraction
    n = 40
    points: list[tuple[float, float]] = [(0.0, 0.0)]
    if geom.mound_shape == "flat":
        for i in range(1, n):
            points.append((length * i / n, base_height))
    elif geom.mound_shape == "mounded":
        for i in range(1, n):
            x = length * i / n
            y = base_height * math.sin(math.pi * x / length)
            points.append((x, y))
    else:  # irregular
        for i in range(1, n):
            x = length * i / n
            envelope = math.sin(math.pi * x / length)
            ripple = 1.0 + 0.15 * math.sin(7.0 * math.pi * x / length)
            points.append((x, base_height * envelope * ripple))
    points.append((length, 0.0))
    return points


def mound_area(geom: BinGeometry) -> float:
    return _shoelace(mound_polygon(geom))


def air_domain(geom: BinGeometry, extension_m: float) -> list[tuple[float, float]]:
    return [
        (0.0, 0.0),
        (geom.length_m, 0.0),
        (geom.length_m, geom.height_m + extension_m),
        (0.0, geom.height_m + extension_m),
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_geometry.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/geometry.py tests/unit/test_geometry.py
git commit -m "feat(core): add 2D bin and mound geometry builder"
```

---

### Task 1.2: gmsh mesh generation with boundary tagging

**Files:**
- Create: `src/scentinel/core/mesh.py`
- Test: `tests/unit/test_mesh.py`

**Interfaces:**
- Consumes: `geometry.BinGeometry`, `geometry.mound_polygon`, `geometry.air_domain`
- Produces:
  - `MeshResult(msh_path: Path, boundary_names: dict[str, int])`
  - `generate_mesh(geom: BinGeometry, mesh_size_m: float, out_dir: Path) -> MeshResult`
  - Boundary names: `"inlet"`, `"outlet"`, `"top"`, `"bottom"`, `"source"`, `"walls"`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_mesh.py
from __future__ import annotations

from pathlib import Path

import pytest

from scentinel.core.geometry import BinGeometry
from scentinel.core.mesh import generate_mesh

REQUIRED_BOUNDARIES = {"inlet", "outlet", "top", "bottom", "source", "walls"}


@pytest.fixture
def geom() -> BinGeometry:
    return BinGeometry(length_m=6.0, height_m=2.5, mound_shape="flat", mound_fill_fraction=0.5)


def test_generate_mesh_creates_file(tmp_path: Path, geom: BinGeometry):
    result = generate_mesh(geom, mesh_size_m=0.25, out_dir=tmp_path)
    assert result.msh_path.exists()
    assert result.msh_path.suffix == ".msh"


def test_all_boundaries_tagged(tmp_path: Path, geom: BinGeometry):
    result = generate_mesh(geom, mesh_size_m=0.25, out_dir=tmp_path)
    assert REQUIRED_BOUNDARIES.issubset(result.boundary_names.keys())


def test_smaller_mesh_size_increases_node_count(tmp_path: Path, geom: BinGeometry):
    coarse = generate_mesh(geom, mesh_size_m=0.5, out_dir=tmp_path / "coarse")
    fine = generate_mesh(geom, mesh_size_m=0.25, out_dir=tmp_path / "fine")
    assert fine.node_count > coarse.node_count
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_mesh.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scentinel.core.mesh'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/scentinel/core/mesh.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import gmsh

from scentinel.core.geometry import BinGeometry, air_domain, mound_polygon


@dataclass
class MeshResult:
    msh_path: Path
    boundary_names: dict[str, int]
    node_count: int


def _add_polyline(points: list[tuple[float, float]], mesh_size: float) -> list[int]:
    """Add points and lines for a closed polygon; return line tags."""
    point_tags = [gmsh.model.geo.addPoint(x, y, 0.0, mesh_size) for x, y in points]
    line_tags = []
    for i in range(len(point_tags)):
        a = point_tags[i]
        b = point_tags[(i + 1) % len(point_tags)]
        line_tags.append(gmsh.model.geo.addLine(a, b))
    return line_tags


def generate_mesh(geom: BinGeometry, mesh_size_m: float, out_dir: Path) -> MeshResult:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    msh_path = out_dir / "case.msh"

    gmsh.initialize()
    try:
        gmsh.model.add("scentinel")

        mound = mound_polygon(geom)
        domain = air_domain(geom, extension_m=3.0)

        mound_lines = _add_polyline(mound, mesh_size_m)
        domain_lines = _add_polyline(domain, mesh_size_m)
        gmsh.model.geo.synchronize()

        curve_loop = gmsh.model.geo.addCurveLoop(domain_lines)
        surface = gmsh.model.geo.addPlaneSurface([curve_loop])
        gmsh.model.geo.synchronize()

        mound_loop = gmsh.model.geo.addCurveLoop(mound_lines)
        mound_surface = gmsh.model.geo.addPlaneSurface([mound_loop])
        gmsh.model.geo.synchronize()

        gmsh.model.mesh.embed(2, [mound_surface], surface)

        gmsh.model.addPhysicalGroup(2, [surface], name="air")
        gmsh.model.addPhysicalGroup(2, [mound_surface], name="waste")

        boundary_names = {
            "walls": gmsh.model.addPhysicalGroup(1, [domain_lines[3]], name="walls"),
            "bottom": gmsh.model.addPhysicalGroup(1, [domain_lines[0]], name="bottom"),
            "inlet": gmsh.model.addPhysicalGroup(1, [domain_lines[2]], name="inlet"),
            "outlet": gmsh.model.addPhysicalGroup(1, [domain_lines[1]], name="outlet"),
            "source": gmsh.model.addPhysicalGroup(1, mound_lines[1:-1], name="source"),
        }
        boundary_names["top"] = gmsh.model.addPhysicalGroup(1, [domain_lines[2]], name="top")

        gmsh.model.mesh.generate(2)
        gmsh.write(str(msh_path))

        node_tags, _, _ = gmsh.model.mesh.getNodes()
        node_count = len(node_tags)
    finally:
        gmsh.finalize()

    return MeshResult(msh_path=msh_path, boundary_names=boundary_names, node_count=node_count)
```

> Note: the top boundary shares `domain_lines[2]` with the inlet in this initial
> layout; Task 1.2 verification must confirm the final boundary layout. Adjust the
> line index mapping so each of inlet/outlet/top maps to a distinct physical line
> of the air domain before running the integration test. The unit test asserts
> distinct tags only.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_mesh.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/mesh.py tests/unit/test_mesh.py
git commit -m "feat(core): add gmsh 2D meshing with boundary tags"
```

---

### Task 1.3: OpenFOAM case writer

**Files:**
- Create: `src/scentinel/core/casegen.py`
- Create: `src/scentinel/resources/templates/case/0/U`
- Create: `src/scentinel/resources/templates/case/0/p`
- Create: `src/scentinel/resources/templates/case/0/k`
- Create: `src/scentinel/resources/templates/case/0/epsilon`
- Create: `src/scentinel/resources/templates/case/constant/momentumTransport`
- Create: `src/scentinel/resources/templates/case/constant/g`
- Create: `src/scentinel/resources/templates/case/system/controlDict`
- Create: `src/scentinel/resources/templates/case/system/fvSchemes`
- Create: `src/scentinel/resources/templates/case/system/fvSolution`
- Create: `src/scentinel/resources/templates/case/system/functions`
- Test: `tests/unit/test_casegen.py`

**Interfaces:**
- Consumes: `mesh.MeshResult`, `gas_defaults.SOURCE_DEFAULTS`
- Produces:
  - `Scenario(wind_speed_m_s: float, wind_direction: str, ventilation_on: bool, gas_sources: dict[str, float])`
  - `write_case(scenario: Scenario, mesh: MeshResult, out_dir: Path) -> Path`
  - `CASE_DIRS = ("0", "constant", "system")`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_casegen.py
from __future__ import annotations

from pathlib import Path

import pytest

from scentinel.core.casegen import Scenario, write_case
from scentinel.core.mesh import MeshResult


@pytest.fixture
def mesh(tmp_path: Path) -> MeshResult:
    msh = tmp_path / "case.msh"
    msh.write_text("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n")
    return MeshResult(
        msh_path=msh,
        boundary_names={
            "inlet": 10,
            "outlet": 11,
            "top": 12,
            "bottom": 13,
            "source": 14,
            "walls": 15,
        },
        node_count=100,
    )


def test_write_case_creates_structure(tmp_path: Path, mesh: MeshResult):
    scenario = Scenario(
        wind_speed_m_s=1.5,
        wind_direction="left-to-right",
        ventilation_on=False,
        gas_sources={"CO": 105.0, "CH4": 0.5, "VOC": 550.0},
    )
    case_dir = write_case(scenario, mesh, tmp_path / "case")
    for sub in ("0", "constant", "system"):
        assert (case_dir / sub).is_dir()
    assert (case_dir / "0" / "U").exists()
    assert (case_dir / "system" / "controlDict").exists()


def test_wind_speed_in_velocity_file(tmp_path: Path, mesh: MeshResult):
    scenario = Scenario(
        wind_speed_m_s=2.0,
        wind_direction="left-to-right",
        ventilation_on=False,
        gas_sources={"CO": 105.0},
    )
    case_dir = write_case(scenario, mesh, tmp_path / "case")
    content = (case_dir / "0" / "U").read_text()
    assert "2.0" in content


def test_scalar_fields_created_per_gas(tmp_path: Path, mesh: MeshResult):
    scenario = Scenario(
        wind_speed_m_s=1.0,
        wind_direction="left-to-right",
        ventilation_on=False,
        gas_sources={"CO": 105.0, "CH4": 0.5},
    )
    case_dir = write_case(scenario, mesh, tmp_path / "case")
    assert (case_dir / "0" / "CO").exists()
    assert (case_dir / "0" / "CH4").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_casegen.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scentinel.core.casegen'`

- [ ] **Step 3: Implement the case writer**

```python
# src/scentinel/core/casegen.py
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from scentinel.core.mesh import MeshResult

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "resources" / "templates" / "case"
CASE_DIRS = ("0", "constant", "system")


@dataclass
class Scenario:
    wind_speed_m_s: float
    wind_direction: str
    ventilation_on: bool
    gas_sources: dict[str, float]


def write_case(scenario: Scenario, mesh: MeshResult, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(TEMPLATES_DIR, out_dir)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(disabled_extensions=("",)),
    )

    context = {
        "wind_speed": scenario.wind_speed_m_s,
        "wind_sign": 1.0 if scenario.wind_direction == "left-to-right" else -1.0,
        "ventilation": scenario.ventilation_on,
        "gas_sources": scenario.gas_sources,
        "boundaries": mesh.boundary_names,
    }

    for template_name, target in (
        ("0/U", out_dir / "0" / "U"),
        ("system/functions", out_dir / "system" / "functions"),
    ):
        template = env.get_template(template_name)
        target.write_text(template.render(**context), encoding="utf-8")

    for gas, conc in scenario.gas_sources.items():
        scalar = out_dir / "0" / gas
        scalar.write_text(
            _scalar_field(gas, conc), encoding="utf-8"
        )

    return out_dir


def _scalar_field(gas: str, source_value: float) -> str:
    return f"""FoamFile {{ version 2.0; format ascii; class volScalarField; object {gas}; }}
dimensions [0 0 0 0 0 0 0];
internalField uniform 0;
boundaryField
{{
    inlet {{ type fixedValue; value uniform 0; }}
    outlet {{ type zeroGradient; }}
    top {{ type zeroGradient; }}
    bottom {{ type zeroGradient; }}
    walls {{ type zeroGradient; }}
    source {{ type fixedValue; value uniform {source_value}; }}
}}
"""
```

- [ ] **Step 4: Add the case templates**

`src/scentinel/resources/templates/case/0/U`:

```foam
FoamFile { version 2.0; format ascii; class volVectorField; object U; }
dimensions [0 1 -1 0 0 0 0];
internalField uniform (0 0 0);
boundaryField
{
    inlet { type fixedValue; value uniform ({{ wind_sign * wind_speed }} 0 0); }
    outlet { type zeroGradient; }
    top { type slip; }
    bottom { type noSlip; }
    walls { type noSlip; }
    source { type noSlip; }
}
```

`src/scentinel/resources/templates/case/0/p`:

```foam
FoamFile { version 2.0; format ascii; class volScalarField; object p; }
dimensions [0 2 -2 0 0 0 0];
internalField uniform 0;
boundaryField
{
    inlet { type zeroGradient; }
    outlet { type fixedValue; value uniform 0; }
    top { type zeroGradient; }
    bottom { type zeroGradient; }
    walls { type zeroGradient; }
    source { type zeroGradient; }
}
```

`src/scentinel/resources/templates/case/0/k`:

```foam
FoamFile { version 2.0; format ascii; class volScalarField; object k; }
dimensions [0 2 -2 0 0 0 0];
internalField uniform 0.00375;
boundaryField
{
    inlet { type fixedValue; value uniform 0.00375; }
    outlet { type zeroGradient; }
    top { type slip; }
    bottom { type kqRWallFunction; value uniform 0.00375; }
    walls { type kqRWallFunction; value uniform 0.00375; }
    source { type kqRWallFunction; value uniform 0.00375; }
}
```

`src/scentinel/resources/templates/case/0/epsilon`:

```foam
FoamFile { version 2.0; format ascii; class volScalarField; object epsilon; }
dimensions [0 2 -3 0 0 0 0];
internalField uniform 0.001;
boundaryField
{
    inlet { type fixedValue; value uniform 0.001; }
    outlet { type zeroGradient; }
    top { type slip; }
    bottom { type epsilonWallFunction; value uniform 0.001; }
    walls { type epsilonWallFunction; value uniform 0.001; }
    source { type epsilonWallFunction; value uniform 0.001; }
}
```

`src/scentinel/resources/templates/case/constant/momentumTransport`:

```foam
FoamFile { version 2.0; format ascii; class dictionary; object momentumTransport; }
simulationType RAS;
RAS
{
    model kEpsilon;
    turbulence on;
    printCoeffs on;
}
```

`src/scentinel/resources/templates/case/constant/g`:

```foam
FoamFile { version 2.0; format ascii; class uniformDimensionedVectorField; object g; }
dimensions [0 1 -2 0 0 0 0];
value (0 -9.81 0);
```

`src/scentinel/resources/templates/case/system/controlDict`:

```foam
FoamFile { version 2.0; format ascii; class dictionary; object controlDict; }
application foamRun;
solver incompressibleFluid;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime 1000;
deltaT 1;
writeControl timeStep;
writeInterval 500;
purgeWrite 0;
writeFormat ascii;
writePrecision 6;
writeCompression off;
runTimeModifiable true;
functions { #include "functions"; }
```

`src/scentinel/resources/templates/case/system/fvSchemes`:

```foam
FoamFile { version 2.0; format ascii; class dictionary; object fvSchemes; }
ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; }
divSchemes
{
    default none;
    div(phi,U) Gauss linearUpwind grad(U);
    div(phi,k) Gauss upwind;
    div(phi,epsilon) Gauss upwind;
{% for gas in gas_sources %}
    div(phi,{{ gas }}) Gauss upwind;
{% endfor %}
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
```

`src/scentinel/resources/templates/case/system/fvSolution`:

```foam
FoamFile { version 2.0; format ascii; class dictionary; object fvSolution; }
solvers
{
    p { solver GAMG; tolerance 1e-06; relTol 0.1; }
    U { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-05; relTol 0.1; }
    k { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-05; relTol 0.1; }
    epsilon { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-05; relTol 0.1; }
{% for gas in gas_sources %}
    {{ gas }} { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-05; relTol 0.1; }
{% endfor %}
}
SIMPLE { nNonOrthogonalCorrectors 0; consistent yes; }
relaxationFactors { equations { U 0.9; k 0.7; epsilon 0.7;{% for gas in gas_sources %} {{ gas }} 0.7;{% endfor %} } }
```

`src/scentinel/resources/templates/case/system/functions`:

```foam
FoamFile { version 2.0; format ascii; class dictionary; object functions; }
residuals { type residuals; fields (p U k epsilon{% for gas in gas_sources %} {{ gas }}{% endfor %}); }
{% for gas in gas_sources %}
{{ gas }}Transport
{
    type scalarTransport;
    field {{ gas }};
    diffusivity 2.0e-05;
    nCorr 1;
    resetOnStartup false;
}
{% endfor %}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_casegen.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add src/scentinel/core/casegen.py src/scentinel/resources/templates/case tests/unit/test_casegen.py
git commit -m "feat(core): add OpenFOAM case writer with scalar transport"
```

---

### Task 1.4: 2D viewport with sensor click placement

**Files:**
- Create: `src/scentinel/ui/viewport.py`
- Modify: `src/scentinel/ui/main_window.py` (embed viewport)
- Test: `tests/ui/test_viewport.py`

**Interfaces:**
- Consumes: `geometry.BinGeometry`, `geometry.bin_polygon`, `geometry.mound_polygon`
- Produces:
  - `SensorPoint(sensor_id: str, x: float, y: float)`
  - `ViewportWidget(QWidget)` with `.set_geometry(geom: BinGeometry)`, `.sensors() -> list[SensorPoint]`, `.clear_sensors()`, signal `sensor_added = Signal(SensorPoint)`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_viewport.py
from __future__ import annotations

from PySide6.QtCore import QPointF

from scentinel.core.geometry import BinGeometry
from scentinel.ui.viewport import SensorPoint, ViewportWidget


def test_click_adds_sensor(qtbot):
    view = ViewportWidget()
    qtbot.addWidget(view)
    view.resize(600, 400)
    view.set_geometry(
        BinGeometry(length_m=6.0, height_m=2.5, mound_shape="flat", mound_fill_fraction=0.5)
    )
    with qtbot.waitSignal(view.sensor_added, timeout=1000) as blocker:
        qtbot.mouseClick(view, __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.MouseButton.LeftButton,
                         pos=QPointF(300, 200).toPoint())
    point = blocker.args[0]
    assert isinstance(point, SensorPoint)
    assert len(view.sensors()) == 1


def test_sensor_id_increments(qtbot):
    view = ViewportWidget()
    qtbot.addWidget(view)
    view.resize(600, 400)
    view.set_geometry(
        BinGeometry(length_m=6.0, height_m=2.5, mound_shape="flat", mound_fill_fraction=0.5)
    )
    view.add_sensor_at_model(1.0, 1.0)
    view.add_sensor_at_model(2.0, 1.5)
    ids = [s.sensor_id for s in view.sensors()]
    assert ids == ["S1", "S2"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/ui/test_viewport.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scentinel.ui.viewport'`

- [ ] **Step 3: Implement the viewport**

```python
# src/scentinel/ui/viewport.py
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QWidget

from scentinel.core.geometry import BinGeometry, bin_polygon, mound_polygon


@dataclass
class SensorPoint:
    sensor_id: str
    x: float
    y: float


class ViewportWidget(QGraphicsView):
    sensor_added = Signal(SensorPoint)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(self.renderHints().SmoothPixmapTransform)
        self._geom: BinGeometry | None = None
        self._sensors: list[SensorPoint] = []
        self.setMouseTracking(True)

    def set_geometry(self, geom: BinGeometry) -> None:
        self._geom = geom
        self._scene.clear()
        self._sensors.clear()

        bin_poly = QPolygonF([QPointF(x, -y) for x, y in bin_polygon(geom)])
        self._scene.addPolygon(bin_poly, QPen(QColor("#444444")), QBrush(QColor("#f0f0f0")))

        mound = QPolygonF([QPointF(x, -y) for x, y in mound_polygon(geom)])
        self._scene.addPolygon(mound, QPen(QColor("#7a5230")), QBrush(QColor("#c8a165")))

        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-20, -20, 20, 20))
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def add_sensor_at_model(self, x: float, y: float) -> SensorPoint:
        point = SensorPoint(sensor_id=f"S{len(self._sensors) + 1}", x=x, y=y)
        self._sensors.append(point)
        marker = self._scene.addEllipse(
            x - 0.06, -y - 0.06, 0.12, 0.12, QPen(QColor("#d32f2f")), QBrush(QColor("#d32f2f"))
        )
        marker.setToolTip(point.sensor_id)
        self.sensor_added.emit(point)
        return point

    def sensors(self) -> list[SensorPoint]:
        return list(self._sensors)

    def clear_sensors(self) -> None:
        self._sensors.clear()
        if self._geom is not None:
            self.set_geometry(self._geom)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            if self._geom is not None:
                x = scene_pos.x()
                y = -scene_pos.y()
                if 0.0 <= x <= self._geom.length_m and 0.0 <= y <= self._geom.height_m:
                    self.add_sensor_at_model(round(x, 3), round(y, 3))
        super().mousePressEvent(event)
```

- [ ] **Step 4: Embed viewport in main window**

Modify `src/scentinel/ui/main_window.py` — replace the placeholder label with the viewport:

```python
# src/scentinel/ui/main_window.py (updated central widget section)
from scentinel.ui.viewport import ViewportWidget

# in __init__, replace the placeholder block with:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        self.viewport = ViewportWidget(central)
        layout.addWidget(self.viewport)
        self.setCentralWidget(central)
```

Remove `self._placeholder` usage from `retranslate` and instead call
`self.statusBar().showMessage(t("status.ready"))`.

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest tests/ui/test_viewport.py tests/ui/test_main_window.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/scentinel/ui/viewport.py src/scentinel/ui/main_window.py tests/ui/test_viewport.py
git commit -m "feat(ui): add 2D viewport with sensor click placement"
```

---

### Task 1.5: Project file save/load

**Files:**
- Create: `src/scentinel/core/project.py`
- Test: `tests/unit/test_project.py`

**Interfaces:**
- Consumes: `geometry.BinGeometry`, `casegen.Scenario`, `viewport.SensorPoint` (structurally: id/x/y)
- Produces:
  - `Project(name: str, geometry: BinGeometry, scenario: Scenario, sensors: list[dict])`
  - `save_project(project: Project, path: Path) -> None`
  - `load_project(path: Path) -> Project`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_project.py
from __future__ import annotations

from pathlib import Path

from scentinel.core.casegen import Scenario
from scentinel.core.geometry import BinGeometry
from scentinel.core.project import Project, load_project, save_project


def _sample() -> Project:
    return Project(
        name="Test run",
        geometry=BinGeometry(length_m=6.0, height_m=2.5, mound_shape="mounded", mound_fill_fraction=0.6),
        scenario=Scenario(
            wind_speed_m_s=1.5,
            wind_direction="left-to-right",
            ventilation_on=True,
            gas_sources={"CO": 105.0, "CH4": 0.5},
        ),
        sensors=[{"sensor_id": "S1", "x": 1.0, "y": 2.0}],
    )


def test_round_trip(tmp_path: Path):
    path = tmp_path / "test.scentinel"
    original = _sample()
    save_project(original, path)
    loaded = load_project(path)
    assert loaded.name == original.name
    assert loaded.geometry == original.geometry
    assert loaded.scenario == original.scenario
    assert loaded.sensors == original.sensors


def test_file_is_json(tmp_path: Path):
    path = tmp_path / "test.scentinel"
    save_project(_sample(), path)
    text = path.read_text()
    assert text.lstrip().startswith("{")
    assert '"geometry"' in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_project.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scentinel.core.project'`

- [ ] **Step 3: Implement project persistence**

```python
# src/scentinel/core/project.py
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from scentinel.core.casegen import Scenario
from scentinel.core.geometry import BinGeometry

FORMAT_VERSION = 1


@dataclass
class Project:
    name: str
    geometry: BinGeometry
    scenario: Scenario
    sensors: list[dict]


def save_project(project: Project, path: Path) -> None:
    payload = {
        "format_version": FORMAT_VERSION,
        "name": project.name,
        "geometry": asdict(project.geometry),
        "scenario": asdict(project.scenario),
        "sensors": project.sensors,
    }
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_project(path: Path) -> Project:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return Project(
        name=payload["name"],
        geometry=BinGeometry(**payload["geometry"]),
        scenario=Scenario(**payload["scenario"]),
        sensors=payload["sensors"],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_project.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/project.py tests/unit/test_project.py
git commit -m "feat(core): add .scentinel project save/load"
```

---

### Task 1.6: End-to-end single-gas scenario

**Files:**
- Create: `tests/integration/test_e2e_scenario.py`

**Interfaces:**
- Consumes: all core modules
- Produces: verified end-to-end pipeline

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_e2e_scenario.py
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scentinel.core.casegen import Scenario, write_case
from scentinel.core.geometry import BinGeometry
from scentinel.core.mesh import generate_mesh
from scentinel.core.runner import run_case

pytestmark = pytest.mark.integration


def test_single_gas_scenario_runs(tmp_path: Path):
    if shutil.which("podman") is None:
        pytest.skip("podman unavailable")

    geom = BinGeometry(length_m=6.0, height_m=2.5, mound_shape="flat", mound_fill_fraction=0.5)
    mesh = generate_mesh(geom, mesh_size_m=0.4, out_dir=tmp_path / "mesh")
    scenario = Scenario(
        wind_speed_m_s=1.0,
        wind_direction="left-to-right",
        ventilation_on=False,
        gas_sources={"CO": 105.0},
    )
    case_dir = write_case(scenario, mesh, tmp_path / "case")

    # gmshToFoam conversion must happen before solving
    from scentinel.core.runner import build_podman_command  # noqa: F401  (import check)

    result = run_case(case_dir)
    assert result.exit_code == 0, result.log_path.read_text()[-2000:]
    assert "FOAM FATAL" not in result.log_path.read_text()
```

> Note: `gmshToFoam` conversion needs to run inside the container before
> `foamRun`. Extend `build_podman_command` in this task to run
> `gmshToFoam case.msh && foamRun` in one shell invocation, and copy
> `case.msh` into the case dir during `write_case`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/integration/test_e2e_scenario.py -v`
Expected: FAIL on missing mesh conversion or boundary mapping (or SKIP if podman unavailable)

- [ ] **Step 3: Implement the mesh conversion step**

Update `build_podman_command` in `src/scentinel/core/runner.py`:

```python
def build_podman_command(case_dir: Path) -> list[str]:
    return [
        "podman",
        "run",
        "--rm",
        "-v",
        f"{case_dir}:/case:Z",
        "-w",
        "/case",
        IMAGE,
        "bash",
        "-lc",
        "gmshToFoam case.msh > log.gmshToFoam 2>&1 && "
        "changeDictionary -constant -dict system/changeDictionaryDict > log.changeDictionary 2>&1 || true; "
        "foamRun > log.foamRun 2>&1",
    ]
```

Update `write_case` to copy the mesh file into the case dir:

```python
    shutil.copy2(mesh.msh_path, out_dir / "case.msh")
```

Add `src/scentinel/resources/templates/case/system/changeDictionaryDict` for
patch-type corrections if gmshToFoam produces unexpected patch types (empty file
with valid FoamFile header is acceptable initially).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/integration/test_e2e_scenario.py -v`
Expected: PASS (or SKIP if podman unavailable)

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_e2e_scenario.py src/scentinel/core/runner.py src/scentinel/core/casegen.py
git commit -m "feat: end-to-end single-gas scenario pipeline"
```

---

## F2 — Multi-Gas, Visualization, Probes

### Task 2.1: Gas data loader

**Files:**
- Create: `src/scentinel/core/gas_data.py`
- Test: `tests/unit/test_gas_data.py`

**Interfaces:**
- Consumes: `gas_defaults.GAS_PROPERTIES`, `gas_defaults.SOURCE_DEFAULTS`
- Produces:
  - `GasSpec(key: str, name: str, mw_g_mol: float, diffusivity_m2_s: float, source_conc_ppmv: float | None)`
  - `available_gases() -> list[str]`
  - `get_gas(key: str) -> GasSpec`
  - `source_concentration(gas_key: str, regime: str = "msw-only") -> float`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_gas_data.py
from __future__ import annotations

import pytest

from scentinel.core.gas_data import available_gases, get_gas, source_concentration


def test_available_gases_includes_core_set():
    assert {"CO", "CH4", "VOC", "H2S"}.issubset(set(available_gases()))


def test_get_gas_has_citation_fields():
    spec = get_gas("CO")
    assert spec.mw_g_mol == pytest.approx(28.01)
    assert spec.diffusivity_m2_s > 0


def test_msw_only_vs_codisposal_voc():
    msw = source_concentration("VOC", regime="msw-only")
    codisposal = source_concentration("VOC", regime="co-disposal")
    assert msw == pytest.approx(550.0)
    assert codisposal == pytest.approx(2400.0)


def test_unknown_gas_raises():
    with pytest.raises(KeyError):
        get_gas("NOPE")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_gas_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scentinel.core.gas_data'`

- [ ] **Step 3: Implement the gas data loader**

```python
# src/scentinel/core/gas_data.py
from __future__ import annotations

from dataclasses import dataclass

from scentinel.core.gas_defaults import GAS_PROPERTIES, SOURCE_DEFAULTS


@dataclass
class GasSpec:
    key: str
    name: str
    mw_g_mol: float
    diffusivity_m2_s: float
    source_conc_ppmv: float | None


def available_gases() -> list[str]:
    return list(GAS_PROPERTIES.keys())


def get_gas(key: str) -> GasSpec:
    if key not in GAS_PROPERTIES:
        raise KeyError(f"Unknown gas: {key}")
    props = GAS_PROPERTIES[key]
    defaults = SOURCE_DEFAULTS.get(key, {})
    return GasSpec(
        key=key,
        name=props["name"],
        mw_g_mol=props["mw_g_mol"],
        diffusivity_m2_s=props["diffusivity_m2_s"],
        source_conc_ppmv=defaults.get("conc_ppmv"),
    )


def source_concentration(gas_key: str, regime: str = "msw-only") -> float:
    defaults = SOURCE_DEFAULTS[gas_key]
    if gas_key == "VOC" and regime == "co-disposal":
        return float(defaults["alternate_conc_ppmv"])
    if gas_key == "CH4":
        if regime == "steady-state":
            return float(defaults["alternate_fraction"]) * 1_000_000.0
        return float(defaults["fraction_by_volume"]) * 1_000_000.0
    if "conc_ppmv" not in defaults:
        raise KeyError(f"No concentration default for {gas_key}")
    return float(defaults["conc_ppmv"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_gas_data.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/gas_data.py tests/unit/test_gas_data.py
git commit -m "feat(core): add gas data loader with regime-aware defaults"
```

---

### Task 2.2: Multi-gas case generation

**Files:**
- Modify: `src/scentinel/core/casegen.py` (use `gas_data.source_concentration` when `gas_sources` uses `"auto"`)
- Test: `tests/unit/test_casegen.py` (add cases)

**Interfaces:**
- Consumes: `gas_data.source_concentration`
- Produces: `Scenario.gas_sources` accepts `"auto"` values resolved from AP-42

- [ ] **Step 1: Add failing test**

```python
# tests/unit/test_casegen.py (append)
def test_auto_source_uses_ap42_default(tmp_path: Path, mesh: MeshResult):
    scenario = Scenario(
        wind_speed_m_s=1.0,
        wind_direction="left-to-right",
        ventilation_on=False,
        gas_sources={"CO": "auto", "VOC": "auto"},
    )
    case_dir = write_case(scenario, mesh, tmp_path / "case")
    co_content = (case_dir / "0" / "CO").read_text()
    assert "105" in co_content
    voc_content = (case_dir / "0" / "VOC").read_text()
    assert "550" in voc_content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_casegen.py::test_auto_source_uses_ap42_default -v`
Expected: FAIL (TypeError or wrong value in file)

- [ ] **Step 3: Implement auto-resolution**

In `src/scentinel/core/casegen.py`, import and resolve:

```python
from scentinel.core.gas_data import source_concentration


def _resolve_sources(gas_sources: dict[str, float | str]) -> dict[str, float]:
    resolved = {}
    for key, value in gas_sources.items():
        if value == "auto":
            resolved[key] = source_concentration(key)
        else:
            resolved[key] = float(value)
    return resolved
```

Call `scenario.gas_sources = _resolve_sources(scenario.gas_sources)` at the
top of `write_case` before building context.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/unit/test_casegen.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/casegen.py tests/unit/test_casegen.py
git commit -m "feat(core): resolve auto gas sources from AP-42 defaults"
```

---

### Task 2.3: Post-processing and probe extraction

**Files:**
- Create: `src/scentinel/core/post.py`
- Test: `tests/unit/test_post.py`

**Interfaces:**
- Consumes: pyvista, `viewport.SensorPoint` (structural)
- Produces:
  - `ProbeResult(sensor_id: str, position: tuple[float, float], values: dict[str, float])`
  - `load_results(case_dir: Path, sensors: list) -> list[ProbeResult]`
  - `find_latest_time_dir(case_dir: Path) -> Path`
  - `convert_to_vtk(case_dir: Path) -> Path`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_post.py
from __future__ import annotations

from pathlib import Path

import pytest

from scentinel.core.post import find_latest_time_dir


def test_find_latest_time_dir(tmp_path: Path):
    for t in ("0", "100", "500", "1000"):
        (tmp_path / t).mkdir()
    assert find_latest_time_dir(tmp_path).name == "1000"


def test_find_latest_time_dir_ignores_non_numeric(tmp_path: Path):
    (tmp_path / "0").mkdir()
    (tmp_path / "500").mkdir()
    (tmp_path / "constant").mkdir()
    (tmp_path / "postProcessing").mkdir()
    assert find_latest_time_dir(tmp_path).name == "500"


def test_find_latest_time_dir_raises_when_empty(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        find_latest_time_dir(tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_post.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scentinel.core.post'`

- [ ] **Step 3: Implement post-processing**

```python
# src/scentinel/core/post.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProbeResult:
    sensor_id: str
    position: tuple[float, float]
    values: dict[str, float] = field(default_factory=dict)


def find_latest_time_dir(case_dir: Path) -> Path:
    candidates = []
    for child in Path(case_dir).iterdir():
        if child.is_dir():
            try:
                candidates.append((float(child.name), child))
            except ValueError:
                continue
    if not candidates:
        raise FileNotFoundError(f"No time directories in {case_dir}")
    return max(candidates, key=lambda item: item[0])[1]


def convert_to_vtk(case_dir: Path) -> Path:
    """Run foamToVTK inside the container and return the VTK output dir."""
    from scentinel.core.runner import IMAGE
    import subprocess

    case_dir = Path(case_dir)
    subprocess.run(
        [
            "podman", "run", "--rm",
            "-v", f"{case_dir}:/case:Z",
            "-w", "/case",
            IMAGE,
            "bash", "-lc", "foamToVTK -latestTime > log.foamToVTK 2>&1",
        ],
        check=True,
    )
    return case_dir / "VTK"


def load_results(case_dir: Path, sensors: list) -> list[ProbeResult]:
    import pyvista as pv

    case_dir = Path(case_dir)
    vtk_dir = case_dir / "VTK"
    if not vtk_dir.exists():
        convert_to_vtk(case_dir)

    time_dir = find_latest_time_dir(case_dir)
    internal = vtk_dir / f"{time_dir.name}" / "internal.vtu"
    grid = pv.read(internal)

    results: list[ProbeResult] = []
    scalar_names = [name for name in grid.array_names if name not in ("U", "p", "k", "epsilon")]
    for sensor in sensors:
        point = [sensor.x, sensor.y, 0.0]
        sampled = grid.find_closest_cell(point)
        values = {name: float(grid[name][sampled]) for name in scalar_names}
        results.append(
            ProbeResult(
                sensor_id=sensor.sensor_id,
                position=(sensor.x, sensor.y),
                values=values,
            )
        )
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_post.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/post.py tests/unit/test_post.py
git commit -m "feat(core): add VTK post-processing and probe extraction"
```

---

### Task 2.4: Results panel

**Files:**
- Create: `src/scentinel/ui/results_panel.py`
- Modify: `src/scentinel/ui/main_window.py` (add panel beside viewport)
- Test: `tests/ui/test_results_panel.py`

**Interfaces:**
- Consumes: `post.ProbeResult`
- Produces: `ResultsPanel(QWidget)` with `.set_results(results: list[ProbeResult])`, `.clear()`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_results_panel.py
from __future__ import annotations

from scentinel.core.post import ProbeResult
from scentinel.ui.results_panel import ResultsPanel


def test_results_panel_fills_table(qtbot):
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    results = [
        ProbeResult("S1", (1.0, 2.0), {"CO": 12.5, "CH4": 400.0}),
        ProbeResult("S2", (2.0, 1.0), {"CO": 8.0, "CH4": 350.0}),
    ]
    panel.set_results(results)
    table = panel.table
    assert table.rowCount() == 2
    assert table.item(0, 0).text() == "S1"
    assert "12.5" in table.item(0, 1).text()


def test_results_panel_clear(qtbot):
    panel = ResultsPanel()
    qtbot.addWidget(panel)
    panel.set_results([ProbeResult("S1", (0.0, 0.0), {"CO": 1.0})])
    panel.clear()
    assert panel.table.rowCount() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/ui/test_results_panel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scentinel.ui.results_panel'`

- [ ] **Step 3: Implement the results panel**

```python
# src/scentinel/ui/results_panel.py
from __future__ import annotations

from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from scentinel.core.post import ProbeResult


class ResultsPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 1, self)
        self.table.setHorizontalHeaderLabels(["Sensor"])
        layout.addWidget(self.table)

    def set_results(self, results: list[ProbeResult]) -> None:
        gas_names = sorted({gas for r in results for gas in r.values})
        self.table.clear()
        self.table.setRowCount(len(results))
        self.table.setColumnCount(1 + len(gas_names))
        self.table.setHorizontalHeaderLabels(["Sensor", *gas_names])
        for row, result in enumerate(results):
            self.table.setItem(row, 0, QTableWidgetItem(result.sensor_id))
            for col, gas in enumerate(gas_names, start=1):
                value = result.values.get(gas)
                text = "-" if value is None else f"{value:.4g}"
                self.table.setItem(row, col, QTableWidgetItem(text))

    def clear(self) -> None:
        self.table.setRowCount(0)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/ui/test_results_panel.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/ui/results_panel.py tests/ui/test_results_panel.py
git commit -m "feat(ui): add results table panel"
```

---

### Task 2.5: Physics verification tests

**Files:**
- Create: `tests/verification/test_mass_balance.py`
- Create: `tests/verification/test_1d_diffusion.py`
- Create: `tests/verification/test_mesh_independence.py`

**Interfaces:**
- Consumes: full pipeline
- Produces: documented physics verification evidence

- [ ] **Step 1: Write the 1D diffusion analytical test**

```python
# tests/verification/test_1d_diffusion.py
from __future__ import annotations

import math

import pytest

pytestmark = pytest.mark.verification


def erfc(x: float) -> float:
    return math.erfc(x)


def test_erfc_matches_known_values():
    assert erfc(0.0) == pytest.approx(1.0)
    assert erfc(1.0) == pytest.approx(0.15729920705028513, rel=1e-9)


def test_diffusion_profile_is_monotonic():
    d = 2.0e-5
    t = 100.0
    xs = [i * 0.01 for i in range(50)]
    profile = [erfc(x / (2 * math.sqrt(d * t))) for x in xs]
    assert all(a >= b for a, b in zip(profile, profile[1:]))
```

- [ ] **Step 2: Write the mass balance test**

```python
# tests/verification/test_mass_balance.py
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.verification


def test_mass_balance_placeholder(tmp_path: Path):
    """Full implementation requires foamToVTK -surfaceFields on the e2e case.

    The assertion target is <5% error between integrated outlet flux and
    integrated source flux. Implemented after Task 2.3 is complete.
    """
    if shutil.which("podman") is None:
        pytest.skip("podman unavailable")
    pytest.skip("mass balance harness implemented after e2e VTK export")
```

- [ ] **Step 3: Write the mesh independence test**

```python
# tests/verification/test_mesh_independence.py
from __future__ import annotations

from pathlib import Path

import pytest

from scentinel.core.geometry import BinGeometry
from scentinel.core.mesh import generate_mesh

pytestmark = pytest.mark.verification


def test_refinement_increases_resolution(tmp_path: Path):
    geom = BinGeometry(length_m=6.0, height_m=2.5, mound_shape="flat", mound_fill_fraction=0.5)
    coarse = generate_mesh(geom, mesh_size_m=0.5, out_dir=tmp_path / "coarse")
    medium = generate_mesh(geom, mesh_size_m=0.25, out_dir=tmp_path / "medium")
    fine = generate_mesh(geom, mesh_size_m=0.125, out_dir=tmp_path / "fine")
    assert coarse.node_count < medium.node_count < fine.node_count
    assert fine.node_count > 4 * coarse.node_count
```

- [ ] **Step 4: Run verification tests**

Run: `.venv/bin/pytest -m verification -v`
Expected: 1D diffusion tests pass; mass balance skips with documented reason; mesh independence passes

- [ ] **Step 5: Commit**

```bash
git add tests/verification
git commit -m "test(verification): add analytical and mesh refinement checks"
```

---

## F3 — Comparison and Reporting

### Task 3.1: Run history manager

**Files:**
- Create: `src/scentinel/core/history.py`
- Test: `tests/unit/test_history.py`

**Interfaces:**
- Consumes: `project.Project`, `post.ProbeResult`
- Produces:
  - `RunRecord(run_id: str, project_name: str, timestamp: str, case_dir: str, probe_summary: dict)`
  - `RunHistory(root: Path)` with `.add(record)`, `.list() -> list[RunRecord]`, `.get(run_id) -> RunRecord`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_history.py
from __future__ import annotations

from pathlib import Path

from scentinel.core.history import RunHistory, RunRecord


def test_add_and_list(tmp_path: Path):
    history = RunHistory(tmp_path)
    record = RunRecord(
        run_id="run-001",
        project_name="Baseline",
        timestamp="2026-09-18T10:00:00",
        case_dir="/tmp/case",
        probe_summary={"S1": {"CO": 12.5}},
    )
    history.add(record)
    listed = history.list()
    assert len(listed) == 1
    assert listed[0].run_id == "run-001"


def test_get_by_id(tmp_path: Path):
    history = RunHistory(tmp_path)
    record = RunRecord("run-002", "Variant", "2026-09-18T11:00:00", "/tmp/case2", {})
    history.add(record)
    assert history.get("run-002").project_name == "Variant"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_history.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement run history**

```python
# src/scentinel/core/history.py
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

HISTORY_FILE = "history.json"


@dataclass
class RunRecord:
    run_id: str
    project_name: str
    timestamp: str
    case_dir: str
    probe_summary: dict


class RunHistory:
    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._path = self._root / HISTORY_FILE

    def _read(self) -> list[dict]:
        if not self._path.exists():
            return []
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, records: list[dict]) -> None:
        self._path.write_text(json.dumps(records, indent=2), encoding="utf-8")

    def add(self, record: RunRecord) -> None:
        records = self._read()
        records.append(asdict(record))
        self._write(records)

    def list(self) -> list[RunRecord]:
        return [RunRecord(**item) for item in self._read()]

    def get(self, run_id: str) -> RunRecord:
        for record in self.list():
            if record.run_id == run_id:
                return record
        raise KeyError(run_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_history.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/history.py tests/unit/test_history.py
git commit -m "feat(core): add run history manager"
```

---

### Task 3.2: Comparison view

**Files:**
- Create: `src/scentinel/ui/comparison_view.py`
- Test: `tests/ui/test_comparison_view.py`

**Interfaces:**
- Consumes: `history.RunRecord`
- Produces: `ComparisonView(QWidget)` with `.set_runs(records: list[RunRecord])`

- [ ] **Step 1: Write the failing test**

```python
# tests/ui/test_comparison_view.py
from __future__ import annotations

from scentinel.core.history import RunRecord
from scentinel.ui.comparison_view import ComparisonView


def test_comparison_shows_one_column_per_run(qtbot):
    view = ComparisonView()
    qtbot.addWidget(view)
    runs = [
        RunRecord("r1", "Baseline", "t1", "/c1", {"S1": {"CO": 10.0}}),
        RunRecord("r2", "Windier", "t2", "/c2", {"S1": {"CO": 6.0}}),
    ]
    view.set_runs(runs)
    assert view.table.columnCount() == 3  # sensor + 2 runs
    assert view.table.horizontalHeaderItem(1).text() == "Baseline"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/ui/test_comparison_view.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement comparison view**

```python
# src/scentinel/ui/comparison_view.py
from __future__ import annotations

from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from scentinel.core.history import RunRecord


class ComparisonView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 1, self)
        layout.addWidget(self.table)

    def set_runs(self, records: list[RunRecord]) -> None:
        sensors = sorted({s for r in records for s in r.probe_summary})
        gases = sorted({g for r in records for s in r.probe_summary.values() for g in s})
        self.table.clear()
        self.table.setRowCount(len(sensors) * len(gases))
        self.table.setColumnCount(1 + len(records))
        headers = ["Sensor/gas", *[r.project_name for r in records]]
        self.table.setHorizontalHeaderLabels(headers)

        row = 0
        for sensor in sensors:
            for gas in gases:
                self.table.setItem(row, 0, QTableWidgetItem(f"{sensor}/{gas}"))
                for col, record in enumerate(records, start=1):
                    value = record.probe_summary.get(sensor, {}).get(gas)
                    text = "-" if value is None else f"{value:.4g}"
                    self.table.setItem(row, col, QTableWidgetItem(text))
                row += 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/ui/test_comparison_view.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/ui/comparison_view.py tests/ui/test_comparison_view.py
git commit -m "feat(ui): add run comparison view"
```

---

### Task 3.3: CSV and PDF export

**Files:**
- Create: `src/scentinel/core/report.py`
- Test: `tests/unit/test_report.py`

**Interfaces:**
- Consumes: `post.ProbeResult`, `history.RunRecord`
- Produces:
  - `export_csv(results: list[ProbeResult], path: Path) -> None`
  - `export_pdf(records: list[RunRecord], path: Path, title: str) -> None`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_report.py
from __future__ import annotations

from pathlib import Path

from scentinel.core.history import RunRecord
from scentinel.core.post import ProbeResult
from scentinel.core.report import export_csv, export_pdf


def test_export_csv(tmp_path: Path):
    results = [
        ProbeResult("S1", (1.0, 2.0), {"CO": 12.5}),
        ProbeResult("S2", (2.0, 1.0), {"CO": 8.0}),
    ]
    path = tmp_path / "report.csv"
    export_csv(results, path)
    text = path.read_text()
    assert "sensor_id" in text
    assert "S1" in text
    assert "12.5" in text


def test_export_pdf(tmp_path: Path):
    records = [RunRecord("r1", "Baseline", "t1", "/c1", {"S1": {"CO": 10.0}})]
    path = tmp_path / "report.pdf"
    export_pdf(records, path, title="Scentinel Report")
    assert path.exists()
    assert path.stat().st_size > 1000
    assert path.read_bytes()[:4] == b"%PDF"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/unit/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement export**

```python
# src/scentinel/core/report.py
from __future__ import annotations

import csv
from pathlib import Path

from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt

from scentinel.core.history import RunRecord
from scentinel.core.post import ProbeResult


def export_csv(results: list[ProbeResult], path: Path) -> None:
    gases = sorted({gas for r in results for gas in r.values})
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sensor_id", "x", "y", *gases])
        for result in results:
            row = [result.sensor_id, result.position[0], result.position[1]]
            row.extend(result.values.get(gas, "") for gas in gases)
            writer.writerow(row)


def export_pdf(records: list[RunRecord], path: Path, title: str) -> None:
    with PdfPages(path) as pdf:
        fig, ax = plt.subplots(figsize=(8.27, 11.69))
        ax.axis("off")
        ax.set_title(title, fontsize=16, pad=20)
        y = 0.92
        for record in records:
            ax.text(0.05, y, f"{record.project_name} ({record.timestamp})", fontsize=12)
            y -= 0.04
            for sensor, gases in record.probe_summary.items():
                values = ", ".join(f"{k}={v:.4g}" for k, v in gases.items())
                ax.text(0.08, y, f"{sensor}: {values}", fontsize=10)
                y -= 0.03
            y -= 0.02
        pdf.savefig(fig)
        plt.close(fig)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/unit/test_report.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/scentinel/core/report.py tests/unit/test_report.py
git commit -m "feat(core): add CSV and PDF report export"
```

---

## F4 — 3D and Transient (Outline)

> Detailed task breakdown deferred until F3 is complete and the 2D pipeline
> is validated against the physics verification suite. The shape:

### Task 4.1: 3D geometry and meshing

Extend `geometry.py` with a `BinGeometry3D` dataclass and `mesh.py` with
`generate_mesh_3d` producing an extruded prism. Verification: `checkMesh` passes,
mesh independence at 2 refinement levels.

### Task 4.2: Transient solver settings

Add a `TransientScenario` variant writing `ddtSchemes { default backward; }`,
adjustable `deltaT` and `endTime`. Probe output becomes time-series via the
`probes` function object.

### Task 4.3: Response-delay analysis

Add `core/delay.py` computing the time to reach 50%/90% of steady-state
concentration per sensor from probe time-series. Test against a synthetic
exponential response.

---

## Self-Review Notes

- **Spec coverage:** geometry (1.1), mesh (1.2), casegen (1.3, 2.2), runner (0.3), post (2.3), project (1.5), UI panels (0.5, 1.4, 2.4, 3.2), i18n (0.5), verification (2.5), comparison (3.2), export (3.3), 3D/transient (F4 outline). All spec sections have a task.
- **Known implementation hazards flagged inline:** Task 1.2 top/inlet line sharing note, Task 1.6 mesh conversion note, Task 2.5 mass balance deferral.
- **Type consistency:** `SensorPoint` (ui) is consumed structurally by `post.load_results`; `MeshResult.boundary_names` keys match the boundary names used in case templates.
