# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Step-1 anti-fake gate: the GOLD patch, round-tripped through the NEW workspace seam, must grade resolved.

Clone flask-4045 at base_commit (host_clone) -> git apply the gold source fix -> workspace_diff (the seam
both backends use) -> grade with the official harness. Confirms the general seam produces a gradeable patch
(gold -> resolved). The empty -> not-resolved half is structural (grade_patch returns False on an empty
patch without invoking Docker). Env-gated (git + Docker), slow.
"""

import subprocess
import sys
from pathlib import Path

from datasets import load_dataset

from substrate.assay.swebench import grade_patch
from substrate.assay.swebench_workspace import host_clone, workspace_diff

IID = "pallets__flask-4045"


def main() -> None:
    inst = next(
        x
        for x in load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
        if x["instance_id"] == IID
    )
    print("cloning at base_commit (host_clone)...", flush=True)
    clone = host_clone(f"https://github.com/{inst['repo']}", inst["base_commit"])

    # apply the GOLD source fix into the checkout (stands in for what a topology would do: change the repo).
    p = subprocess.run(
        ["git", "-C", clone, "apply"], input=inst["patch"], text=True, capture_output=True
    )
    if p.returncode != 0:
        print("git apply of gold failed:\n" + p.stderr[-800:], flush=True)
        sys.exit(2)

    patch = workspace_diff(clone)
    print(
        f"workspace_diff produced {len(patch)}b; touches: "
        f"{[ln[6:] for ln in patch.splitlines() if ln.startswith('+++ b/')]}",
        flush=True,
    )

    print("grading via the official harness (Docker; slow)...", flush=True)
    resolved = grade_patch(
        IID,
        patch,
        report_root=Path("process/runs/assays/ws_gate"),
        dataset_name="princeton-nlp/SWE-bench_Lite",
    )
    print(
        f"\n=== STEP-1 GATE: {'PASS' if resolved else 'FAIL'} "
        f"(gold via workspace_diff -> resolved={resolved}) ===",
        flush=True,
    )
    sys.exit(0 if resolved else 3)


if __name__ == "__main__":
    main()
