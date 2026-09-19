"""Background solver worker: meshing, case writing, solving, and sampling.

Everything runs off the GUI thread. The worker owns its own run directory so a
cancelled or failed run never leaves the project in a partial state.

Meshing is delegated to a child process rather than run in this thread: gmsh
installs a ``SIGINT`` handler during ``initialize()``, and Python only allows
that on the main thread of the main interpreter. A spawned process sidesteps
the restriction and keeps the GIL free for the UI.
"""

from __future__ import annotations

import multiprocessing
import queue as queue_module
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from scentinel.core import casegen, mesh, post, runner
from scentinel.core.geometry import BinGeometry
from scentinel.core.project import Project


@dataclass
class RunOutcome:
    """Everything a finished run produced."""

    case_dir: Path | None = None
    readings: list[post.SensorReading] = field(default_factory=list)
    mesh_cells: int = 0
    element_types: dict[str, int] = field(default_factory=dict)
    exit_code: int | None = None
    failed_stage: str | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and self.exit_code == 0


#: How long a meshing child may take before it is killed.
MESH_TIMEOUT_S = 600.0


def _start_method() -> str:
    """Pick a multiprocessing start method that can actually re-import __main__.

    ``spawn`` is the safer default because it gives the child a clean
    interpreter, but it re-imports ``__main__`` by path, which raises when the
    program was launched from a stream (``python -``, an embedded interpreter,
    a notebook) and ``__main__`` has no file. ``fork`` has no such requirement.
    """
    main_path = getattr(sys.modules.get("__main__"), "__file__", None)
    if main_path and Path(main_path).exists():
        return "spawn"
    return "fork"


def _mesh_in_child(
    geom: BinGeometry, mesh_size_m: float, out_dir: str, queue
) -> None:
    """Child-process entry point: mesh and return a summary or the error.

    Defined at module level so the spawn start method can pickle it.
    """
    try:
        result = mesh.generate_mesh(geom, mesh_size_m, Path(out_dir))
        queue.put(
            (
                "ok",
                {
                    "msh_path": str(result.msh_path),
                    "patches": result.patches,
                    "node_count": result.node_count,
                    "cell_count": result.cell_count,
                    "element_types": result.element_types,
                    "mesh_size_m": result.mesh_size_m,
                },
            )
        )
    except Exception as error:  # reported back to the UI thread
        queue.put(("error", f"{type(error).__name__}: {error}"))


class SolverWorker(QObject):
    """Runs the full pipeline for one project and reports progress."""

    log_message = Signal(str)
    progress = Signal(int, str)  # percent, stage key
    finished = Signal(object)  # RunOutcome

    def __init__(
        self,
        project: Project,
        run_dir: Path,
        *,
        mesh_size_m: float = 0.25,
        end_time: int = 500,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._project = project
        self._run_dir = Path(run_dir)
        self._mesh_size_m = mesh_size_m
        self._end_time = end_time
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        outcome = RunOutcome()
        try:
            outcome = self._run_pipeline()
        except Exception as error:  # surfaced to the UI, never swallowed
            outcome.error = f"{type(error).__name__}: {error}"
            self.log_message.emit(traceback.format_exc())
        self.finished.emit(outcome)

    # -- pipeline ------------------------------------------------------------

    def _run_pipeline(self) -> RunOutcome:
        project = self._project
        self.progress.emit(5, "mesh")
        self.log_message.emit(f"Meshing at {self._mesh_size_m:g} m ...")
        result = self._mesh(project.geometry)
        self.log_message.emit(
            f"Mesh: {result.cell_count} cells ({result.element_types}), "
            f"{result.node_count} nodes"
        )
        if not result.is_predominantly_hexahedral:
            self.log_message.emit(
                f"Warning: only {result.hex_fraction:.0%} of cells are hex; "
                f"checkMesh may complain about {result.element_types}"
            )

        if self._cancelled():
            return self._cancelled_outcome(result)

        self.progress.emit(20, "case")
        self.log_message.emit("Writing OpenFOAM case ...")
        case_dir = casegen.write_case(
            project.scenario,
            result,
            self._run_dir / "case",
            geom=project.geometry,
            end_time=self._end_time,
        )
        self.log_message.emit(f"Case: {case_dir}")

        if not runner.podman_available():
            return RunOutcome(
                case_dir=case_dir,
                mesh_cells=result.cell_count,
                element_types=result.element_types,
                error="podman is not installed",
            )
        if not runner.image_available():
            return RunOutcome(
                case_dir=case_dir,
                mesh_cells=result.cell_count,
                element_types=result.element_types,
                error=f"container image {casegen.IMAGE} is not pulled",
            )

        if self._cancelled():
            return self._cancelled_outcome(result)

        self.progress.emit(35, "solve")
        self.log_message.emit("Solving in the OpenFOAM container ...")
        run = runner.run_case(case_dir, on_log=self.log_message.emit, cancel=self._cancel)
        self.log_message.emit(f"Solver exited with {run.exit_code}")
        if run.failed_stage:
            self.log_message.emit(f"Failed stage: {run.failed_stage}")
            self.log_message.emit(runner.stage_log(case_dir, run.failed_stage)[-2000:])

        outcome = RunOutcome(
            case_dir=case_dir,
            mesh_cells=result.cell_count,
            element_types=result.element_types,
            exit_code=run.exit_code,
            failed_stage=run.failed_stage,
        )
        if not run.ok:
            return outcome

        if project.sensors:
            self.progress.emit(90, "sample")
            self.log_message.emit(f"Sampling {len(project.sensors)} sensor(s) ...")
            outcome.readings = post.sample_sensors(case_dir, project.sensors)
            for reading in outcome.readings:
                summary = ", ".join(
                    f"{gas}={value * 1e6:.3f} ppmv" for gas, value in reading.values.items()
                )
                self.log_message.emit(f"  {reading.sensor_id}: {summary or 'no scalar fields'}")

        self.progress.emit(100, "done")
        return outcome

    def _mesh(self, geom: BinGeometry) -> mesh.MeshResult:
        """Run gmsh in a child process and rebuild the result here.

        gmsh cannot initialise outside the main thread, so the work is spawned;
        only plain data crosses back.

        ``spawn`` is preferred, but it re-imports ``__main__``, which fails when
        the app was started from a stream (``python -`` or an embedded
        interpreter) where ``__main__`` has no real path. ``fork`` is the
        fallback there; it is safe because the child touches only gmsh and the
        filesystem, never Qt.
        """
        context = multiprocessing.get_context(_start_method())
        queue = context.Queue()
        process = context.Process(
            target=_mesh_in_child,
            args=(geom, self._mesh_size_m, str(self._run_dir / "mesh"), queue),
            daemon=True,
        )
        process.start()

        status: str | None = None
        payload: object = None
        deadline = time.monotonic() + MESH_TIMEOUT_S
        while status is None:
            try:
                status, payload = queue.get(timeout=0.25)
            except queue_module.Empty:
                if not process.is_alive():
                    # Died without reporting: do not block on the queue.
                    process.join(timeout=5)
                    raise RuntimeError(
                        f"meshing process exited with code {process.exitcode} "
                        "before reporting a result"
                    )
                if time.monotonic() > deadline:
                    process.terminate()
                    raise RuntimeError(f"meshing timed out after {MESH_TIMEOUT_S:.0f} s")
        process.join(timeout=30)
        if status == "error":
            raise RuntimeError(payload)
        return mesh.MeshResult(**payload)

    def _cancelled(self) -> bool:
        return self._cancel.is_set()

    def _cancelled_outcome(self, result: mesh.MeshResult) -> RunOutcome:
        self.log_message.emit("Cancelled.")
        return RunOutcome(
            case_dir=None,
            mesh_cells=result.cell_count,
            element_types=result.element_types,
            exit_code=-2,
        )


class SolverThread(QThread):
    """QThread wrapper so the worker can be started and cancelled from the GUI."""

    def __init__(self, worker: SolverWorker) -> None:
        super().__init__()
        self._worker = worker
        worker.moveToThread(self)

    def run(self) -> None:
        self._worker.run()

    def cancel(self) -> None:
        self._worker.cancel()
