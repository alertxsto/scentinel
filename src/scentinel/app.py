"""Scentinel entry point: builds the QApplication and shows the main window."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from scentinel import __version__
from scentinel.core.project import load_project
from scentinel.ui.i18n import DEFAULT_LOCALE, Translator
from scentinel.ui.home_window import HomeWindow
from scentinel.ui.theme import APP_STYLE

def _package_smoke_test() -> int:
    """Load native release dependencies without starting the GUI."""
    import gmsh
    import numpy
    import pyvista
    import vtk

    vtk_version = vtk.vtkVersion.GetVTKVersion()
    print(
        f"Scentinel {__version__} package runtime OK: "
        f"Python {sys.version_info.major}.{sys.version_info.minor}, "
        f"NumPy {numpy.__version__}, PyVista {pyvista.__version__}, "
        f"VTK {vtk_version}, gmsh {gmsh.__version__}"
    )
    return 0



def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv if argv is None else argv)
    if args[1:] == ["--package-smoke-test"]:
        return _package_smoke_test()
    app = QApplication(args)
    app.setApplicationName("Scentinel")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Scentinel")
    app.setStyleSheet(APP_STYLE)

    translator = Translator(DEFAULT_LOCALE)
    project = None
    path = None
    if len(args) > 1 and Path(args[1]).suffix == ".scentinel":
        candidate = Path(args[1])
        if candidate.exists():
            project = load_project(candidate)
            path = candidate

    window = HomeWindow(translator, project=project, path=path)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
