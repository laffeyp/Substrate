# Objective validation layer — design, round 1 (post-adversarial-review)

*Status: architecture-band design, awaiting Architect go. NOT yet a vocabulary session — this is the product/technical scoping the session will transcribe from (per BOOTSTRAP: a session needs source docs to cite, not a pre-decided term list). Working name "assay" is provisional and not locked.*

*Provenance: this round folds a three-lens adversarial panel (SDD-discipline, measurement-validity, substrate-architecture), each briefed on sdd-kit-2 and the real code. Every finding below is traced to its resolution so the fold is auditable.*

---

## 1. What this layer is, and is not

The repo already has **intrinsic** validation: conformance (17 checks), replay (Levels 1/2/3a), observation contracts. These prove the *wiring runs* and the *record replays*. They do not prove a topology *produces a better outcome than a baseline*. That second thing — outcome validation against an external benchmark — is what this layer adds. It is the generalization of the whitepaper §7 experiment from one planted-trap to a reusable harness.

It applies to the **answer-producing** topologies (coding_flow, pair_coding, tool_loop). It does **not** manufacture an outcome score for the **dynamics** topologies (debate, prisoners_dilemma, intel_asymmetry, natural_conversation) — those have no external answer-oracle, and their honest measurement is intrinsic (defection rate, calibration vs known truth, the with/without ablation). Forcing them onto a QA benchmark is a category error and is out of scope here (§7).

---

## 2. Architecture — what survived review, what changed

**The spine survives.** An **Arm** (a configured topology-or-baseline) runs as an inner substrate run via `embedded_substrate` (`kernel/composition.py`), writing a complete record at its own `inner_root`. Real-model, `deterministic=False` inner runs are supported. This is genuine reuse, verified against the code.

**Two contracts the spine imposes (Finding A1):**
- `inner_root` is **mandatory by raise** (`composition.py:_inner_root_from_input → InnerRootRequired`). With Cases fanning out as N events, the control plane must mint **N distinct roots**, one per (Arm × Case × Trial).
- Provenance is **run-granularity only** — there is no per-frame `{inner_run_id, inner_seq}` stamp on the locked `ProducerRef`. The Oracle therefore reads **two records** (the outer orchestration log + the inner record dereferenced by root), not one fused log.

**The control plane is plain Python, not a meta-topology (Finding A5).** `embedded_substrate` is used for **arm execution** — that is where the inner record, fan-out concurrency, and `first_divergence` between arms pay off. But minting roots, invoking external graders, aggregating a leaderboard, and computing statistics is an ordinary harness over the read API (`read_record`, `inspect`, `first_divergence`). The kit's simplest-viable ethos and Section-3 deferral of best-of-N dispatch both say: do not ceremonialize the control plane into an outer topology. "The benchmark is a substrate run" is true for the *arms*, not for the whole harness.

---

## 3. Two Oracle classes — the objectivity claim, made honest (Finding A2/M2)

The "Oracle scores by reading the log" slogan is false for the headline benchmarks. There are two distinct Oracle classes and every benchmark must declare which it is:

| Class | How it grades | Deterministic? | Replayable? | Examples |
|---|---|---|---|---|
| **log-projection** | reads a typed terminal-state event off the inner record and compares to ground truth | yes | yes (committable record) | `state == target` when the state is already an event; exact-match QA |
| **external-grader** | runs an external system (Docker test image, a benchmark DB + tools) and reads its verdict | no | **no** — run-and-observe | SWE-bench (`run_evaluation`), tau-bench (DB state) |

External-grader runs are **run-and-observe**, exactly like `coding_flow` today (`deterministic=False`, excluded from `BUNDLED`, no committed record — `bundled.py`/the `coding_flow` docstring are the precedent). The grade is recorded as an event on the outer log, but the grade itself is **not reproducible by replay**. We label these honestly and do not claim the eval is replayable; only the **orchestration** (which Case, which Arm, which inner root, which grade event) is replayable (Levels 1/2/D-8). Currency-gate any committed artifact with the determinism-skip from KIT_DIARY finding 9.

**No model in the scorer.** For external-grader benchmarks that embed an LLM in the environment (tau-bench's user-simulator, off-instruction ~22% of runs), that model is a confound, not an oracle. Round 1 avoids it (see §6). If ever used, the simulator model + version is pinned into `SESSION_INIT` and reported as a dataset fingerprint, and results across simulator backends are declared non-comparable.

---

## 4. The guarantees, made real

Each anti-cargo-cult guarantee, with the enforcement surface the review demanded (a type is not an enforcement surface — the project proved types tell lies: `Decision.LET_FINISH`, the fake R-3 checker, both green under mypy).

1. **A result is a delta against a named control — enforced by an executable check, not a type (Finding D-Rule2).** A `conformance`-style gate (the assay analog of `substrate conformance`) verifies that every reported result carries a control Arm whose `ProducerStarted` + inner record actually appear on the log, with the control's record committed. Three-state, never boolean: `pass / fail / no-control-ran`, carrying the measured delta. No control on the log → no result emitted.

2. **The Suite and the Adapter are pre-registered (Finding M-Adapter, M-honestnull).** A Suite is a named, versioned, frozen Case set, committed before any run (anti cherry-pick, #41). The Adapter (Case → topology input + the grading wiring) is pre-registered **alongside** the Suite, because it does load-bearing scientific work and is the place an over-fitted mapping manufactures a favorable delta. Every Arm — baselines included — consumes the **identical** Adapter output (Wave-0-carry, #15); the harness asserts this.

3. **One pre-registered primary endpoint + a written null-acceptance rule (Finding M-honestnull).** Before any run, per benchmark, fix: the metric, the baseline, and N. Everything else is labeled exploratory. The null rule is published up front ("if the paired delta on the primary endpoint has a 95% CI crossing zero at N=k, we report NULL") so "no measured benefit" is a verdict the framework can actually reach. Correct across the arm matrix (Holm/Bonferroni).

4. **Tokens and time are reported separately, never fused (#39).** Quality (pass rate), tokens, wall time, and gate-invocation count are each their own measurement; the headline is the pre-registered metric. NONE of them is a cost — there is no money here (local / subscription models). Tokens and time are three different quantities and none stands in for another or for dollars; nothing trades against quality. Time figures are machine-variant, so they carry their measurement context (hardware, model build, date — the N-PERF-1 lesson).

5. **The right baseline isolates the structure, not just more sampling (Finding M-compute).** Best-of-N from one model is a *strong* control. The ablation rung that isolates coding_flow's distinctive mechanism is **N drafts with no correction loop** vs **N drafts + failure-fed correction**, plus a single-draft floor. The placebo control (e.g. a navigator routing a no-op suggestion of the same shape) catches "structure that does nothing."

6. **Statistics are paired across instances, powered before running (Finding M-stats).** Real APIs are not seed-deterministic, so Trials re-run a non-deterministic pipeline (statistically deterministic, not byte-replayable). Use a paired test over the per-instance resolved-bit (McNemar / paired bootstrap), not an unpaired rate t-test — pairing removes most between-run variance. State a minimum-detectable-effect at the trial budget before running. For pass^k, report the bootstrap CI of the estimator; prefer small fixed k with explicit CIs over a point estimate.

7. **Contamination is a mechanism, not a sentence (Finding contamination).** Public sets (SWE-bench Verified, HumanEval, GSM8K) are in training data — Verified was dropped by at least one lab over exactly this. Primary results run on a **contamination-dated / post-cutoff split** (SWE-bench-Live); the static set is secondary, comparison-only, stamped. Authored scenarios require externally-certified ground truth that a cheap surface probe (bag-of-words logistic) **cannot** separate — or the calibration metric is theater.

---

## 5. `ModelUsage`: instrument tokens and time at the Responder seam (Finding A3)

Token and time measurement had **no data source on the record.** `OllamaResponder._content` extracted only `message.content` and **discarded** Ollama's `eval_count` / `prompt_eval_count` / `total_duration`.

Resolution (built, Sprint 1):
- A typed **`ModelUsage`** event (`prompt_tokens`, `completion_tokens`, `wall_ms`, `estimated`) emitted **at the Responder seam** so every model call lands its token/time measurement on the inner record. No money is tracked — these are local / subscription models; tokens and time are measurements, not a cost.
- `OllamaResponder` (and `CliResponder`) stop discarding the usage fields the providers already return.
- `ModelUsage` is an application kind (Producer-declared, the ToolCall precedent), not a reserved `substrate.*` kind — no kernel-vocabulary change.

Tokens and time are interesting and you can benchmark on either; the verdict here is output quality.

---

## 6. First wire-through (corrected): coding_flow → a contamination-dated coding benchmark

**Not** tool_loop → tau-bench — that is two non-deterministic external systems (a DB and an LLM user-simulator) on day one, the worst case for a layer whose thesis is "no model in the scorer." Start where the oracle is genuinely model-free.

- **Topology:** `coding_flow`. Its gate-shaped truth (write files, run a command, read exit code) already maps to apply-patch-and-run, so only the **Adapter** is new.
- **Benchmark:** a contamination-dated coding split (SWE-bench-Live recent instances, or an authored post-cutoff unit-test suite). External-grader Oracle, run-and-observe, labeled as such.
- **The Adapter is the real work and the real risk (Finding M-Adapter / the "single most likely fake number").** It must use the official `swebench` harness: clone repo, checkout base commit, apply candidate patch, build the pinned env, run the **held-out** FAIL_TO_PASS + PASS_TO_PASS sets; the Oracle reads *that* report. It must **not** keep coding_flow's current convenience gate, which grades free-form artifacts against the *author's own fixtures* — that is a self-graded look-alike, not the benchmark. The Adapter is differential-tested against ≥10 known-resolved + known-unresolved gold instances before any number is trusted.
- **Arms:** single draft (floor) / N drafts no-correction / N drafts + failure-fed correction (full) / single-model best-of-N at the same sample count (does the diverse ensemble beat sampling one model N times).
- **Endpoint:** pre-registered — primary metric = instances resolved on the dated split; paired McNemar across instances; dimensions reported separately; null rule published.

tau-bench is **second**, after the statistics and the Adapter discipline are proven on the clean deterministic case.

---

## 7. Out of scope, round 1 (named so the scope is honest)

- tau-bench / any external-grader with an LLM in the environment.
- Outcome scoring for the dynamics topologies (debate/PD/intel/natural_conversation) — measured intrinsically, separate track.
- LLM-as-judge in any scored path. If ever used, only under #42's full protocol (judge-family disjoint from generator, randomized order, length-normalized, Bradley-Terry, inter-judge agreement reported as a precondition).
- Expressing the whole harness as an outer topology.

---

## 8. Open decisions for the Architect

1. **`ModelUsage`** (§5) — built as an application kind (the ToolCall precedent; no ratification needed). Instruments tokens + time only; no money is tracked.
2. **Confirm coding_flow → contamination-dated coding as the first wire-through** (§6), tau-bench deferred to second.
3. **Confirm the plain-Python control plane** (arms via `embedded_substrate`; harness + read-API for everything else) over a meta-topology.
4. **Name** — defer "assay" vs alternatives to the vocabulary session; do not lock now.

## 9. Build sequence after go

1. Surface + ratify `ModelUsage`; emit it at the Responder seam; stop discarding provider usage.
2. Write the assay product/technical spec from this doc; run the vocabulary session against it.
3. Build the control plane (root-minting fan-out, Suite/Adapter pre-registration, the three-state control-ran conformance check).
4. Build the coding Adapter against the official `swebench` harness; differential-test on gold instances.
5. Run the first pre-registered endpoint; report per-dimension with the null rule live.
6. Send the built layer back to the adversarial panel before it becomes a daily driver.

---

## Findings-resolution trace

| Finding (panel) | Resolution |
|---|---|
| A1 — embedded_substrate inner_root mandatory; run-granularity provenance | §2: mint N roots in fan-out; Oracle reads two records |
| A2 / M2 — "Oracle reads the log" false for external graders | §3: two Oracle classes; external-grader = run-and-observe, labeled |
| A3 — no token/time data on the record | §5: `ModelUsage` event at the Responder seam (built, Sprint 1) |
| A4 — "eval is replayable" inverted | §3: only orchestration replayable; currency-gate with determinism-skip |
| A5 — meta-topology is over-engineering | §2: plain-Python control plane; embedded_substrate for arms only |
| D-Rule2 — delta-in-the-type unenforceable | §4.1: executable three-state control-ran check |
| D-vocab — invents, not transcribes; not session-ready | §1 status: spec first, then session; name deferred |
| M-compute — cost / "matched compute" framing | dropped — no money here; tokens + time are measurements; baseline is a single model |
| M-honestnull — degrees of freedom hide the null | §4.3: pre-registered primary endpoint + published null rule |
| M-stats — power hand-waved; seeds non-deterministic | §4.6: paired McNemar across instances; MDE before running |
| M-Adapter — Adapter substitutes the benchmark | §6: official swebench harness; held-out tests; gold differential-test |
| contamination — a sentence, not a mechanism | §4.7: dated split primary; authored truth surface-probe-tested |
| objectivity leak (tau-bench user-sim, LLM graders) | §3/§6/§7: tau-bench deferred; no model in scorer round 1 |
