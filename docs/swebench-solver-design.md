# SWE-bench solver — vanilla topology design (v1)

Status: design, reviewed (folds review #53). No code yet. Target: a SIMPLE, non-agentic
Substrate-native solver that produces a `model_patch` for a SWE-bench instance, graded by the proven
`assay/swebench.py` oracle.

The SDD solver (verify-against-real-API preflight + dual-contract grade + correction loop as
error-correction that makes the model write better) is a deliberate **v2** that wraps this. Not now.

## 1. Scope and shape

Input: a SWE-bench instance — `repo`, `base_commit`, `problem_statement` (the issue), and the repo
itself checked out at `base_commit`. Output: `model_patch`, a unified git diff that resolves the issue.

Three plain phases, no tool use, modeled on Agentless (the one non-agentic approach with verified
adoption — OpenAI used it for GPT-4o/o1; arxiv 2407.01489):

```
LOCALIZE            REPAIR                       SELECT
repo tree skeleton  best-of-N SEARCH/REPLACE     run regression tests (repo's PASS_TO_PASS-eligible set)
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
  gives you an issue and a repo. v1: LLM-on-repo-tree-skeleton for file-level (the embedding arm is a
  v1 cut — see §5, gated on a measured recall number), then class/function skeletons -> elements, then
  edit lines.
- **Test-based selection** — generate a reproduction test from the issue + run the repo's existing
  tests; rerank the N candidates by what passes. v1: majority vote on AST-normalized patches, gated on
  regression-pass, reproduction-test as the tiebreak (fall back to regression-only, per Agentless).

What we SKIP (the complexity traps): Moatless MCTS, AutoCodeRover call-graph program analysis, Aider
repo-map. v1 scales Agentless's 40-patch / 40-reproduction-sample budget WAY down (small N) — the
shape matters, the brute-force count is a knob.

## 2. The firewall (the load-bearing invariant)

The held-out, graded set is **`FAIL_TO_PASS`** specifically — the issue's new tests, which live in
**`test_patch`** and are applied ONLY at grade time. The firewall is **structural, not a check**:

- `FAIL_TO_PASS` is, by construction, NOT in the gold `patch` (defined as the PR diff MINUS test code)
  and NOT in the `base_commit` tree. The solver, working at `base_commit`, physically cannot read the
  graded assertions.
- What `base_commit` DOES contain, and what SELECT deliberately USES: the repo's pre-existing tests —
  i.e. the **`PASS_TO_PASS`/regression** set. So "the solver can't see the held-out set" means
  `FAIL_TO_PASS`, not "tests" in general; the regression tests are present and are supposed to be run.
- The grade (the `assay/swebench.py` oracle) applies `test_patch` and runs `FAIL_TO_PASS` +
  `PASS_TO_PASS` in the instance's Docker image — entirely outside and after the solver.

ASSERT it, don't assume it (the patch/test_patch split is a curation HEURISTIC, imperfect — which is
why Verified is human-curated). The same data-level disjointness discipline the coding bank already has:
- Per instance, require `files(patch) ∩ files(test_patch) == ∅` AND every `FAIL_TO_PASS` test file
  ∈ `files(test_patch)`. Exclude or flag any instance that fails.
- Prefer **SWE-bench_Verified** (500, human-curated) as the base set over Lite/full.

KNOWN ORACLE-ERROR AXIS (record it; do not claim it away). The bigger firewall-adjacent risk is the
INVERSE of leakage — the grade is too WEAK, not too strong. An ICSE'26 empirical study ("Are 'Solved
Issues' in SWE-bench Really Solved Correctly?", arxiv 2503.15223) finds SWE-bench validates only the
test files in `test_patch` and ignores other coverage, so **~7.8% of plausible patches are actually
incorrect (~4.5% absolute resolution-rate inflation)**. This is the SWE-bench analogue of the
grader-validity axis already flagged for the coding bank: `resolved` is not ground truth. Carry it as
a measured oracle-error axis on any headline.

## 3. Substrate mapping (the eight words)

The record replaces the prompt-factory's hand-rolled `signal_emitter.py` (an event log rebuilt by hand
— Substrate's Bus does this natively). Per instance, the pipeline is a chain of Producers over one
record; across instances it fans out (the assay Route).

- **Producers**: `Localizer` (emits `SuspectFiles` -> `SuspectElements` -> `EditLocations`, a genuine
  sequential chain — each step is conditioned on the prior), `Repairer` (emits `CandidatePatch` ×N),
  `Selector` (emits `SelectedPatch`).
- **REPAIR is a nested sub-topology, factored ONCE and reused.** best-of-N + apply->validate->rollback
  ->feed-error->retry is the SAME machinery `coding_flow` already implements, and `code_evolution` is a
  third consumer of the same shape. Use Substrate's `embedded_substrate` composition: factor
  "best-of-N + correction loop" as one nested topology that the swebench `Repairer`, `coding_flow`, and
  the EA all NEST — re-rolling the loop a third time is three places for the currency-gate / determinism
  bugs to diverge.
- **Bus / record**: every stage's output is a typed record; the solve is replayable from it (modulo the
  run-and-observe test seam, §4).
- **Views**: `localization` (suspect set), `candidates` (the N patches + apply/test status),
  `verdict` (selected patch + why).
- **Predicates / Triggers**: "N candidates present -> run SELECT"; "candidate failed to apply ->
  correction-loop retry"; "no patch passes reproduction -> fall back to regression-only selection".
- **Routes**: instance -> solver chain. In the assay, each ARM is a solver CONFIG (model, N,
  with/without reproduction test) routed over the same instance set.
- **TerminationPolicy**: a patch is selected, OR the budget (calls/time) is exhausted -> emit the
  best-available (or empty) patch. Never hang.
- **Topology**: `swebench_solver` — the assembled graph above.

## 4. Where Docker enters (ties to the containerization decision)

Two distinct Docker touches, both on the per-instance image we already proved runs here (x86 under
emulation on arm64; native x86 on a cloud box):

1. **SELECT-phase test execution** (regression + reproduction) — the solver's OWN validation. It lives
   INSIDE the solver topology (the selector triggers on its results to rerank — moving it outside would
   sever the feedback the phase exists for), but it shares the oracle's NATURE: a Docker subprocess is
   non-deterministic, run-and-observe. So model it as a typed **external-observation Producer seam** that
   emits `TestResults` onto the record with `replayable=False` (captured once), exactly the oracle's
   class — positioned inside the chain. Selection LOGIC stays pure/replayable; test EXECUTION is the
   recorded run-and-observe seam. The record stays honest about what is reproducible.
   - Firewall scope: run the regression set as an **allowlist of the repo's pre-existing tests**, not
     "run everything" — never let it sweep in a file that `test_patch` later turns into a `FAIL_TO_PASS`.
     Treat the reproduction test as the solver's own recorded artifact.
2. **The final grade** — the swebench oracle (already working), entirely after and outside the solver.

This is why containerization is required for the SWE-bench path (see `docs/swebench-bridge-mapping.md`):
not just the grade, but the solver's own test-based selection needs the instance environment. The
local-arm64-emulated path works for development; the reportable run belongs on x86.

## 5. v1 cut lines (what's deliberately minimal — but instrumented)

- **File localization: LLM-on-skeleton only (no embedding arm) — gated on a MEASURED recall number.**
  Agentless deliberately runs BOTH arms (LLM-on-skeleton AND text-embedding-3-small retrieval, 512-chunk,
  merged) because they are complementary; the embedding arm catches files the skeleton-prompt misses on
  large repos / vague issues. Localization recall is the hard ceiling on the whole pipeline — you cannot
  repair a file you never localized. So the cut is acceptable ONLY because file-level **recall@k is a
  first-class measured number from day one**: `recall@k = (gold-patch files ⊆ suspect files?)` per
  instance (the gold patch's touched files are the ground truth). "Add the embedding arm" then becomes a
  data-driven decision when recall is the bottleneck, not a guess — and a low resolve rate is
  attributable to localization vs repair instead of an un-ablated dead end.
- N small (e.g., 3-5 candidates, not 40). The assay measures whether N helps; don't assume.
- Reproduction test: single generation, not 40 samples. Selection leans on regression + majority vote.
- Python repos only (SWE-bench is Python). The Swift-bound `codebase_grepper`/`preflight`/`drafter`
  ideas (verify-against-real-API) are the SDD-solver v2 layer, rebuilt on Python AST.

## 6. Forward note — when this becomes an assay arm (not v1)

The three equivalence gates and matched-compute discipline from reviews #2-#3 apply the moment the
solver is an assay ARM: the per-instance firewall assertion (§2), the ~7.8% grader-error axis (§2) as a
measured oracle-error band, matched compute across arms (tokens/calls/time), and the power floor before
any "reached SOTA / matched agent X" verdict. The solver design is upstream of that; the headline must
not outrun those gates.

## 7. Review #53 fold status

- P1 (firewall, §2): FOLDED — `FAIL_TO_PASS` named as the held-out set (regression is present/used); the
  per-instance `files(patch) ∩ files(test_patch) == ∅` assertion added; SWE-bench_Verified preferred; the
  ~7.8% grader-error axis recorded.
- P2 (mapping, §3): FOLDED — best-of-N + correction loop factored as a nested sub-topology reused by
  coding_flow / swebench / code_evolution; LOCALIZE kept as a sequential chain.
- P3 (localization recall, §5): FOLDED — file-level recall@k is a measured number gating the
  embedding-arm cut.
- P4 (SELECT Docker, §4): FOLDED — test execution inside the topology as a run-and-observe Producer seam
  (replayable=False), selection logic pure, regression scoped to a pre-existing-tests allowlist.
