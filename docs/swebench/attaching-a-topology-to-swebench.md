# Attaching a topology to the SWE-bench runner

Substrate's SWE-bench runner grades a topology against real SWE-bench instances through the
official swebench harness (Docker per grade, official `run_swebench` subprocess). The runner
does the git clones, image pulls, firewall checks, salvage-resume, per-repo per-cell timeouts,
error classification, and cells-JSONL writing. The topology does the solve.

## The attachment point

`substrate.assay.suite.Arm` is the attachment. An `Arm` packages a topology under a name; the
runner fires the Arm on each prepared Case and grades the resulting record.

```python
from substrate.assay.suite import Arm, Case
from substrate.assay.swebench_suite import (
    prepare_swebench_case,
    swebench_suite,
)
from substrate.assay.run import run_suite_with_salvage


def my_topology(builder):
    """A substrate topology. Whatever producers, triggers, views, termination policy your
    topology declares — plus it must emit `SelectedPatch(slot=..., model_patch=...)` before
    quiescence for the SWE-bench oracle to grade a patch. Uses whichever models/responders
    your topology wires internally; the runner does not pass models."""
    ...


# 1. Wrap the topology in an Arm. `role="full"` is the default; leave it alone for solo runs.
arm = Arm(name="my_topology", build=lambda case: my_topology)

# 2. Prepare cases (one per SWE-bench instance dict from the HuggingFace dataset).
from datasets import load_dataset
instances = list(load_dataset("princeton-nlp/SWE-bench_Lite", split="test"))[:10]
cases = [prepare_swebench_case(inst) for inst in instances]

# 3. Build a Suite. `control_arm=None` is the default for solo runs; the report layer skips
#    paired-delta framing.
suite = swebench_suite(
    cases=cases,
    arms=[arm],
    report_root="./grade-reports",
    dataset_name="princeton-nlp/SWE-bench_Lite",
)

# 4. Fire the sweep. Cells JSONL rows come out via the `on_outcome` callback; records land
#    per cell under `root_dir`.
import asyncio, json

async def append_row(outcome):
    with open("./cells.jsonl", "a") as f:
        f.write(json.dumps({
            "arm": outcome.arm.name,
            "case_id": outcome.case.case_id,
            "verdict": outcome.result.verdict.value if outcome.result else "no_verdict",
            "elapsed_ms": outcome.elapsed_ms,
        }) + "\n")

outcomes = asyncio.run(run_suite_with_salvage(
    suite,
    root_dir="./records",
    trials=1,
    concurrency=4,
    on_outcome=append_row,
))
```

## What the topology must do

The Arm contract:

- **Its topology must emit `SelectedPatch(slot: int, model_patch: str, reason: str)`** before the
  run finalises. `SelectedPatch` is the terminal event the SWE-bench oracle reads. A topology
  that never emits `SelectedPatch` grades as fail (no patch to grade) or, if `swebench_solve_and_grade_suite`
  is used, as `verdict=no_verdict, reason=docker_error` when the essential-path producer failed.
- **Its topology owns its model choices.** The runner does not pass a `model=` argument. The
  topology's `build(case)` constructs whichever `Responder` instances the topology needs —
  one responder, multiple responders, an ensemble, whatever the topology wires. See
  `substrate.assay.swebench_matrix._wrap_ollama` for the pattern that wraps a responder in
  `RateLimitedResponder` under the current Ollama tier.

## Reading results

Two shapes come out per run:

1. **Cells JSONL**: one line per (arm × case × trial), whatever your `on_outcome` callback
   writes. Substrate's built-in runner (`scripts/assay_swebench_confirmatory.py`) writes a
   detailed row: `verdict`, `reason`, `source`, `elapsed_ms`, `model_calls`, `prompt_tokens`,
   `completion_tokens`, `reproduction`, `recall_at_k`. Your own topology-attachment reader can
   record whatever fields it needs.
2. **Per-cell records** under `root_dir/{arm}__{case}__t{trial}/`: the full substrate event
   log for that cell — every `ModelUsage`, `Draft`, `Candidate`, `Verdict`, `SelectedPatch`,
   `GradeResult`, `substrate.ProducerStarted/Completed/Failed`. Any topology-level metric
   projects off this log with `substrate.api.read_record(root)`.

## When to use the built-in runner vs. rolling your own

The built-in runner `scripts/assay_swebench_confirmatory.py` is designed for the substrate
project's own comparative experiments: multiple pre-registered arm modes (`solver`, `pass1`,
`matrix`, `solve_and_grade`), pre-registration gate, foreign-config resume guard, model
preflight, image prepull, batch-grade opt-in. It reads a large env-var configuration surface.

A topology author test-driving their own topology should NOT edit the built-in runner. The
pattern above — six library calls, ~30 lines — is the intended attachment surface. The built-in
runner is one specific consumer of that library, not the library.

## Existing built-in arms

Reference implementations under `substrate.assay.swebench_matrix` +
`substrate.assay.swebench_suite`:

- `swebench_repair_arm(name, *, models, n, max_rounds)` — best-of-N repair topology, no
  in-topology grading.
- `swebench_solve_and_grade_arm(name, role, *, models, report_root, dataset_name, ...)` —
  same shape plus an in-topology grade producer that emits `GradeResult`.
- `container_arm(name, role, *, model, max_steps)` — agent-loop-in-Docker topology.
- `container_solve_and_grade_arm(name, role, *, model, report_root, dataset_name, ...)` —
  container arm with in-topology grader.
- `host_arm(name, role, *, model)` — host-side backend.
- `swebench_solver_arm(name, role, *, models, n, max_rounds)` — repair arm, pre-Sprint-199c
  API kept for source-compat.

Each is a working example of the Arm contract.
