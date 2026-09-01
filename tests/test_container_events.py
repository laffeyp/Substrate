# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 194 (roadmap v2 S5.3): typed events on the B3 Docker container-lifecycle boundary.

`DockerTestRunner.run` emits `ContainerRequested` on entry, then one of `ContainerExited`
(normal termination — carries `exit_code`) or `ContainerKilled` (timeout / start-failure)
on the terminal branch. Same stderr-JSON pattern as Sprint 190's repo-clone events.

Substance tests without live Docker: monkeypatch `subprocess.run` to simulate the timeout
+ OSError + normal-exit paths. Source-scan pin catches the three event kinds surviving a
future edit.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _load_events(captured: str) -> list[dict]:
    events = []
    for line in captured.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("boundary") == "container":
            events.append(obj)
    return events


def test_normal_exit_emits_requested_and_exited(monkeypatch, capsys):
    """Normal termination: `ContainerRequested` on entry, `ContainerExited(exit_code=0)` on
    the terminal branch. Uses monkeypatched subprocess.run to skip actual docker."""
    from substrate.topologies.swebench_solver import select_docker

    class _FakeCompleted:
        def __init__(self, rc: int, stdout: str = "ok", stderr: str = ""):
            self.returncode = rc
            self.stdout = stdout
            self.stderr = stderr

    monkeypatch.setattr(
        select_docker.subprocess,
        "run",
        lambda *args, **kwargs: _FakeCompleted(0, "test ok", ""),
    )

    runner = select_docker.DockerTestRunner(image="test:img", timeout=60)
    rc, out = runner.run("", "pytest -q")
    assert rc == 0

    captured = capsys.readouterr()
    events = _load_events(captured.err)
    kinds = [e["kind"] for e in events]
    assert kinds == ["ContainerRequested", "ContainerExited"], (
        f"expected [Requested, Exited] on normal exit; got {kinds}"
    )
    assert events[0]["payload"]["image"] == "test:img"
    assert events[1]["payload"]["exit_code"] == 0
    assert events[1]["payload"]["wall_ms"] >= 0


def test_timeout_emits_requested_and_killed(monkeypatch, capsys):
    """Timeout: `ContainerRequested` on entry, `ContainerKilled(reason=timed_out)` on the
    terminal branch."""
    from substrate.topologies.swebench_solver import select_docker

    def _fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="docker run ...", timeout=1)

    monkeypatch.setattr(select_docker.subprocess, "run", _fake_run)

    runner = select_docker.DockerTestRunner(image="test:img", timeout=1)
    rc, out = runner.run("", "pytest -q")
    assert rc == 124

    captured = capsys.readouterr()
    events = _load_events(captured.err)
    kinds = [e["kind"] for e in events]
    assert kinds == ["ContainerRequested", "ContainerKilled"], (
        f"expected [Requested, Killed] on timeout; got {kinds}"
    )
    assert events[1]["payload"]["reason"] == "timed_out"


def test_start_failure_emits_requested_and_killed_docker_error(monkeypatch, capsys):
    """Docker daemon down / OSError: `ContainerRequested` then `ContainerKilled(reason=docker_error)`."""
    from substrate.topologies.swebench_solver import select_docker

    def _fake_run(*args, **kwargs):
        raise OSError("docker daemon not reachable")

    monkeypatch.setattr(select_docker.subprocess, "run", _fake_run)

    runner = select_docker.DockerTestRunner(image="test:img", timeout=60)
    rc, out = runner.run("", "pytest -q")
    assert rc == 125

    captured = capsys.readouterr()
    events = _load_events(captured.err)
    kinds = [e["kind"] for e in events]
    assert kinds == ["ContainerRequested", "ContainerKilled"], (
        f"expected [Requested, Killed] on OSError; got {kinds}"
    )
    assert events[1]["payload"]["reason"] == "docker_error"
    assert "docker daemon" in events[1]["payload"]["detail"]


def test_select_docker_source_contains_three_event_kinds():
    """Source-scan pin: `DockerTestRunner.run` emits all three vocab v0.3 § G.2 kinds it uses
    (Requested, Exited, Killed). ContainerStarted isn't emitted here because subprocess.run
    is synchronous — the "started" boundary and the "exited" boundary collapse into one call
    site under subprocess.run's blocking shape. A refactor to an async spawn+wait would gain
    Started; the pin catches any drop of the three currently emitted."""
    src = Path(
        sys.modules["substrate.topologies.swebench_solver.select_docker"].__file__ or ""
    ).read_text()
    for kind in ("ContainerRequested", "ContainerExited", "ContainerKilled"):
        assert kind in src, f"expected {kind!r} event kind at the container boundary"
    assert '"container"' in src
