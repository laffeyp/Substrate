"""Verify the REAL substrate coding topology resolves SWE-bench instances — localize -> best-of-N repair ->
first applyable patch, run as an Arm through run_arm_on_case, graded by the official harness. The substrate
producers do the coding (not a function in a shell). Env-gated (git + Docker + a live model). Slow.

Usage: uv run python scripts/assay_repair_topology_verify.py [model] [n] [instance_ids...]
"""

import asyncio
import sys
import tempfile
from pathlib import Path

from datasets import load_dataset

from substrate.assay.run import run_arm_on_case
from substrate.assay.suite import FULL, Case
from substrate.assay.swebench import swebench_record_oracle
from substrate.assay.swebench_matrix import repair_arm
from substrate.assay.swebench_suite import safe_case_id

MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen3-coder:480b-cloud"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 3
IIDS = sys.argv[3:] or ["astropy__astropy-12907", "django__django-10914"]


def main() -> None:
    ds = list(load_dataset("princeton-nlp/SWE-bench_Lite", split="test"))
    by_id = {x["instance_id"]: x for x in ds}
    arm = repair_arm("repair", FULL, model=MODEL, n=N, max_rounds=2)
    oracle = swebench_record_oracle(
        report_root="process/assay_repair", dataset_name="princeton-nlp/SWE-bench_Lite"
    )
    base = Path(tempfile.mkdtemp(prefix="repair-verify-"))
    resolved = []
    for iid in IIDS:
        inst = by_id[iid]
        case = Case(case_id=safe_case_id(iid), payload={}, ground_truth=inst)
        print(f"\n--- {iid} ({inst['repo']}) — running the repair TOPOLOGY (n={N}; slow) ---", flush=True)
        res = asyncio.run(run_arm_on_case(arm, case, oracle, base / case.case_id))
        # show that the substrate producers actually ran (the record is the proof).
        from substrate.api import read_record
        rec = list(read_record(base / case.case_id))
        kinds = [e["kind"] for e in rec]
        print(f"  record kinds: localizer={kinds.count('SuspectFiles')} drafts={kinds.count('Candidate')} "
              f"applied={kinds.count('AppliedPatch')} selected={kinds.count('SelectedPatch')}", flush=True)
        print(f"  resolved={res.result.passed} | {res.result.detail}", flush=True)
        if res.result.passed:
            resolved.append(iid)

    print(f"\n=== REPAIR TOPOLOGY: {len(resolved)}/{len(IIDS)} resolved -> {resolved} ===", flush=True)
    print("(a genuine substrate topology — producers do the localize/draft/apply — emitting patches, graded official)", flush=True)


if __name__ == "__main__":
    main()
