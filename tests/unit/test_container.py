"""Container storage isolation and the pull/verify flow.

Every podman invocation must carry ``CONTAINERS_STORAGE_CONF`` pointing inside
the app home; these tests pin that, plus the setup flow's step order, its
failure reporting, and its cancellation.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from scentinel.core import container
from scentinel.core.casegen import IMAGE


class _FakeCompleted:
    """Stand-in for ``subprocess.CompletedProcess`` with captured output."""

    def __init__(self, returncode: int = 0, stdout: list[str] | None = None) -> None:
        self.returncode = returncode
        self.stdout = stdout if stdout is not None else []


class _Recorder:
    """Records every ``run`` call and replays a scripted sequence of results."""

    def __init__(self, results: list[_FakeCompleted]) -> None:
        self.calls: list[dict[str, object]] = []
        self._results = list(results)

    def __call__(self, command, **kwargs):
        self.calls.append({"command": list(command), **kwargs})
        return self._results.pop(0) if self._results else _FakeCompleted()

    @property
    def envs(self) -> list[dict[str, str]]:
        return [call["env"] for call in self.calls]


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCENTINEL_HOME", str(tmp_path))


def test_storage_conf_lives_in_the_app_home_and_points_inside_it(tmp_path: Path):
    path = container.ensure_storage_conf()

    assert path == tmp_path / "containers" / "storage.conf"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert f'graphroot = "{tmp_path / "containers" / "storage"}"' in text
    assert f'runroot = "{tmp_path / "containers" / "run"}"' in text


def test_storage_conf_enables_userns_keep_id_in_a_private_graphroot(tmp_path: Path):
    """``podman run --userns=keep-id`` fails on a fresh private graphroot otherwise.

    The native overlay driver needs an ID-mapped copy of every layer, which a
    store the user has never populated cannot produce: measured as
    "creating an ID-mapped copy of layer". fuse-overlayfs does that mapping in
    userspace, so it must be selected whenever it is installed.
    """
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(container.shutil, "which", lambda name: "/usr/bin/fuse-overlayfs")
    try:
        text = container.ensure_storage_conf().read_text(encoding="utf-8")
    finally:
        monkeypatch.undo()

    assert 'driver = "overlay"' in text
    assert 'mount_program = "/usr/bin/fuse-overlayfs"' in text
    assert 'ignore_chown_errors = "true"' in text


def test_storage_conf_stays_plain_without_fuse_overlayfs():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(container.shutil, "which", lambda name: None)
    try:
        text = container.ensure_storage_conf().read_text(encoding="utf-8")
    finally:
        monkeypatch.undo()

    # Without the helper there is nothing to point at, so no driver is pinned:
    # podman's rootless default is still better than a wrong choice.
    assert "mount_program" not in text
    assert "driver" not in text


def test_podman_env_sets_the_storage_conf(tmp_path: Path):
    env = container.podman_env()

    assert env["CONTAINERS_STORAGE_CONF"] == str(tmp_path / "containers" / "storage.conf")
    assert Path(env["CONTAINERS_STORAGE_CONF"]).exists()


def test_podman_env_preserves_the_base_environment():
    env = container.podman_env({"PATH": "/bin"})

    assert env["PATH"] == "/bin"
    assert "CONTAINERS_STORAGE_CONF" in env
    # The caller's mapping is never mutated in place.
    base = {"PATH": "/bin"}
    container.podman_env(base)
    assert base == {"PATH": "/bin"}


def test_container_ready_reports_a_missing_podman_without_raising(monkeypatch):
    monkeypatch.setattr(container.shutil, "which", lambda _name: None)

    ok, reason = container.container_ready()

    assert ok is False
    assert "podman" in reason


def test_container_ready_reports_a_missing_image(monkeypatch):
    monkeypatch.setattr(container.shutil, "which", lambda _name: "/usr/bin/podman")
    monkeypatch.setattr(container, "image_available", lambda _image=IMAGE: False)

    ok, reason = container.container_ready()

    assert ok is False
    assert IMAGE in reason


def test_setup_pulls_then_verifies_inside_the_isolated_storage(tmp_path: Path):
    run = _Recorder(
        [
            _FakeCompleted(stdout=["Trying to pull...", "Copying blob abc\n"]),
            _FakeCompleted(stdout=["  gmshToFoam OK\n", "  simpleFoam OK\n"]),
        ]
    )

    result = container.setup_container(run=run)

    assert result.ok
    assert result.exit_code == 0
    assert len(run.calls) == 2
    assert run.calls[0]["command"][:2] == ["podman", "pull"]
    assert run.calls[0]["command"][2] == IMAGE
    assert run.calls[1]["command"][:3] == ["podman", "run", "--rm"]
    for env in run.envs:
        assert env["CONTAINERS_STORAGE_CONF"] == str(tmp_path / "containers" / "storage.conf")
    assert "Trying to pull..." in result.log
    assert "  gmshToFoam OK" in result.log
    assert "==> Container ready" in result.log


def test_setup_reports_a_failed_verification():
    run = _Recorder(
        [
            _FakeCompleted(stdout=["pulled\n"]),
            _FakeCompleted(returncode=1, stdout=["MISSING: foamToVTK\n"]),
        ]
    )

    result = container.setup_container(run=run)

    assert result.ok is False
    assert result.exit_code == 1
    assert any("MISSING: foamToVTK" in line for line in result.log)
    assert not any("Container ready" in line for line in result.log)


def test_setup_streams_every_line_to_the_callback():
    run = _Recorder([_FakeCompleted(stdout=["one\n", "two\n"]), _FakeCompleted()])
    seen: list[str] = []

    container.setup_container(on_log=seen.append, run=run)

    assert "one" in seen
    assert "two" in seen


def test_setup_returns_early_when_cancelled():
    cancel = threading.Event()
    cancel.set()
    run = _Recorder([])

    result = container.setup_container(cancel=cancel, run=run)

    assert run.calls == []
    assert result.ok is False
    assert result.exit_code == container.CANCELLED_EXIT_CODE


def test_main_pulls_the_requested_image_and_reports_failure(monkeypatch):
    seen: list[str] = []

    def fake_setup(image=IMAGE, **kwargs):
        seen.append(image)
        return container.ContainerSetupResult(ok=False, exit_code=1, log=[])

    monkeypatch.setattr(container, "setup_container", fake_setup)

    assert container.main(["example/image:1"]) == 1
    assert seen == ["example/image:1"]
