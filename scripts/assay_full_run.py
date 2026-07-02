"""Run the REPAIR TOPOLOGY over the ENTIRE SWE-bench set and produce a complete result.

The goal: the topology runs on EVERY instance and the run finishes with a number — resolved / total — whatever
that number is (it depends on the model plugged in). Robust by construction: each instance is isolated in a
try/except (a clone/model/grade failure becomes a recorded 'error', never kills the run), the base clone is
cleaned per instance (no disk blowup at 300+), and every outcome is checkpointed to a JSONL so a long run
RESUMES where it left off and partial results are never lost.

Usage: uv run python scripts/assay_full_run.py [model] [n] [limit]
  model  — the producer model (default qwen3-coder:480b-cloud)
  n      — best-of-N drafters (default 3)
  limit  — cap the number of instances (default 0 = ALL of SWE-bench Lite, 300)
Env-gated (git + Docker + image pulls per instance + a live model). Long.
"""

import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from datasets import load_dataset

from substrate.api import Runtime, read_record
from substrate.assay.swebench import firewall_check, swebench_record_oracle
from substrate.reference._models import OllamaResponder
from substrate.assay.swebench_workspace import host_clone
from substrate.topologies.swebench_solver.assemble import swebench_repair_topology

MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen3-coder:480b-cloud"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 3
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 0


async def _solve_and_grade(inst, oracle, root: Path) -> tuple[str, str]:
    """Clone at base_commit, run the repair topology, classify the outcome from the TYPED terminal record
    (`RepairSummary`), and — only if a patch was selected — grade it. Returns (status, detail). The status
    is the topology's own enumerated outcome (no reconstruction from event kinds): `resolved` / `wrong_patch`
    (a patch was submitted, graded pass/fail), or the no-patch reason (`no_applicable_edit` / `no_localization`),
    or `timed_out` (no terminal summary -> the run hit its watchdog). A patch the official grader CAN'T score
    (e.g. the SWE-bench eval image is missing from the registry -> BuildImageError/404) is `grade_unavailable`
    — the topology succeeded; the failure is grading INFRASTRUCTURE, not us. Any clone/topology failure raises
    to the caller -> 'error' (the genuine our-side / couldn't-run-the-topology bucket)."""
    clone = host_clone(f"https://github.com/{inst['repo']}", inst["base_commit"])
    try:
        files = subprocess.run(
            ["git", "-C", clone, "ls-files"], capture_output=True, text=True
        ).stdout.split()
        responders = [OllamaResponder(MODEL, max_tokens=2048) for _ in range(N)]
        topo = swebench_repair_topology(
            responders=responders,
            base_checkout=clone,
            issue=str(inst["problem_statement"]),
            repo_skeleton="\n".join(files),
            known_files=set(files),
            n=N,
            max_rounds=2,
        )
        await Runtime(root).run(topo)
        record = list(read_record(root))
        summary = next((e["payload"] for e in record if e["kind"] == "RepairSummary"), None)
        if summary is None:
            return (
                "timed_out",
                "no RepairSummary — the run hit its time limit before reaching an outcome",
            )
        diag = f"localized={summary['localized']} drafted={summary['drafted']} applied={summary['applied']}"
        if summary["outcome"] != "selected":
            return summary[
                "outcome"
            ], diag  # no patch -> the typed outcome IS the status; nothing to grade
        try:
            result = oracle.grade(record, inst)  # a patch was selected -> grade it
        except Exception as exc:  # noqa: BLE001 — the topology produced a patch; the GRADER couldn't score it
            # grade infrastructure failed (e.g. the SWE-bench eval image is missing -> BuildImageError/404).
            # That's upstream, not our topology — a distinct status from a clone/topology 'error'.
            return (
                "grade_unavailable",
                f"grader could not score a produced patch: {type(exc).__name__}: {str(exc)[:140]} | {diag}",
            )
        return ("resolved" if result.passed else "wrong_patch"), f"{result.detail} | {diag}"
    finally:
        shutil.rmtree(clone, ignore_errors=True)


def main() -> None:
    ds = list(load_dataset("princeton-nlp/SWE-bench_Lite", split="test"))
    if LIMIT:
        ds = ds[:LIMIT]
    safe_model = MODEL.replace("/", "_").replace(":", "_")
    out_dir = Path("process/assay_full") / safe_model
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt = out_dir / "results.jsonl"

    done: dict[str, str] = {}
    if ckpt.exists():
        for line in ckpt.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["instance_id"]] = r["status"]
    print(
        f"FULL RUN: {len(ds)} instances | model={MODEL} n={N} | already done: {len(done)} (resuming)",
        flush=True,
    )

    oracle = swebench_record_oracle(
        report_root=str(out_dir / "grade"), dataset_name="princeton-nlp/SWE-bench_Lite"
    )
    base = Path(tempfile.mkdtemp(prefix="full-run-"))
    started = time.monotonic()

    for i, inst in enumerate(ds):
        iid = inst["instance_id"]
        if iid in done:
            continue
        fw_ok, _ = firewall_check(inst)
        try:
            status, detail = asyncio.run(_solve_and_grade(inst, oracle, base / f"c{i}"))
        except Exception as exc:  # noqa: BLE001 — an instance that blows up is recorded, not fatal
            status, detail = "error", f"{type(exc).__name__}: {str(exc)[:160]}"
        rec = {
            "instance_id": iid,
            "repo": inst["repo"],
            "status": status,
            "firewall_clean": fw_ok,
            "detail": detail,
        }
        with ckpt.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
        done[iid] = status
        n_res = sum(1 for s in done.values() if s == "resolved")
        print(f"[{len(done)}/{len(ds)}] {iid} -> {status} | resolved so far: {n_res}", flush=True)

    # final tally from the checkpoint (authoritative, survives restarts), broken down by the TYPED outcome.
    from collections import Counter

    rows = [json.loads(line) for line in ckpt.read_text().splitlines() if line.strip()]
    counts = Counter(r["status"] for r in rows)
    res = counts["resolved"]
    elapsed = int(time.monotonic() - started)
    print(
        "\n==================== FULL SWE-BENCH RESULT (repair topology) ====================",
        flush=True,
    )
    print(
        f"model={MODEL} n={N} | processed {len(rows)}/{len(ds)} | {elapsed}s this session",
        flush=True,
    )
    print(f"RESOLVED {res}/{len(rows)} ({100 * res / max(len(rows), 1):.1f}%)", flush=True)
    # the breakdown a person can read: resolved (fixed it) vs wrong_patch (model's fix didn't pass) vs
    # no_applicable_edit (the model's edits didn't match the file — OUR concern if high) vs no_localization
    # (no file picked) vs timed_out (hit the watchdog) vs grade_unavailable (patch produced but the official
    # eval image is missing -> upstream, not us) vs error (couldn't even run the topology — clone/topology crash).
    for label in (
        "resolved",
        "wrong_patch",
        "no_applicable_edit",
        "no_localization",
        "timed_out",
        "grade_unavailable",
        "error",
    ):
        print(f"  {label:<20} {counts[label]}", flush=True)
    # the resolve rate over GRADEABLE instances excludes grade_unavailable (we never got a verdict on those).
    gradeable = len(rows) - counts["grade_unavailable"] - counts["error"]
    print(
        f"resolved over gradeable: {res}/{gradeable} ({100 * res / max(gradeable, 1):.1f}%)",
        flush=True,
    )
    for bucket in ("grade_unavailable", "error"):
        bad = [r for r in rows if r["status"] == bucket]
        if bad:
            print(f"{bucket} by repo: {Counter(r['repo'] for r in bad)}", flush=True)
            for r in bad[:10]:
                print(f"    {r['instance_id']}: {r['detail']}", flush=True)
    print(f"checkpoint: {ckpt}", flush=True)


if __name__ == "__main__":
    main()
