"""Container backend — a LIVE instance container an executing topology edits and runs tests in.

The faithful workspace: bring up the instance's eval image (repo at `/testbed`, deps installed), keep it
alive, and route a topology's read/edit/bash actions into it via `docker exec`. The patch is `git diff`
in-container — the same seam as the host backend, just produced inside the container. For agents that run
tests/bash while solving (where the host backend's static clone can't help them).

CONTAMINATION LOCKDOWN (review): inside the eval image the agent could reach the network (`pip install` the
already-fixed package version) or the git remotes / future-commit history (the fixing commit is reachable).
Guards: `--network none` (no fetch, no pip-from-index) and strip all git remotes at startup. (`/testbed`'s
local history still contains the fix as a descendant of base_commit — `git log` from HEAD shows only
ancestors, but `git log --all` could surface it; network-off + no-remotes closes the high-value vectors,
and the deeper guard is to not give the agent a reason to do git archaeology.)
"""

from __future__ import annotations

import os
import subprocess
import tempfile

from ..topologies.swebench_solver.select_docker import instance_image
from .swebench_workspace import filter_diff


class ContainerWorkspace:
    """A live instance container. `start()` runs it detached with the network OFF and remotes stripped;
    `exec`/`read_file`/`write_file` operate inside it at `/testbed`; `diff` is `git diff` in-container;
    `stop()` removes it. Use as a context manager. Env-gated (Docker + the eval image)."""

    def __init__(
        self,
        instance_id: str,
        *,
        image: str | None = None,
        testbed: str = "/testbed",
        platform: str = "linux/amd64",
        exec_timeout: int = 900,
    ) -> None:
        self.image = image or instance_image(instance_id)
        self.testbed = testbed
        self.platform = platform
        self.exec_timeout = exec_timeout
        self._cid: str | None = None

    def __enter__(self) -> ContainerWorkspace:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def start(self) -> None:
        """Run the eval image detached with `--network none` (contamination lockdown), then strip git
        remotes so a `git fetch` of the fix is impossible even if the network ever came back."""
        p = subprocess.run(
            ["docker", "run", "-d", "--rm", "--network", "none", "--platform", self.platform,
             self.image, "sleep", "infinity"],
            capture_output=True, text=True, check=True,
        )
        self._cid = p.stdout.strip()
        # strip every remote (belt-and-suspenders with --network none).
        self.exec("git remote 2>/dev/null | xargs -r -n1 git remote remove")

    def exec(self, command: str) -> tuple[int, str]:
        """Run `command` in the container at `/testbed` (login shell, so the conda testbed env is active).
        Returns (returncode, combined output). 124 on timeout."""
        if self._cid is None:
            raise RuntimeError("ContainerWorkspace not started")
        script = f"cd {self.testbed} && {command}"
        try:
            p = subprocess.run(
                ["docker", "exec", self._cid, "bash", "-lc", script],
                capture_output=True, text=True, timeout=self.exec_timeout,
            )
        except subprocess.TimeoutExpired:
            return (124, f"exec timed out after {self.exec_timeout}s")
        return (p.returncode, p.stdout + p.stderr)

    def read_file(self, relpath: str) -> str:
        """The content of `/testbed/<relpath>` ("" if it does not exist)."""
        rc, out = self.exec(f"cat {relpath}")
        return out if rc == 0 else ""

    def write_file(self, relpath: str, content: str) -> None:
        """Write `content` to `/testbed/<relpath>` via `docker cp` (robust — no shell escaping of content)."""
        if self._cid is None:
            raise RuntimeError("ContainerWorkspace not started")
        with tempfile.TemporaryDirectory() as d:
            host = os.path.join(d, "f")
            with open(host, "w", encoding="utf-8") as fh:
                fh.write(content)
            self.exec(f"mkdir -p $(dirname {relpath})")
            subprocess.run(
                ["docker", "cp", host, f"{self._cid}:{self.testbed}/{relpath}"],
                capture_output=True, check=False,
            )

    def diff(self, *, drop_files: frozenset[str] = frozenset()) -> str:
        """The model_patch: `git add -A && git diff --cached HEAD` IN-CONTAINER, with graded-test-file
        sections dropped (the same `filter_diff` seam the host backend uses)."""
        _, out = self.exec("git add -A && git diff --cached HEAD")
        return filter_diff(out, drop_files=drop_files)

    def stop(self) -> None:
        if self._cid is not None:
            subprocess.run(["docker", "rm", "-f", self._cid], capture_output=True, check=False)
            self._cid = None


__all__ = ["ContainerWorkspace"]
