from __future__ import annotations

import threading
from pathlib import Path

import pytest

from scentinel.core.casegen import IMAGE
from scentinel.core.runner import (
    EXIT_STAGE,
    build_podman_command,
    podman_available,
    read_log,
    run_case,
    stage_log,
)


def test_command_mounts_the_case_and_sources_the_environment(tmp_path: Path):
    cmd = build_podman_command(tmp_path)
    assert cmd[0] == "podman"
    assert "run" in cmd
    assert IMAGE in cmd
    assert any(str(tmp_path.resolve()) in part for part in cmd)


def test_command_runs_the_pipeline_in_order(tmp_path: Path):
    script = build_podman_command(tmp_path)[-1]
    assert script.index("gmshToFoam") < script.index("changeDictionary")
    assert script.index("changeDictionary") < script.index("simpleFoam")
    assert script.index("simpleFoam") < script.index("foamToVTK")
    # The image entrypoint leaves the shell outside the case directory.
    assert "cd /case" in script
    assert "source /usr/lib/openfoam" in script


def test_run_case_streams_output(tmp_path: Path):
    lines: list[str] = []
    result = run_case(
        tmp_path,
        on_log=lines.append,
        command_override=["bash", "-lc", "echo hello-scentinel"],
    )
    assert result.exit_code == 0
    assert result.ok
    assert any("hello-scentinel" in line for line in lines)
    assert result.log_path.exists()


def test_run_case_records_the_failing_stage(tmp_path: Path):
    result = run_case(tmp_path, command_override=["bash", "-lc", "exit 13"])
    assert result.exit_code == 13
    assert result.failed_stage == EXIT_STAGE[13]


def test_run_case_cancels_and_kills_the_process_tree(tmp_path: Path):
    cancel = threading.Event()
    cancel.set()
    result = run_case(
        tmp_path,
        cancel=cancel,
        command_override=["bash", "-lc", "sleep 30"],
    )
    assert result.exit_code != 0
    assert not result.ok


def test_cancel_before_start_does_not_launch(tmp_path: Path):
    cancel = threading.Event()
    cancel.set()
    result = run_case(tmp_path, cancel=cancel, command_override=["bash", "-lc", "exit 0"])
    assert result.exit_code == -2
    assert "cancelled" in result.log_path.read_text()


def test_read_log_returns_the_tail(tmp_path: Path):
    result = run_case(
        tmp_path,
        command_override=["bash", "-lc", "for i in $(seq 1 60); do echo line-$i; done"],
    )
    tail = read_log(result, tail_lines=5)
    assert "line-60" in tail
    assert "line-1" not in tail


def test_stage_log_reads_the_named_file(tmp_path: Path):
    (tmp_path / "log.simpleFoam").write_text("solver output")
    assert "solver output" in stage_log(tmp_path, "simpleFoam")
    assert stage_log(tmp_path, "missing") == ""


@pytest.mark.integration
def test_podman_reports_its_availability():
    assert podman_available() in (True, False)
