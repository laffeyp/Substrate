"""Local SWE-bench smoke — prove the eval pipeline end-to-end on THIS arm64 box.

Takes one PURE-PYTHON instance (flask/requests/click — no C extensions, the best shot at a clean
native arm64 build), uses its GOLD patch as the prediction, and runs the official harness with
`namespace=''` (BUILD arm64 images locally, not pull the x86 pre-built ones — the arm64 requirement
the SWE-bench docs state). The gold patch MUST resolve; if it does, the containerized grade works here.
Slow on the first build (image layers + deps). Run:  uv run python scripts/swebench_smoke.py
"""

import sys
import traceback
from pathlib import Path

from datasets import load_dataset

from substrate.assay.swebench import make_prediction, read_resolved, run_swebench

PREFER = ("pallets/flask", "psf/requests", "pallets/click", "sqlfluff/sqlfluff", "marshmallow-code/marshmallow")
RUN_ID = "goldsmoke"
RDIR = Path("process/swebench_smoke").resolve()


def main() -> None:
    d = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    inst = next((x for x in d if x["repo"] in PREFER), d[0])
    iid = inst["instance_id"]
    print(f"instance: {iid}  repo={inst['repo']}  base={inst['base_commit'][:10]}", flush=True)
    pred = make_prediction(iid, inst["patch"], model_name="gold")
    print("running the harness — default namespace => PULL the official x86 image + run under "
          "emulation (Rosetta/QEMU). Slow: pulls ~GB then runs the test suite emulated…", flush=True)
    try:
        report = run_swebench(
            [pred],
            dataset_name="princeton-nlp/SWE-bench_Lite",
            run_id=RUN_ID,
            instance_ids=[iid],
            report_dir=RDIR,
            max_workers=1,
            # default namespace='swebench': pull docker.io/swebench/sweb.eval.x86_64.* and run emulated.
            # (namespace='' tries a local arm64 build, which 4.1.0 botches: x86_64 baked in the name +
            #  an invalid leading-slash reference. Emulation is the working local path on Apple Silicon.)
        )
        print("RUN REPORT:", report, flush=True)
    except Exception as exc:  # noqa: BLE001 — the WHOLE point is to surface the real arm64 failure mode
        traceback.print_exc()
        print(f"\nHARNESS ERROR (this IS the answer about local arm64): {type(exc).__name__}: {exc}", flush=True)
        sys.exit(2)
    try:
        resolved = read_resolved(RDIR, RUN_ID, "gold", iid)
    except FileNotFoundError as exc:
        print(f"\nno report.json found: {exc}", flush=True)
        sys.exit(3)
    print(f"\nRESOLVED: {resolved}   (the gold patch MUST resolve — proves the pipeline works here)", flush=True)


if __name__ == "__main__":
    main()
