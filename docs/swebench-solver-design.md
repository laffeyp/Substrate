# SWE-bench solver — vanilla topology design (v1)

Status: design for review. No code yet. Target: a SIMPLE, non-agentic Substrate-native solver that
produces a `model_patch` for a SWE-bench instance, graded by the proven `assay/swebench.py` oracle.

The SDD solver (verify-against-real-API preflight + dual-contract grade + correction loop as
error-correction that makes the model write better) is a deliberate **v2** that wraps this. Not now.

## 1. Scope and shape

Input: a SWE-bench instance — `repo`, `base_commit`, `problem_statement` (the issue), and the repo
itself checked out at `base_commit`. Output: `model_patch`, a unified git diff that resolves the issue.

Three plain phases, no tool use, modeled on Agentless (the one non-agentic approach with verified
adoption — OpenAI used it for GPT-4o/o1; arxiv 2407.01489):

```
LOCALIZE            REPAIR                       SELECT
repo tree skeleton  best-of-N SEARCH/REPLACE     run regression tests (repo's own)
  -> suspect files    apply to a repo clone       + a generated reproduction test
  -> suspect elems    git diff -> candidate patch  rerank candidates -> one model_patch
  -> edit locations   (N candidates)
```

What we KEEP from our own build (the prompt-factory is reference-only — never reuse its code):
- **SEARCH/REPLACE edits**, not unified diffs (LLMs miscount `@@` lines — the prompt-factory learned
  this; `patch_applier.py` is the hardening spec to re-implement: unique-match, overlap, CRLF, atomic).
- **best-of-N** dispatch + the **correction loop** (apply -> validate -> rollback -> feed error -> retry).

What we TAKE from Agentless (the two things we lack):
- **Localization** — the front-end. The prompt-factory assumed you already knew the files; SWE-bench
  gives you an issue and a repo. v1: LLM-on-repo-tree-skeleton for file-level (skip the embedding arm
  for v1 — add later if recall is poor), then class/function skeletons -> elements, then edit lines.
- **Test-based selection** — generate a reproduction test from the issue + run the repo's existing
  tests; rerank the N candidates by what passes. v1: majority vote on AST-normalized patches, gated on
  regression-pass, reproduction-test as the tiebreak (fall back to regression-only, per Agentless).

What we SKIP (the complexity traps): Moatless MCTS, AutoCodeRover call-graph program analysis, Aider
repo-map. v1 scales Agentless's 40-patch / 40-reproduction-sample budget WAY down (small N) — the
shape matters, the brute-force count is a knob.

## 2. The firewall (the load-bearing invariant)

The solver MUST NOT see the held-out tests. In SWE-bench those live in `test_patch`, which adds the
`FAIL_TO_PASS` tests and is applied ONLY at grade time. So the firewall is **structural, not a check**:

- The solver operates on the repo **at `base_commit`** — `test_patch` is not in that tree, so the
  solver physically cannot read `FAIL_TO_PASS`.
- The solver's own SELECT-phase validation runs only (a) the repo's **pre-existing** tests (regression)
  and (b) a reproduction test the solver **itself generates** from the issue text. Neither is the grade.
- The grade (the `assay/swebench.py` oracle) applies `test_patch` and runs `FAIL_TO_PASS` +
  `PASS_TO_PASS` in the instance's Docker image — entirely outside and after the solver.

Open question for review: is "repo at base_commit excludes test_patch" true for EVERY instance, or do
some repos carry a test file the gold fix also edits? If the gold `patch` (not `test_patch`) touches a
test file, the solver could edit it — acceptable (that's a real fix), but worth confirming the
`test_patch`/`patch` split is clean.

## 3. Substrate mapping (the eight words)

The record replaces the prompt-factory's hand-rolled `signal_emitter.py` (which is an event log
rebuilt by hand — Substrate's Bus does this natively). Per instance, the pipeline is a chain of
Producers over one record; across instances it fans out (the assay Route).

- **Producers**: `Localizer` (emits `SuspectFiles` -> `SuspectElements` -> `EditLocations`),
  `Repairer` (emits `CandidatePatch` ×N — the best-of-N fan-out), `Selector` (emits `SelectedPatch`).
- **Bus / record**: every stage's output is a typed record; the solve is fully replayable from it.
- **Views**: `localization` (current suspect set), `candidates` (the N patches + their apply/test
  status), `verdict` (selected patch + why).
- **Predicates / Triggers**: "N candidates present -> run SELECT"; "candidate failed to apply ->
  correction-loop retry"; "no patch passes reproduction -> fall back to regression-only selection".
- **Routes**: instance -> solver chain. In the assay, each ARM is a solver CONFIG (e.g., model, N,
  with/without reproduction test) routed over the same instance set.
- **TerminationPolicy**: a patch is selected, OR the budget (calls/time) is exhausted -> emit the
  best-available (or empty) patch. Never hang.
- **Topology**: `swebench_solver` — the assembled graph above.

## 4. Where Docker enters (ties to the containerization decision)

Two distinct Docker touches, both on the per-instance image we already proved runs here (x86 under
emulation on arm64; native x86 on a cloud box):
1. SELECT-phase test execution (regression + reproduction) — the solver's OWN validation, in the
   instance env. This is new wiring (the solver must run tests in the container).
2. The final grade — the swebench oracle (already working).

This is why containerization is required for the SWE-bench path (see
`docs/swebench-bridge-mapping.md`): not just the grade, but the solver's own test-based selection
needs the instance environment. The local-arm64-emulated path works for development; the reportable
run belongs on x86.

## 5. v1 cut lines (what's deliberately minimal)

- File localization: LLM-on-skeleton only (no embedding arm). Add embedding if recall is the bottleneck.
- N small (e.g., 3-5 candidates, not 40). The assay measures whether N helps; don't assume.
- Reproduction test: single generation, not 40 samples. Selection leans on regression + majority vote.
- Python repos only (SWE-bench is Python). The Swift-bound `codebase_grepper`/`preflight`/`drafter`
  ideas (verify-against-real-API) are the SDD-solver v2 layer, rebuilt on Python AST.

## 6. What to scrutinize (for the reviewer)

1. The firewall claim in §2 — is base_commit genuinely free of the held-out tests for all instances?
2. The Substrate mapping in §3 — is per-instance-chain + across-instance-fan-out the right decomposition,
   or is the best-of-N fan-out better as a sub-topology?
3. The v1 cut lines in §5 — is dropping the embedding-localization arm too aggressive for recall?
4. Does the SELECT-phase Docker test execution (§4) belong inside the solver topology, or as a separate
   graded seam (like the oracle) to keep the solver pure?
