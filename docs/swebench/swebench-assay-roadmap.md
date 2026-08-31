# SWE-bench as an assay benchmark — roadmap

## The real goal

Make SWE-bench a benchmark that **any substrate orchestration of the right shape** can be run against and measured — the same way `coding.py` already does for a firewalled coding benchmark. Not one bespoke solver. The substrate lets you build many different orchestrations (of any producers, models or not, mixed however); the assay layer runs all of them through one harness and measures how they differ.

This realizes `docs/benchmarking/benchmarking-design-round1.md` (the "assay" layer) for SWE-bench specifically.

## What already exists (verified, cite before trusting) — the harness is built

The Arm/Case/Suite contract and the control plane are **done and generic**:

- `assay/suite.py` — `Case(case_id, payload, ground_truth)`, `Arm(name, role, build: Case→Topology)`, `Suite(cases, arms, oracle, control_arm, primary_metric, null_rule, equivalence_margin, pass_k)`. **An Arm is any topology buildable from a Case — this is the "right shape."**
- `assay/run.py` — `run_suite` / `run_arm_on_case`: run each (Arm × Case × Trial) at a minted root, grade the record via the Oracle, measure tokens + two time axes (real wall-clock vs summed inference work).
- `assay/oracle.py` — `LogProjectionOracle` (replayable) / `ExternalGraderOracle` (run-and-observe, `replayable=False`).
- `assay/report.py`, `assay/conformance.py`, `assay/stats.py` — leaderboard, three-state control-ran check, the statistics (pass^k, paired bootstrap, TOST/equivalence, BH-FDR, `equivalence_power_floor` ~90/160/360).
- `assay/coding.py` + `coding_problems.py` — a **complete worked benchmark**: `CodingProblem` (dev gate vs held-out grading = the firewall), `coding_oracle` (held-out external grade), `coding_suite` (the ablation arm matrix over coding_flow). This is the pattern the SWE-bench Adapter copies.
- `assay/swebench.py` — the SWE-bench grading pieces: `firewall_check`, `DockerTestRunner`, `run_swebench`, `read_resolved`, `make_prediction`, `swebench_oracle`. Proven on the live flask-4045 image this session.
- Candidate Arms: `topologies/swebench_solver/` (the localize→repair→select pipeline — proven to emit an applyable, regression-clean, near-correct patch), `topologies/tool_loop/` (model→tool→model with file tools), `topologies/coding_flow/` + `best_of_n/`.

## What's actually missing (narrow)

1. **A record-grading SWE-bench Oracle.** `coding_oracle` extracts the selected candidate from the record and grades it inline; the SWE-bench analog must extract the `model_patch` from an Arm's record (the `SelectedPatch` event) and grade it via Docker (`DockerTestRunner` / one-instance `run_swebench`). `swebench.py`'s current `swebench_oracle` reads a *pre-run batch* report — adapt/add an inline form that fits `run_arm_on_case`.
2. **A SWE-bench Suite/Adapter** (`assay/swebench_suite.py`), the analog of `coding_suite`: Cases = instances (`ground_truth` = the instance dict), Arms wire topologies via `build(case)`, the per-case repo checkout + firewall-clean regression setup (the harness work the session's `solve_instance.py` does by hand) lives in the Adapter, never exposing `test_patch`/FAIL_TO_PASS.
3. **The record contract for an Arm:** a SWE-bench Arm's topology must emit its `model_patch` on the record. `swebench_solver` already emits `SelectedPatch.model_patch`. Other arms (a tool agent) must emit an equivalent patch event (or the Adapter computes the diff from the repo edits).
4. **More arms + the measurement run** — ride the existing harness unchanged.

## The shape (Arm contract for SWE-bench)

- `build(case)` returns a topology that, given the instance's issue + a repo checked out at `base_commit`, emits a `model_patch` event on its record.
- The Adapter owns: per-case checkout, firewall-clean regression planner + passed-at-base (the session's `select_regression` / `select_docker` pieces), and wiring the record-grading Oracle.
- A topology is a valid SWE-bench Arm iff it can be built from a Case and emits a `model_patch`. Nothing SWE-bench-specific leaks into the topology.

## Sprints

**S1 — the SWE-bench Oracle + Suite + first Arm (the core missing piece).**
- Record-grading SWE-bench Oracle: extract `model_patch` from the record → Docker grade → `resolved`. Run-and-observe, `replayable=False`.
- `swebench_suite(instances, arms)`: Cases from instances; per-case checkout + firewall setup in the Adapter; `swebench_solver` wired as the first Arm via `build(case)`.
- Gold differential-test the Adapter+Oracle on ≥10 instances (known-resolved gold resolves; empty patch does not) — the anti-fake-number gate, before any Arm number is trusted.

**S2 — run one Arm over a small frozen Suite through `run_suite`; produce the leaderboard via `report.py`.** Confirm the three-state control-ran check (`conformance.py`). Tokens/time/quality reported separately.

**S3 — second Arm: a tool-using agent (`tool_loop` with read/edit/bash on the checkout), same Adapter unchanged.** The topology-agnosticism proof.

**S4 — third Arm: ensemble / mixed producers.** Same Adapter.

**S5 — pre-registered measurement.** Suite (contamination-dated split primary — SWE-bench-Live; Lite secondary/stamped), primary endpoint (resolved), published null/equivalence rule, control arm, N at the power floor; paired McNemar / bootstrap; per-dimension report.

**S6 — back to the reviewer before any number is a "result."**

## Non-negotiables

- Firewall in the Adapter; every Arm consumes the identical Adapter output.
- External-grader = run-and-observe, `replayable=False`, labeled; only the orchestration replays.
- Tokens, time, quality are three separate measurements; no money.
- Pre-registration + published null rule + paired stats + power before running; never print equivalence below the power floor.
- Contamination-dated primary; static set secondary, stamped.
- No model tiers / no "paradigm" reasoning — an Arm is arbitrary compute behind the shape.

## Verification

- Gold differential-test passes (≥10 instances).
- Each Arm runs end-to-end on the live container and lands a graded record.
- The *same* Adapter runs ≥2 structurally different Arms (pipeline + tool agent) with no Arm-specific change.
- The leaderboard's orchestration replays; grades are labeled run-and-observe.
- The report refuses equivalence below the power floor and emits no result without a control Arm on the log.

## Notes

- `run.py` uses a plain top-level `Runtime` per Arm (not `embedded_substrate`); the design's two-record/embedded form is an open decision (design §8.3) — follow `run.py`'s plain-Runtime path.
- Confirm `report.py` / `conformance.py` exact surfaces when wiring S2.
- SWE-bench-Live is a distinct harness/image backend (design §6) — confirm availability in S5.
