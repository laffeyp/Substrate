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
repo tree skeleton  best-of-N SEARCH/REPLACE     run regression (repo-DERIVED set, NOT the PASS_TO_PASS field)
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
- **Bus / record**: every stage's output is a typed record. "Replayable from the record" means
  **re-derivable (L1/L2), not re-executable** — the MODEL calls (LOCALIZE, REPAIR) are themselves
  run-and-observe (non-deterministic), exactly like `coding_flow`; the test-execution seam (§4) is the
  same. The record is the honest L1/L2 trace, not a promise of byte-identical re-execution.
- **Metering**: every phase emits **ModelUsage onto the record from the first commit** — LOCALIZE, each
  REPAIR candidate, SELECT (calls/tokens/time). The coding run shipped with an all-zero compute axis
  because ModelUsage didn't persist; this is new code, so the matched-compute discipline (§6) is wired
  in from day one, not backfilled.
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
   - Firewall scope: the solver **DERIVES its regression set from the repo at `base_commit`** (the
     existing suite, or tests in/near the suspect files) and must NOT consult the instance's
     `PASS_TO_PASS` list — that list is grade metadata, and handing it to the solver is a subtle
     grade-metadata channel (a real solver in the wild has no `PASS_TO_PASS`; the assay solver must not
     either). Run it as an allowlist (never "run everything", which could sweep in a file `test_patch`
     later turns into a `FAIL_TO_PASS`). Treat the reproduction test as the solver's own recorded artifact.
2. **The final grade** — the swebench oracle (already working), entirely after and outside the solver.

This is why containerization is required for the SWE-bench path (see `docs/swebench-bridge-mapping.md`):
not just the grade, but the solver's own test-based selection needs the instance environment. The
local-arm64-emulated path works for development; the reportable run belongs on x86.

## 4b. The REPAIR applier contract (pin before code — review #54 P1, highest mechanical risk)

The whole REPAIR phase rests on applying LLM-emitted edits to a clone and emitting a clean diff. If the
applier is ambiguous, whitespace/CRLF-fragile, or mishandles overlapping edits, candidates fail to APPLY
for MECHANICAL reasons unrelated to model quality — confounding every number the assay produces (you
can't tell "model wrote a bad fix" from "applier dropped a good one"). This is the one component where a
v1 shortcut poisons the measurement rather than just lowering it. The committed contract (re-implemented,
NOT reused from the prompt-factory):
- **Unique-match-or-reject**: each SEARCH block must match exactly once in the target file; zero or
  multiple matches -> reject that candidate with a structured reason (fed back to the correction loop).
- **Overlap handling**: resolve all blocks against the ORIGINAL file, splice in one pass; overlapping
  spans -> reject (a worker error, not a silent mis-apply).
- **Whitespace / CRLF**: detect and preserve the file's line endings; normalize for matching, restore on
  write.
- **Atomic, all-or-nothing**: a candidate's blocks all apply or none do; never a half-applied tree.
- **Output is `git diff` on the clone, NEVER hand-built hunks**: apply edits to the checked-out repo,
  then `git diff` produces `model_patch`. This is the committed rule, not a diagram aside.

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
  Its **reliability is itself a measured number** — bank how often the self-generated repro test agrees
  with the eventual grade, so "repro as tiebreak" is evidenced, not assumed. (Selecting on a repro test
  inferred from the issue is legitimate — it IS the task — not a leak.)
- Python repos only (SWE-bench is Python). The Swift-bound `codebase_grepper`/`preflight`/`drafter`
  ideas (verify-against-real-API) are the SDD-solver v2 layer, rebuilt on Python AST.

## 6. Forward note — when this becomes an assay arm (not v1)

The three equivalence gates and matched-compute discipline from reviews #2-#3 apply the moment the
solver is an assay ARM: the per-instance firewall assertion (§2), the ~7.8% grader-error axis (§2) as a
measured oracle-error band, matched compute across arms (tokens/calls/time), and the power floor before
any "reached SOTA / matched agent X" verdict. The solver design is upstream of that; the headline must
not outrun those gates.

## 7. SDD adherence — how the solver is BUILT (not just what it does)

The solver is built under the same SDD discipline that governs the rest of substrate (catalog:
`sdd-kit-2/TECHNIQUES.md`). The runtime SDD layer (verify-against-real-API, dual-contract self-grade)
is the v2 SDD-solver; this is about the BUILD process adhering to SDD:

- **Vocabulary-first (#1, #2, #4-#6).** The solver's records are a typed vocabulary designed BEFORE code,
  reviewed like a schema: `SuspectFiles` -> `SuspectElements` -> `EditLocations` -> `CandidatePatch` ×N
  -> `TestResults` -> `SelectedPatch`, plus `ModelUsage` per phase. Categories align with the phases
  (LOCALIZE / REPAIR / SELECT), not files (#5). Payloads are minimal-but-complete — exactly enough to
  reconstruct the decision (#6): recall@k inputs, the apply/test status, the compute. Substrate's typed
  records enforce schema-at-the-mouth natively (#2).
- **Chain-of-small-sprints (#12, #17), architecture-then-functional (#14).** Built as ≤2-file sprints:
  (a) the vocabulary + topology skeleton (architecture, plan-mode), (b) the SEARCH/REPLACE applier
  (its contract is §4b), (c) Localizer, (d) the nested best-of-N+correction sub-topology, (e) Selector +
  the test seam, (f) the swebench-oracle wiring. Each closes clean before the next.
- **Dual + observation contract (#23, #24) — load-bearing here.** The solver is behavior-heavy (it runs
  models AND Docker), so every behavior-touching sprint carries an **observation contract** run FOR REAL,
  not green-on-wiring: localize on a real instance and check recall@k against the gold files; repair
  produces a patch that actually applies + `git diff`s; select runs real tests in the real container.
  Green is not proven (the "be your own skeptic" rule) — the gold-patch smoke (flask-4045 RESOLVED on
  arm64) is the first confirmed-good fixture (#38), reused as a regression fixture.
- **Typed halts, no silent decisions (#28, #29).** The firewall disjointness check (§2), an instance that
  fails it, a candidate that won't apply, a budget exhaustion — each is a typed status / flagged
  exclusion, never a silent pass. TerminationPolicy never hangs.
- **The assay arm structure IS techniques #39 + #40.** #39 names SWE-bench Verified as the carrier
  benchmark and demands the dimensions (quality / speed / reliability / compute) be reported SEPARATELY —
  which the assay layer + the matched-compute axis already do. #40 (the fidelity test: prose-context arm
  vs signal/discipline-context arm) is EXACTLY the eventual vanilla-solver-vs-SDD-solver comparison — the
  clean way to show whether the SDD discipline lifts resolution rate. The pre-registration + contamination
  + matched-compute cautions (#41) are the cargo-cult gates from reviews #2-#3.
- **Additive, originals untouched (#36, #37).** This doc is additive; the prompt-factory is reference-only
  and never edited.

## 8. Fold status

Review #53: P1 firewall §2 FOLDED · P2 mapping §3 FOLDED · P3 localization-recall §5 FOLDED · P4
SELECT-Docker §4 FOLDED.
Review #54 (CONFIRMED): P1 applier contract §4b PINNED · P2 SELECT allowlist repo-derived (NOT
PASS_TO_PASS) §4 FOLDED · P3 per-phase ModelUsage §3 FOLDED · lower notes (replay precision §3,
reproduction-test reliability §5) FOLDED.
