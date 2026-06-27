"""DockerTestRunner — run an instance's tests in its container with a candidate patch applied.

Implements the TestRunner protocol. Env-gated (needs Docker + the per-instance swebench eval image). On
arm64 it runs under emulation (`--platform linux/amd64`) — the path the gold smoke proved works. The repo
lives at /testbed in the image (checked out at base_commit), so a model_patch (a git diff from base_commit)
applies cleanly.

`build_regression_command` keeps the firewall: it reuses ONLY the repo's env-setup (`pip install -e .`) and
test-runner invocation (e.g. `pytest -rA`) from swebench's per-repo spec — NEVER the eval_script's test
selection (which applies `test_patch` and names the held-out FAIL_TO_PASS/PASS_TO_PASS tests — that script
IS the grade, review #67). The test FILES come from the checkout via the proximity picker, never the
PASS_TO_PASS field.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Mapping
from typing import Any

# The swebench eval images activate a conda env named `testbed` holding the installed repo (seen in
# make_test_spec(inst).eval_script). Reusing the activation + install is env-setup, NOT test selection.
TESTBED_ACTIVATE = "source /opt/miniconda3/bin/activate && conda activate testbed"


def instance_image(instance_id: str, *, namespace: str = "swebench", arch: str = "x86_64") -> str:
    """The swebench eval image for an instance, e.g. pallets__flask-4045 ->
    swebench/sweb.eval.x86_64.pallets_1776_flask-4045:latest (the `__`->`_1776_` rule from TestSpec)."""
    key = instance_id.replace("__", "_1776_")
    return f"{namespace}/sweb.eval.{arch}.{key}:latest"


def repo_test_spec(repo: str, version: str) -> Mapping[str, Any]:
    """swebench's per-repo eval spec (`install`, `test_cmd`, ...) for a repo+version, read from
    MAP_REPO_VERSION_TO_SPECS — the SAME source make_test_spec uses for env setup + the test runner, with
    NONE of the eval_script's test selection / test_patch application (firewall). Lazy-imports swebench
    (env-gated); raises KeyError if the repo/version is unknown so a missing spec fails loudly."""
    from swebench.harness.constants import MAP_REPO_VERSION_TO_SPECS  # lazy, env-gated

    return MAP_REPO_VERSION_TO_SPECS[repo][version]  # type: ignore[no-any-return]


def cmd_takes_paths(test_cmd: str) -> bool:
    """Does the repo's runner take FILE PATHS as args, so appending picked test files forms a valid command?
    True for pytest-style runners (flask: `pytest -rA <files>`). FALSE for module-LABEL runners — django's
    `./tests/runtests.py --settings=...` wants `module.Class` labels, not paths, so appending paths makes a
    malformed/empty regression run (review #69, the per-repo guard before going past flask). Unknown ->
    False (conservative: don't silently emit a broken command for an uncatalogued runner)."""
    low = test_cmd.lower()
    if "pytest" in low or "py.test" in low:
        return True
    return False


def build_regression_command(
    spec: Mapping[str, Any], regression_files: list[str], *, activate: str = TESTBED_ACTIVATE
) -> str:
    """The firewall-clean in-container regression command: activate the testbed env, run the repo's OWN
    install (`spec['install']`, e.g. `python -m pip install -e .` so the candidate's source change takes
    effect) then the repo's OWN test runner (`spec['test_cmd']`, e.g. `pytest -rA`) over the chosen
    `regression_files`. `regression_files` come from the proximity picker over the checkout — NEVER the
    eval_script's selection / PASS_TO_PASS. Empty if there's nothing to run (no vacuous all-pass).

    Raises ValueError if the repo's `test_cmd` is NOT a path-taking runner (django-style) while files are
    given — fail loud rather than append paths to a module-label runner and silently run nothing (#69)."""
    if not regression_files:
        return ""
    test_cmd = str(spec["test_cmd"]).strip()
    if not cmd_takes_paths(test_cmd):
        raise ValueError(
            f"test_cmd {test_cmd!r} is not a path-taking runner; appending file paths would malform the "
            "regression command. Add a per-repo command adapter (e.g. paths->module labels) before this repo."
        )
    install = str(spec["install"]).strip()
    # --continue-on-collection-errors: pytest ABORTS the whole run if ANY named file fails to collect
    # (a stray test module with a missing optional dep -> 0 passed for everything, proven by the real solve
    # #152). Continue past it so the collectable tests still run and establish the base-passing set; an
    # uncollectable file simply contributes no test ids (it can't be in passed_at_base anyway).
    return f"{activate} && {install} && {test_cmd} --continue-on-collection-errors {' '.join(regression_files)}".strip()


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

    def run(self, model_patch: str, test_command: str, extra_files: dict[str, str] | None = None) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "patch.diff"), "w") as fh:
                fh.write(model_patch)
            # extra files (e.g. the generated reproduction test) land in /sol alongside the patch, so the
            # test_command can reference them (`python /sol/repro.py`).
            for rel, content in (extra_files or {}).items():
                with open(os.path.join(d, rel), "w") as fh:
                    fh.write(content)
            # apply the patch, then run the tests; `&&` so a failed apply short-circuits to non-zero. An
            # EMPTY patch means "run on base_commit" (the passed-at-base run) — skip git apply, which errors
            # on an empty file ("No valid patches in input", rc 128) and would short-circuit the test run.
            apply = "" if not model_patch.strip() else "git apply -v /sol/patch.diff && "
            script = f"cd {self.testbed} && {apply}{test_command}"
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
