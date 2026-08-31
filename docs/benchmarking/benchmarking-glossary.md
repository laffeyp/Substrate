# Benchmarking glossary and on-ramp

This is a reading aid for the benchmarking design doc ([`benchmarking-design-round1.md`](benchmarking-design-round1.md)). It assumes you are a competent engineer who has not seen this codebase or its methodology. Read this first, then the design doc will make sense.

The benchmarking layer (working name **"assay"**, not yet locked) measures whether a Substrate topology actually *produces a better outcome* than a baseline, judged against an external benchmark. Substrate already has checks that prove a run's wiring executes and that its log replays; those say nothing about outcome quality. The assay layer adds that missing axis: run the topology and a control side by side on real tasks, grade both against ground truth, and report the difference honestly (with statistics and contamination accounted for). Tokens and time are measured too, but they are not a cost — these are local / subscription models, so there is no money involved at all.

## Terms

Substrate vocabulary (the runtime these benchmarks run on). Deeper definitions are in [`../README.md`](../README.md) and [`adding-a-topology.md`](adding-a-topology.md).

- **topology** — a small Python program declaring which computations may run, what conditions start them, and how data flows. It is the unit being benchmarked. See the README "What you actually write" section.
- **Producer** — one callable inside a topology that takes typed input and emits typed Events (an LLM, a checker, a subprocess, a parser). See [`adding-a-topology.md`](adding-a-topology.md).
- **Event** — one typed, numbered fact written on the log (e.g. `AnswerEmitted`). The log is an append-only ledger of these.
- **record** (a.k.a. run record) — the complete log of a run, persisted to disk as framed, CRC-protected JSONL. Every event and every runtime decision is on it; it is what gets replayed and inspected.
- **run root / inner_root** — the on-disk location (the "root") a run writes its record to. When one run launches another run inside itself, the inner run gets its own distinct root, called the **inner_root**. The benchmark mints one inner_root per (Arm × Case × Trial) so each arm's record is separable.
- **embedded_substrate** — the kernel facility (`kernel/composition.py`) that lets a run execute another full Substrate run inside itself. The assay layer does NOT use it: each Arm runs as a plain top-level run at its own root (simpler, and the records are still separable).
- **Oracle** — the component that decides whether an Arm's output is correct, by comparing it to ground truth. It is the source of the "did it pass" verdict.
- **log-projection Oracle vs external-grader Oracle** — two kinds of Oracle. A *log-projection* Oracle grades by reading a terminal-state event off the inner record and comparing to a known answer; it is deterministic and replayable. An *external-grader* Oracle runs an outside system (e.g. a Docker test image) and reads its verdict; it is non-deterministic and *not* replayable — only the orchestration around it (which case, which arm, which grade event) replays.
- **Arm** — one configured contestant in a comparison: a specific topology configuration, or a baseline. Each Arm runs as a plain top-level run at its own root; the Arms are compared against each other. (Statistics borrows the clinical-trial sense of "arm.")
- **Suite** — a named, versioned, frozen set of Cases (benchmark instances), committed before any run so results cannot be cherry-picked after the fact.
- **Adapter** — the wiring that turns a benchmark Case into topology input and connects the grading. It does load-bearing scientific work (a sloppy Adapter can manufacture a favorable result), so it is pre-registered alongside the Suite and every Arm consumes identical Adapter output.
- **Trial** — one run of one Arm on one Case. Because real model APIs are not seed-deterministic, multiple Trials re-run the same pipeline to measure variance.
- **Report** — the aggregated output: per-Arm results, the measured delta against the control, and the token and time measurements per Arm (separate fields, not a cost).
- **ModelUsage** — a typed event carrying `prompt_tokens`, `completion_tokens`, `wall_ms`, `estimated`, emitted at the model-call seam so each model call's token and time measurement lands on the record. No money is tracked — these are local / subscription models; tokens and time are measurements, not a cost (see design doc §5).
- **single-model baseline** — the control Arm: one model on the same task. The comparison asks whether the topology's structure produces a better outcome than one model. Tokens and time are reported as separate measurements; neither is a cost, and there is no money here.
- **ablation** — removing one mechanism from the topology to see what it actually contributes. Example: "N drafts with no correction loop" vs "N drafts + failure-fed correction" isolates whether the correction loop earns its keep.

SDD process words (the methodology used to build this repo; you only need the gist):

- **the kit** — the Signal-Driven Development (SDD) methodology kit the project follows. Its catalogue of named techniques is `TECHNIQUES.md` (see below); the design doc's `#NN` citations point into it.
- **vocabulary session** — a methodology step where a term list is *transcribed* from source design docs rather than invented ad hoc. The design doc notes it is pre-session scoping, not the session itself.
- **the Architect** — the role that ratifies architecture-band decisions. Several open items in the doc are flagged as needing Architect sign-off before code is written.

## Benchmark shorthand

External benchmark terms the design doc uses without defining:

- **SWE-bench** — a benchmark of real GitHub issues; the model must produce a patch that fixes the bug. **SWE-bench Verified** is a human-filtered subset of solvable, well-specified instances. **SWE-bench-Live** is a continuously-updated stream of recent instances, used here because recent ones post-date model training cutoffs (see contamination, below).
- **FAIL_TO_PASS / PASS_TO_PASS** — the two test sets a SWE-bench patch is graded on. `FAIL_TO_PASS` tests fail before the patch and must pass after (proves the fix). `PASS_TO_PASS` tests pass before and must still pass after (proves nothing was broken). A patch is resolved only if both hold.
- **pass@1 vs pass^k** — `pass@1` is the chance a single attempt succeeds. `pass^k` (pass-hat-k) is the chance *all* k independent attempts succeed — a stricter consistency measure, reported here with a bootstrap confidence interval rather than a point estimate.
- **McNemar** — a paired statistical test for two methods on the same instances with binary (pass/fail) outcomes. Pairing across instances cancels most between-run noise, which is why it is preferred here over an unpaired rate comparison.
- **contamination-dated split** — selecting only benchmark instances created *after* a model's training cutoff, so the model cannot have memorized the answer. Public sets (SWE-bench Verified, HumanEval, GSM8K) are assumed contaminated and used only as stamped, secondary comparisons.

## Where the referenced docs live

- **`#NN` technique citations** (e.g. `#41`, `#15`, `#42`) — refer to numbered techniques in the SDD kit's **`TECHNIQUES.md`** (in the sdd-kit-2 methodology kit, not this repo's `src/`).
- **Levels 1 / 2 / 3a / D-8** (replay fidelity levels and the log-equivalence diff) — defined in [`replay.md`](replay.md).
- **KIT_DIARY findings** (e.g. "finding 9") — recorded in **`process/KIT_DIARY.md`** in the development record.
- **`BLACKBOARD.md`** (where the `ModelUsage` halt is surfaced for review) — in **`process/`**.
- **The specs** referenced indirectly (kernel, product, technical, design) — under `docs/specs/`; see the README "Repository layout" table for the canonical drafts.
