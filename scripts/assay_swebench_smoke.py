"""S1 live gate: run the FULL assay path on flask-4045 with a GOLD-fed Arm, through the real harness.

The buildable parts are unit-tested; this proves the integration end-to-end: prepare_swebench_case (clone +
base run) -> a custom Arm whose build wires solver_topology_from_payload with gold-fed responders ->
run_arm_on_case (runs the topology, the record carries a SelectedPatch) -> swebench_record_oracle (extracts
the patch, Docker-grades it). The gold fix MUST come back resolved=True. Env-gated (git + Docker), slow.
"""

import asyncio
import sys
import tempfile
from pathlib import Path

from datasets import load_dataset

from substrate.assay.run import run_arm_on_case
from substrate.assay.suite import FULL, Arm
from substrate.assay.swebench import swebench_record_oracle
from substrate.assay.swebench_suite import prepare_swebench_case, solver_topology_from_payload

IID = "pallets__flask-4045"


def diff_to_search_replace(diff: str) -> str:
    """Gold unified diff -> the solver's SEARCH/REPLACE blocks (one per hunk): SEARCH = context+removed,
    REPLACE = context+added. Same converter the gold-fed flask_solve uses."""
    lines = diff.splitlines()
    out: list[str] = []
    path: str | None = None
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        if ln.startswith("+++ b/"):
            path = ln[6:].strip()
            i += 1
            continue
        if ln.startswith("@@"):
            i += 1
            search: list[str] = []
            replace: list[str] = []
            while i < n and not lines[i].startswith("@@") and not lines[i].startswith("diff --git"):
                h = lines[i]
                if h.startswith("+"):
                    replace.append(h[1:])
                elif h.startswith("-"):
                    search.append(h[1:])
                elif h.startswith(" "):
                    search.append(h[1:])
                    replace.append(h[1:])
                i += 1
            if path and (search or replace):
                out.append(
                    f"# path: {path}\n<<<<<<< SEARCH\n"
                    + "\n".join(search)
                    + "\n=======\n"
                    + "\n".join(replace)
                    + "\n>>>>>>> REPLACE"
                )
            continue
        i += 1
    return "\n".join(out) + "\n"


def main() -> None:
    inst = next(
        x
        for x in load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
        if x["instance_id"] == IID
    )
    gold_files = sorted({ln[6:] for ln in inst["patch"].splitlines() if ln.startswith("+++ b/")})
    sr = diff_to_search_replace(inst["patch"])

    class _GoldResponder:
        """Returns the gold localization on a localize prompt, the gold SEARCH/REPLACE on a repair prompt."""

        def respond(self, prompt: str) -> str:
            return ("\n".join(gold_files) + "\n") if "suspect file" in prompt else sr

    print("preparing the case (clone + base run; slow)...", flush=True)
    case = prepare_swebench_case(inst)
    print(
        f"  case_id={case.case_id}; passed-at-base={len(case.payload['passed_at_base'])}",
        flush=True,
    )

    def build(c) -> object:  # type: ignore[no-untyped-def]
        return solver_topology_from_payload(c.payload, [_GoldResponder()], n=1, max_rounds=1)

    arm = Arm(name="gold", role=FULL, build=build)
    oracle = swebench_record_oracle(
        report_root=Path("process/assay_smoke"), dataset_name="princeton-nlp/SWE-bench_Lite"
    )
    root = Path(tempfile.mkdtemp(prefix="assay-smoke-")) / "run"

    print("running the arm through run_arm_on_case + grading (real container; slow)...", flush=True)
    result = asyncio.run(run_arm_on_case(arm, case, oracle, root))
    print(f"\nresolved={result.result.passed} | {result.result.detail}", flush=True)
    print(
        f"oracle_class={result.result.oracle_class} replayable={result.result.replayable} "
        f"elapsed_ms={result.elapsed_ms} model_calls={result.usage.model_calls}",
        flush=True,
    )
    print(
        f"\n=== S1 GATE: {'PASS' if result.result.passed else 'FAIL'} "
        f"(gold-fed arm resolves through the full assay path) ===",
        flush=True,
    )
    sys.exit(0 if result.result.passed else 3)


if __name__ == "__main__":
    main()
