"""Run OpenFOAM cases inside the Podman container and stream the log.

The container does all of the work: mesh conversion, patch-type correction, the
solve, and the VTK export. Each stage writes its own log file next to the case
so a failure can be read back without re-running.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from scentinel.core import container
from scentinel.core.casegen import FOAM_BASHRC, IMAGE, SOLVER

#: Case directory as seen from inside the container.
CONTAINER_CASE = "/case"

#: Shell pipeline executed inside the container, in order.
#:
#: Two details are load-bearing. The ``source`` line is required because the
#: image's entrypoint leaves a non-interactive shell without the OpenFOAM
#: environment on PATH. The ``cd`` is required because that entrypoint also
#: lands the shell in ``/home/openfoam``, so ``-w`` on ``podman run`` does not
#: survive.
SOLVER_SCRIPT = (
    f"source {FOAM_BASHRC} || exit 9; "
    "set -o pipefail; "
    f"cd {CONTAINER_CASE} || exit 10; "
    "gmshToFoam case.msh > log.gmshToFoam 2>&1 || exit 11; "
    "changeDictionary -constant -dict system/changeDictionaryDict "
    "> log.changeDictionary 2>&1 || exit 12; "
    f"{SOLVER} > log.{SOLVER} 2>&1 || exit 13; "
    "foamToVTK -latestTime > log.foamToVTK 2>&1 || exit 14; "
    "exit 0"
)

EXIT_STAGE = {
    9: "source",
    10: "cd",
    11: "gmshToFoam",
    12: "changeDictionary",
    13: "solver",
    14: "foamToVTK",
}

#: Pipeline for a case whose mesh comes from ``blockMesh`` rather than gmsh.
#:
#: The verification benchmarks build minimal ducts by hand so that they do not
#: depend on the case generator they are meant to validate; feeding those
#: through the gmsh pipeline would convert a mesh file that does not exist.
BLOCKMESH_SCRIPT = (
    f"source {FOAM_BASHRC} || exit 9; "
    "set -o pipefail; "
    f"cd {CONTAINER_CASE} || exit 10; "
    "blockMesh > log.blockMesh 2>&1 || exit 11; "
    f"{SOLVER} > log.{SOLVER} 2>&1 || exit 13; "
    "foamToVTK -latestTime > log.foamToVTK 2>&1 || exit 14; "
    "exit 0"
)

BLOCKMESH_EXIT_STAGE = {
    9: "source",
    10: "cd",
    11: "blockMesh",
    13: "solver",
    14: "foamToVTK",
}


@dataclass
class RunResult:
    """Outcome of a solver run."""

    case_dir: Path
    exit_code: int
    log_path: Path

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    @property
    def failed_stage(self) -> str | None:
        """Which container stage failed, when the exit code identifies one."""
        return EXIT_STAGE.get(self.exit_code)


def podman_available() -> bool:
    """True when podman is on PATH. Thin alias of :mod:`container`'s check."""
    return container.podman_available()


def image_available(image: str = IMAGE) -> bool:
    """True when the solver image is already pulled locally.

    Delegates to :mod:`scentinel.core.container`, which is the single place
    that knows the isolated storage config every podman call must use.
    """
    return container.image_available(image)


def build_podman_command(
    case_dir: Path, image: str = IMAGE, *, script: str = SOLVER_SCRIPT
) -> list[str]:
    """Podman invocation that runs ``script`` for ``case_dir``.

    ``script`` defaults to the gmsh pipeline; the verification benchmarks pass
    :data:`BLOCKMESH_SCRIPT` for cases they mesh with ``blockMesh``.
    """
    return [
        "podman",
        "run",
        "--rm",
        "--userns=keep-id",
        "-v",
        f"{Path(case_dir).resolve()}:{CONTAINER_CASE}:Z",
        "-w",
        CONTAINER_CASE,
        image,
        "bash",
        "-lc",
        script,
    ]


def run_case(
    case_dir: Path,
    on_log: Callable[[str], None] | None = None,
    cancel: threading.Event | None = None,
    *,
    image: str = IMAGE,
    timeout_s: float | None = None,
    command_override: Iterable[str] | None = None,
    script: str = SOLVER_SCRIPT,
) -> RunResult:
    """Run the case, streaming output line by line.

    ``command_override`` replaces the podman invocation; the unit tests use it
    to exercise streaming and cancellation without a container.

    ``script`` selects the in-container pipeline. The default is the gmsh
    pipeline the app uses; ``BLOCKMESH_SCRIPT`` is for benchmark cases that
    build their own mesh.

    Cancellation kills the whole process group: ``podman run`` spawns a
    container whose process tree would otherwise survive a bare
    ``terminate()`` on the direct child.
    """
    case_dir = Path(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    log_path = case_dir / "scentinel_run.log"

    command = (
        list(command_override)
        if command_override is not None
        else build_podman_command(case_dir, image, script=script)
    )

    if cancel is not None and cancel.is_set():
        log_path.write_text("cancelled before start\n", encoding="utf-8")
        return RunResult(case_dir=case_dir, exit_code=-2, log_path=log_path)

    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,  # own process group, so we can kill the tree
            # The container storage must stay inside the app home even for
            # overridden commands: the override replaces the argv, not the
            # environment a podman process would inherit.
            env=container.podman_env(),
        )
        assert process.stdout is not None
        try:
            for line in process.stdout:
                log_file.write(line)
                log_file.flush()
                if on_log is not None:
                    on_log(line.rstrip("\n"))
                if cancel is not None and cancel.is_set():
                    _kill_tree(process)
                    break
            exit_code = process.wait(timeout=timeout_s)
        finally:
            process.stdout.close()

    if cancel is not None and cancel.is_set() and exit_code == 0:
        exit_code = -2
    return RunResult(case_dir=case_dir, exit_code=exit_code, log_path=log_path)


def _kill_tree(process: subprocess.Popen) -> None:
    """Terminate the child and everything it spawned."""
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()
        process.wait()


def read_log(result: RunResult, tail_lines: int = 40) -> str:
    """Last lines of the run log, for showing in the UI."""
    if not result.log_path.exists():
        return ""
    lines = result.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-tail_lines:])


def stage_log(case_dir: Path, stage: str) -> str:
    """Contents of one container stage log (``gmshToFoam``, ``foamRun``, …)."""
    path = Path(case_dir) / f"log.{stage}"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")
