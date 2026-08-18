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


PATH_RUNNER = "path"
MODULE_LABEL_RUNNER = "module_label"


def runner_flavor(test_cmd: str) -> str:
    """Which arg shape does the repo's test runner expect: file paths or dotted module labels?

    Pytest / py.test take file paths (`pytest tests/test_x.py`). Django's `runtests.py` and any
    `python -m unittest` form take DOTTED MODULE LABELS (`myapp.tests.foo` or
    `myapp.tests.foo.MyTest.test_bar`), not paths. F5 fix (review 2026-08-08): pre-fix
    `build_regression_command` RAISED on the module-label case, so every Django instance (~14 on
    SWE-bench Lite, ~34 on Verified) crashed at case-preparation before the topology ran. Now
    `build_regression_command` dispatches on this classifier and adapts.

    Unknown -> PATH_RUNNER falls back to the pytest shape (the majority default on
    SWE-bench). A truly novel runner will surface as a mis-formatted command, not a silent
    exclusion; the failing case-preparation still returns cleanly and the runner logs the
    mismatch."""
    low = test_cmd.lower()
    if "runtests.py" in low or "python -m unittest" in low or "unittest" in low.split():
        return MODULE_LABEL_RUNNER
    if "pytest" in low or "py.test" in low:
        return PATH_RUNNER
    return PATH_RUNNER


def cmd_takes_paths(test_cmd: str) -> bool:
    """Legacy alias — kept for the one caller that still checks the boolean.  Prefer `runner_flavor`."""
    return runner_flavor(test_cmd) == PATH_RUNNER


def path_to_module_label(path: str) -> str:
    """Convert a Python file path to its dotted module label. `myapp/tests/foo.py` ->
    `myapp.tests.foo`. Non-Python paths (a `.cfg` or a `.txt` in the regression set) return the
    original path unchanged — the caller filters them out per runner. F5 fix (review 2026-08-08).

    Package-init `__init__.py` maps to the parent package (`myapp/tests/__init__.py` ->
    `myapp.tests`) so a Django caller that picks a `tests/` folder gets the package label, not a
    `.__init__` suffix the module runner wouldn't understand."""
    if not path.endswith(".py"):
        return path
    stem = path[:-3]
    if stem.endswith("/__init__"):
        stem = stem[: -len("/__init__")]
    return stem.replace("/", ".")


def build_regression_command(
    spec: Mapping[str, Any], regression_files: list[str], *, activate: str = TESTBED_ACTIVATE
) -> str:
    """The firewall-clean in-container regression command: activate the testbed env, run the repo's OWN
    install (`spec['install']`, e.g. `python -m pip install -e .` so the candidate's source change takes
    effect) then the repo's OWN test runner (`spec['test_cmd']`, e.g. `pytest -rA`) over the chosen
    `regression_files`. `regression_files` come from the proximity picker over the checkout — NEVER the
    eval_script's selection / PASS_TO_PASS. Empty if there's nothing to run (no vacuous all-pass).

    F5 fix (review 2026-08-08): dispatches on the runner flavor. Path-taking runners (pytest) get
    file paths + `--continue-on-collection-errors`. Module-label runners (django's runtests.py,
    `python -m unittest`) get the file paths converted to dotted module labels via
    `path_to_module_label`. Django's runtests takes labels positionally; adding them just works
    (`./tests/runtests.py --settings=... myapp.tests` runs myapp.tests's whole module).
    Non-Python entries in `regression_files` are dropped for module-label runners (a `.cfg` can't
    be a module label; that entry silently omits, the pytest side would have grepped past it too).

    An unknown runner flavor falls back to PATH_RUNNER — no exception. Real runners that break on
    this fallback show up in the run's stderr, not as a silent exclusion at case-preparation.
    """
    if not regression_files:
        return ""
    test_cmd = str(spec["test_cmd"]).strip()
    install = str(spec["install"]).strip()
    flavor = runner_flavor(test_cmd)
    if flavor == PATH_RUNNER:
        # --continue-on-collection-errors: pytest ABORTS the whole run if ANY named file fails to
        # collect (a stray test module with a missing optional dep -> 0 passed for everything,
        # proven by the real solve #152). Continue past it so the collectable tests still run
        # and establish the base-passing set; an uncollectable file simply contributes no test
        # ids (it can't be in passed_at_base anyway).
        args = " ".join(regression_files)
        return (
            f"{activate} && {install} && {test_cmd} --continue-on-collection-errors {args}".strip()
        )
    # MODULE_LABEL_RUNNER — django's runtests, python -m unittest. Convert paths to labels;
    # drop non-Python entries (can't be module labels).
    labels = [path_to_module_label(p) for p in regression_files if p.endswith(".py")]
    if not labels:
        return ""
    args = " ".join(labels)
    return f"{activate} && {install} && {test_cmd} {args}".strip()


def _emit_container_event(kind: str, payload: dict[str, object]) -> None:
    """Sprint 194 (roadmap v2 S5.3): typed events for the B3 Docker container lifecycle.
    `DockerTestRunner.run` fires `docker run --rm` per invocation; each run is one container's
    lifecycle. Stderr JSON matches Sprint 190's repo-clone, Sprint 192's image-pull, Sprint 193's
    harness patterns. Kind names match vocab v0.3 § G.2."""
    import json as _json
    import sys as _sys
    import time as _time

    line = _json.dumps(
        {"t": _time.time(), "kind": kind, "boundary": "container", "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
    )
    print(line, file=_sys.stderr, flush=True)


class DockerTestRunner:
    """Run `test_command` in the instance container after applying `model_patch` to /testbed. Returns
    (returncode, combined-output). A patch that fails to apply -> non-zero (an honest not-passed).

    Sprint 194 (roadmap v2 S5.3): emits typed `ContainerRequested` on entry then one of
    `ContainerExited` (normal termination — carries `exit_code`) or `ContainerKilled`
    (wall-clock exceeded or start failure) on the terminal branch. Same stderr-JSON pattern
    as Sprint 190's repo-clone events."""

    def __init__(
        self,
        image: str,
        *,
        testbed: str = "/testbed",
        platform: str = "linux/amd64",
        timeout: int = 900,
    ) -> None:
        self.image = image
        self.testbed = testbed
        self.platform = platform
        self.timeout = timeout

    def run(
        self, model_patch: str, test_command: str, extra_files: dict[str, str] | None = None
    ) -> tuple[int, str]:
        import time as _time

        _started = _time.monotonic()
        _emit_container_event(
            "ContainerRequested",
            {
                "image": self.image,
                "timeout_s": self.timeout,
                "patch_bytes": len(model_patch),
            },
        )
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
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--platform",
                        self.platform,
                        "-v",
                        f"{d}:/sol:ro",
                        self.image,
                        "bash",
                        "-lc",
                        script,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
            except subprocess.TimeoutExpired:
                _emit_container_event(
                    "ContainerKilled",
                    {
                        "image": self.image,
                        "wall_ms": int((_time.monotonic() - _started) * 1000),
                        "reason": "timed_out",
                    },
                )
                return (124, f"docker run timed out after {self.timeout}s")
            except OSError as exc:
                _emit_container_event(
                    "ContainerKilled",
                    {
                        "image": self.image,
                        "wall_ms": int((_time.monotonic() - _started) * 1000),
                        "reason": "docker_error",
                        "detail": str(exc)[:400],
                    },
                )
                return (125, f"docker run failed to start: {exc}")
            _emit_container_event(
                "ContainerExited",
                {
                    "image": self.image,
                    "exit_code": p.returncode,
                    "wall_ms": int((_time.monotonic() - _started) * 1000),
                },
            )
            return (p.returncode, p.stdout + p.stderr)
