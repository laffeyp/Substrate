"""NET #2 (review #69): smoke the REAL regression SEAM end to end on the live flask-4045 image — the seam
the gold-fed solve sidestepped with _PassRunner. This drives the ACTUAL firewall-clean regression command
(proximity picker -> build_regression_command, reusing swebench's own install + test_cmd) through the real
DockerTestRunner, with the gold patch applied, and confirms the picked UNRELATED tests pass (regression
holds) — proving the command + container before the signal is ever trusted to drive selection.

Also runs the per-instance firewall assertion and prints exclude_delta (the harness-assist disclosure).
Real, slow, env-gated (Docker + the cached image). Run on the Architect's box, never in CI.
"""

import subprocess
import sys

from datasets import load_dataset

from substrate.assay.swebench import firewall_check
from substrate.topologies.swebench_solver.select_docker import (
    DockerTestRunner,
    instance_image,
    repo_test_spec,
)
from substrate.topologies.swebench_solver.select_exec import regression_passed
from substrate.topologies.swebench_solver.select_regression import (
    discover_test_modules,
    exclude_delta,
    make_regression_planner,
    patch_touched_files,
)

IID = "pallets__flask-4045"


def _added_files(diff: str) -> set[str]:
    return {ln[6:] for ln in diff.splitlines() if ln.startswith("+++ b/") and ln[6:] != "dev/null"}


def main() -> None:
    inst = next(x for x in load_dataset("princeton-nlp/SWE-bench_Lite", split="test") if x["instance_id"] == IID)
    img = instance_image(IID)

    # 1. per-instance firewall assertion (NET #2 item 2)
    ok, reason = firewall_check(inst)
    print(f"firewall_check: {ok} — {reason}", flush=True)
    if not ok:
        sys.exit(2)

    # 2. discover the repo's OWN test files from the container at base_commit (the checkout, not PASS_TO_PASS)
    print(f"image: {img}\ndiscovering repo test files in-container...", flush=True)
    ls = subprocess.run(
        ["docker", "run", "--rm", "--platform", "linux/amd64", img, "bash", "-lc",
         "cd /testbed && git ls-files 'tests/**.py' tests/*.py"],
        capture_output=True, text=True,
    )
    if ls.returncode != 0:
        print("ls FAILED:\n" + ls.stderr[-1500:], flush=True)
        sys.exit(2)
    # filter to pytest-collectable test MODULES — not fixture/support files (which error on collection).
    repo_tests = discover_test_modules([ln for ln in ls.stdout.splitlines() if ln.strip()])
    print(f"  {len(repo_tests)} repo test modules (e.g. {repo_tests[:3]})", flush=True)

    # 3. build the firewall-clean planner; plan the regression command for the GOLD patch
    spec = repo_test_spec(inst["repo"], inst["version"])
    exclude = _added_files(inst["test_patch"])  # held-out test_patch file paths
    touched = patch_touched_files(inst["patch"])  # gold patch touches src/flask/blueprints.py
    print(f"  gold patch touches: {sorted(touched)}", flush=True)
    print(f"  test_patch files (exclude): {sorted(exclude)}", flush=True)
    print(f"  exclude_delta (harness-assist beyond proximity): {exclude_delta(repo_tests, touched, exclude=exclude)}",
          flush=True)

    plan = make_regression_planner(spec, repo_tests, exclude=exclude)
    cmd = plan(inst["patch"])
    picked = cmd.split("pytest -rA ", 1)[1] if "pytest -rA " in cmd else "(none)"
    print(f"  regression set (issue-unrelated): {picked[:200]}{'...' if len(picked) > 200 else ''}", flush=True)

    # 4. run the REAL regression command through the REAL runner with the gold patch applied
    print("\nrunning the firewall-clean regression command in-container (slow)...", flush=True)
    runner = DockerTestRunner(img, timeout=1800)
    rc, out = runner.run(inst["patch"], cmd)
    print(f"\nrc={rc}\n--- tail ---\n{out[-1800:]}", flush=True)
    passed = regression_passed(rc, out)
    print(f"\nregression_passed = {passed}  (the gold patch passes the issue-UNRELATED regression set)", flush=True)
    # the gold patch is correct, so the unrelated regression set must hold; a False here means the SEAM is
    # broken (env setup, command shape, or the runner), not the patch.
    sys.exit(0 if passed else 3)


if __name__ == "__main__":
    main()
