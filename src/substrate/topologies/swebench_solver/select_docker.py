"""DockerTestRunner — run an instance's tests in its container with a candidate patch applied.

Implements the TestRunner protocol. Env-gated (needs Docker + the per-instance swebench eval image). On
arm64 it runs under emulation (`--platform linux/amd64`) — the path the gold smoke proved works. The repo
lives at /testbed in the image (checked out at base_commit), so a model_patch (a git diff from base_commit)
applies cleanly.

`derive_regression_command` keeps the firewall: the regression command is built from the repo's OWN test
files, with the held-out `test_patch` files dropped — it is never the instance's PASS_TO_PASS field.
"""

from __future__ import annotations

import os
import subprocess
import tempfile


def instance_image(instance_id: str, *, namespace: str = "swebench", arch: str = "x86_64") -> str:
    """The swebench eval image for an instance, e.g. pallets__flask-4045 ->
    swebench/sweb.eval.x86_64.pallets_1776_flask-4045:latest (the `__`->`_1776_` rule from TestSpec)."""
    key = instance_id.replace("__", "_1776_")
    return f"{namespace}/sweb.eval.{arch}.{key}:latest"


def derive_regression_command(test_files: list[str], *, exclude: set[str], extra: str = "-q") -> str:
    """Build the regression pytest command from the REPO's discovered test files, dropping the held-out
    `test_patch` files (`exclude`). NOT the PASS_TO_PASS field. Empty if nothing is left to run."""
    files = [f for f in test_files if f not in exclude]
    if not files:
        return ""
    return f"python -m pytest {' '.join(files)} {extra}".strip()


class DockerTestRunner:
    """Run `test_command` in the instance container after applying `model_patch` to /testbed. Returns
    (returncode, combined-output). A patch that fails to apply -> non-zero (an honest not-passed)."""

    def __init__(
        self, image: str, *, testbed: str = "/testbed", platform: str = "linux/amd64", timeout: int = 900
    ) -> None:
        self.image = image
        self.testbed = testbed
        self.platform = platform
        self.timeout = timeout

    def run(self, model_patch: str, test_command: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "patch.diff"), "w") as fh:
                fh.write(model_patch)
            # apply the patch, then run the tests; `&&` so a failed apply short-circuits to non-zero.
            script = f"cd {self.testbed} && git apply -v /sol/patch.diff && {test_command}"
            try:
                p = subprocess.run(
                    ["docker", "run", "--rm", "--platform", self.platform, "-v", f"{d}:/sol:ro",
                     self.image, "bash", "-lc", script],
                    capture_output=True, text=True, timeout=self.timeout,
                )
            except subprocess.TimeoutExpired:
                return (124, f"docker run timed out after {self.timeout}s")
            except OSError as exc:
                return (125, f"docker run failed to start: {exc}")
            return (p.returncode, p.stdout + p.stderr)
