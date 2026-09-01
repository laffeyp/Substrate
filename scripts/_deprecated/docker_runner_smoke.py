# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Verify DockerTestRunner against the LIVE flask-4045 image: pull it, apply the gold patch, run flask's
own blueprint tests in the container, confirm they run and pass (regression holds). Real, slow."""

import subprocess
import sys

from datasets import load_dataset

from substrate.topologies.swebench_solver.select_docker import DockerTestRunner, instance_image
from substrate.topologies.swebench_solver.select_exec import regression_passed

IID = "pallets__flask-4045"


def main() -> None:
    d = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    inst = next(x for x in d if x["instance_id"] == IID)
    img = instance_image(IID)
    print(f"image: {img}\npulling (slow, ~GB under emulation)...", flush=True)
    pull = subprocess.run(
        ["docker", "pull", "--platform", "linux/amd64", img], capture_output=True, text=True
    )
    if pull.returncode != 0:
        print("pull FAILED:\n" + pull.stderr[-1500:], flush=True)
        sys.exit(2)
    print("pulled. running flask's blueprint tests with the gold patch applied...", flush=True)
    runner = DockerTestRunner(img, timeout=1200)
    rc, out = runner.run(inst["patch"], "python -m pytest tests/test_blueprints.py -q")
    print(f"\nrc={rc}\n--- tail ---\n{out[-1800:]}", flush=True)
    print(
        f"\nregression_passed = {regression_passed(rc, out)}  (the runner ran flask's tests in-container)",
        flush=True,
    )


if __name__ == "__main__":
    main()
