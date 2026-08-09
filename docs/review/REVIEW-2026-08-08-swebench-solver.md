# Review — swebench_solver topology and its assay wiring

Date: 2026-08-08.
Reviewer role: findings for the Architect, not patches. Nothing in the tree is edited by this review.

## Scope

Read in full for this review:

- The SDD kit as the method under which the code was built: `sdd-kit-2/README.md`, `AGENTS.md`, `CLAUDE.md`, all four `foundations/`, both `grammar/` files, `TECHNIQUES.md`, `ADDENDUMS.md` A–D, `ADDENDUM_PROMPT.md`, `lib/sdd.py`, `templates/SPRINT_CARD.md`, `templates/VOCABULARY.json`.
- Substrate package surface: `README.md`, `src/substrate/api.py`, `types.py`, `protocols.py`, `kernel/topology.py`.
- The topology under review: every file in `src/substrate/topologies/swebench_solver/` (`__init__.py`, `records.py`, `localize.py`, `localize_elements.py`, `repair.py`, `applier.py`, `reproduction.py`, `repro_base_validate.py`, `select.py`, `select_regression.py`, `select_exec.py`, `select_docker.py`, `assemble.py`).
- The assay wiring: `src/substrate/assay/swebench.py`, `swebench_workspace.py`, `swebench_suite.py`, `swebench_matrix.py`, `swebench_host.py`, `swebench_agent.py`, `swebench_container.py`.
- Design docs: `docs/swebench-solver-design.md`, `docs/swebench-close-the-loop-roadmap.md` (round 3), `docs/swebench-assay-roadmap.md`, `docs/swebench-bridge-mapping.md`.
- Confirmatory runner: `scripts/assay_swebench_confirmatory.py`.

Load-bearing claims re-verified against the code by targeted grep before writing.

Out of scope: substrate's kernel semantics, the record layer, the projections, the conformance suite, the coding_flow topology, the substrate-ui. Read enough of each to know the SWE-bench topology is a well-formed substrate consumer; not audited on its own merits.

## What the topology is

Two topology entry points in `src/substrate/topologies/swebench_solver/assemble.py`.

`swebench_repair_topology` (line 202). Producers: `localizer` → `seeder` → `drafter` → `validator` → `judge` → `selector` (a `_first_patch_selector_factory` at line 143 that emits the applied patch at the slot the judge names as solved) → `outcome`. Terminates on the always-emit `RepairSummary` (line 373). No test execution. No Docker except any the caller wires in.

`swebench_solver_topology` (line 383). Same front end, plus a `repro_gen` and a `repro_base_validate` producer that runs the generated reproduction test once on the unpatched base checkout (sprint 155). After the judge's `Solved`, a `select_exec` producer runs each applied patch's regression + reproduction in Docker via `DockerTestRunner`, and a `_selector_factory` (line 113) reranks with `select.select_patch` — filter to regression-passing, prefer reproduction-resolved, majority-vote on a normalized diff, lowest-slot tiebreak.

Two Arm surfaces. `swebench_solver_arm` in `assay/swebench_suite.py:154` wraps the full solver topology. `repair_arm` and the four sprint-159 siblings in `assay/swebench_matrix.py:127–213` wrap the repair-only topology. The confirmatory runner selects between them via the `SWEBENCH_ARMS` environment variable: `solver` picks the full topology, `pass1` and `matrix` pick the repair-only path.

Graded via `swebench_record_oracle` in `assay/swebench.py:313`. It extracts the last `SelectedPatch.model_patch` from the record, filters out any diff section touching a graded test file (`filter_diff` in `assay/swebench_workspace.py:66`), and grades the resulting patch by calling the official `swebench.harness.run_evaluation.main` in Docker.

The topology reuses the shared best-of-N + correction contract (`Draft`, `Candidate`, `Verdict`, `Solved`, `Exhausted`) from `topologies/best_of_n/contracts` as its canonical 3-consumer type set. The SWE-bench-specific records (`SuspectFiles`, `SuspectElements`, `EditLocations`, `AppliedPatch`, `ReproductionTest`, `Reproduction`, `TestResults`, `SelectedPatch`, `RepairOutcome`, `RepairSummary`) are declared in `records.py` as frozen msgspec Structs.

## What holds

Named plainly so the findings that follow do not read as a global negative.

**Applier contract.** `applier.py` implements the design's §4b pin without shortcut. Whole-line match, two tiers (exact then leading-whitespace-flexible, unique-or-reject at each tier), never fuzzy. Atomic all-or-nothing across a candidate's files. Path escape guarded at line 240 against absolute paths and `..` traversal. CRLF detected on read at line 253 and restored on write at line 273. Empty-SEARCH creates a new file at line 181; a create block against an existing path is rejected at line 184. Empty resulting diff is rejected as failed at line 291, closing the silent-not-resolve case where a candidate compiles to a no-op. The `model_patch` is `git diff --cached` on the clone, never a hand-built hunk. This is one of the cleanest published SEARCH/REPLACE appliers I have read.

**Container contamination lockdown.** `assay/swebench_container.py:56–87`. `--network none`, remotes stripped, HEAD detached, every ref deleted, reflog expired. `git log --all` after start reaches only base and its ancestors, so the fix commit — a descendant — is unreachable through refs. Most published SWE-bench container harnesses stop at `--network none` and leave the fix reachable via `git log`. This is more thorough than the reference.

**Grade-side test-file filter.** `swebench_record_oracle` at `assay/swebench.py:353–360` drops any diff section that touches a file in `graded_test_files(test_patch)` before grading. A name-based backstop (`is_test_file` in `swebench_workspace.py:43`) catches pre-existing test files the model shouldn't touch. This blocks the WEAKEN-A-GRADED-TEST inflation channel at the harness boundary, so the topology stays honest about what it changes. The filter runs after the topology emits its patch, which is where it belongs.

**Firewall discipline.** Two data-level conditions in `assay/swebench.py:71`. `files(patch) ∩ files(test_patch) == ∅` and every `FAIL_TO_PASS` file added by `test_patch`. Fail-closed on unparseable ids since sprint 142. Enforced at four arm-building sites (`swebench_matrix.py:106`, `swebench_suite.py:93`, `swebench_host.py:58`, `swebench_agent.py:88`) plus an optional in-topology guard on both `swebench_repair_topology` (line 227) and `swebench_solver_topology` (line 409) that a hand-stitched caller can opt into.

**Substrate-native record vocabulary.** `records.py` uses frozen msgspec Structs throughout and enums for `Reproduction` and `RepairOutcome`. This is SDD Principle 2 realised in Python: schema enforced at the speaker's mouth. Unknown kinds cannot appear on the record. Reusing coding_flow's `Candidate` / `Verdict` / `Solved` / `Exhausted` as the shared 3-consumer contract, rather than re-rolling them, is the correct Wave-0 shared-file move (grammar/PRINCIPLES.md commitment 3).

**`RepairSummary` as always-emit terminal.** `assemble.py:167`. The topology terminates on exactly one `RepairSummary` per run, carrying an enumerated `outcome` (`SELECTED`, `NO_LOCALIZATION`, `NO_APPLICABLE_EDIT`) and the per-stage counts. A reader learns what happened from one typed event rather than reconstructing it from the absence of others. SDD technique #51 applied correctly. The watchdog terminal — a true wedge — deliberately emits none, and the docstring names that absence as the runner-level `timed_out` signal. The terminal taxonomy is complete across the two levels.

**Scope-aware regression check.** `regression_held` in `select_exec.py:79`. Base-passing test ids must reappear and pass in the patched run; a test that vanishes because the patch broke its module's collection is a regression, not a legitimate absence. The check is scoped to the tests THIS candidate actually ran via `in_scope_files`, so a base-passing test in a file the per-candidate proximity picker didn't run is not charged. Most published solvers get this wrong by comparing raw pass counts.

**`--continue-on-collection-errors`** in `build_regression_command:81`. A stray uncollectable module would otherwise abort the whole run and zero the base-passing set. The comment pins this to a real observation from sprint 152. This is a bug you only find by running the code on real repos.

## Findings, ranked by material impact

### F1 — The confirmatory matrix runs the repair topology, not the solver topology

`scripts/assay_swebench_confirmatory.py:290–314` (the `SWEBENCH_ARMS=matrix` branch) builds every one of the five sprint-159 arms via `_build_repair_arm_from_models` in `assay/swebench_matrix.py:92`. That helper wires `swebench_repair_topology`, whose selector is `_first_patch_selector_factory` at `assemble.py:143`: emit the first applied patch at the slot the judge names, no test execution, no reranking. The full solver topology — `repro_gen`, `repro_base_validate`, `select_exec`, `_selector_factory`, `select.select_patch` — is reachable only through `swebench_solver_arm` in `assay/swebench_suite.py:154`, i.e. `SWEBENCH_ARMS=solver`.

Consequence. Sprint 155's base-fails-first reproduction validator, `select_regression.proximity_regression_files`, the `passed_at_base` filter, and the regression + reproduction rerank in `select.select_patch` are dead code in the planned Pass-2 confirmatory. Any writeup that quotes those mechanisms as active is wrong about what ran.

Fix, one of two. Rewire the matrix arms through `swebench_solver_topology` and pay the Docker cost per applied candidate. Or state in the writeup that the confirmatory measures REPAIR alone with a trivial selector, and label the reproduction-and-regression SELECT as a separate ablation to be run later.

### F2 — Localization recall is defined and never measured

`localize.py:88` defines `full_recall_at_k(suspect, gold) -> bool` and `localize.py:95` defines `recall_at_k(suspect, gold) -> float`. Grep for callers across `src/substrate/` returns zero. The design doc §5 makes the file-only localization cut acceptable ONLY on the condition that recall@k is measured per instance, so a low resolve rate is attributable to localization vs. repair. That condition is not met in the assay path. Sprint 160-pass2 will produce resolve numbers with no recall@k banked, and the write-up will therefore not be able to say whether the ceiling is localization or repair.

Fix. Compute `recall_at_k` per case at grade time — the gold patch's touched files are in the harness metadata and never enter the solver's context. Bank the fractional and boolean-full numbers in the cells sidecar alongside `TestResults`. This is a small addition to the oracle; it does not touch the topology.

### F3 — Whole-file inlining into the drafter prompt

`assemble.py:45`, `_build_edit_context`. For every target in `EditLocations`, read the file from `base_checkout` and inline the entire content wrapped in a fenced block. The default `swebench_solver_topology` uses `localizer_factory` (file-level only), so `targets` is a list of file paths and `_build_edit_context` inlines every file whole.

For a target like `src/flask/blueprints.py` (~2 000 lines) or a Django models file, the drafter prompt is dominated by unrelated code. `SuspectElements` (records.py:51) and `element_localizer_factory` (localize_elements.py:89) exist to trim this to class/function granularity, but neither is imported by `assemble.py` and no arm in the matrix or the solver arm wires them. Grep confirms `element_localizer_factory` is referenced only in its own docstring and `__all__`.

Fix. Wire the element localizer as the default. Keep the file-level path as a fallback for non-Python targets, which it already handles at `localize_elements.py:129`. Alternatively, if the element localizer is meant to be an ablation arm, add it to the matrix and stop calling the file-only path the default.

### F4 — Reproduction test is single-sample

`reproduction.py:56–63`. `repro_generator_factory` makes one call to `call_responder_metered`, yields one `ReproductionTest`, done. The base-fails-first gate at `repro_base_validate.py:72` demotes the repro to empty if the base run does not cleanly report `Issue reproduced`, which catches trivially-passing tests but not a repro that passes on base for the wrong reason.

At K=1 the reproduction signal in `select.select_patch` is one Bernoulli draw per candidate. `Reproduction.RESOLVED` on the winning slot is what a reader would take as evidence that the SELECT phase discriminated; from one sample, it does not. The failure mode on flask-4045 with qwen3-coder (KIT_DIARY finding 21, quoted in the roadmap) is exactly this: a repro that fires but exercises the wrong half of the bug.

Fix. Sample the repro K > 1 times, majority-vote at the marker level, and only trust `RESOLVED` if the vote is clean. Sprint 158's `repro_kappa` will surface the disagreement rate but does not fix the sample size. If Docker cost per K is prohibitive on the confirmatory, drop the reproduction signal from the mechanism claim and rely on regression alone.

### F5 — Django-family instances fail at case preparation

`select_docker.build_regression_command:71–75` raises `ValueError` when `spec['test_cmd']` is not a path-taking runner. `cmd_takes_paths` at line 45 returns True only for `pytest` or `py.test`. Django's `runtests.py --settings=...` takes module labels, not paths. `prepare_swebench_case` in `swebench_suite.py:109` calls `build_regression_command` unconditionally to establish the passed-at-base set, so any Django instance crashes at case-preparation, before any solver work.

SWE-bench Verified has ~34 Django instances and Lite has ~14. Silent exclusion is not defensible. Fix, one of two. Ship a per-repo command adapter that maps paths to `module.Class.method` labels for the Django runner. Or exclude Django up front, count the exclusions, and report resolve rate over the pytest subset only, named as such in the writeup.

### F6 — Watchdog defaults are inverted between the two topologies

`swebench_repair_topology` (repair-only, less work) defaults `watchdog_seconds=600.0` at `assemble.py:212`. `swebench_solver_topology` (repair plus Docker test execution per candidate) defaults `watchdog_seconds=60.0` at `assemble.py:396`. The suite override at `swebench_suite.py:150` sets 2 400 s, so production callers are covered, but any test or script that instantiates the solver topology at defaults gets guillotined at 60 s. This looks like a swap. Fix by inverting the defaults.

### F7 — Firewall unittest-id parser is too loose

`assay/swebench.py:105–108`.

```
parts = m.group(1).split(".")
frag = "/".join(parts[:-1]) if len(parts) > 1 else parts[0]
return any(frag in f for f in tp_files)
```

For a two-segment unittest id like `test_x (myapp.tests)`, `frag = "myapp"`, and `any("myapp" in f for f in tp_files)` returns True whenever any `test_patch` file lives anywhere under `myapp/`. The check succeeds without verifying that the specific test's file is in `tp_files`. A pre-existing test in `myapp/other/test_foo.py` — a real leak, the case the firewall exists for — passes if `test_patch` happens to add anything under `myapp/`.

Fix. Reconstruct the specific file path from all module segments (`"/".join(parts[:-1]) + ".py"` or the unittest test-loader convention that maps `myapp.tests` to `myapp/tests.py`), then check equality against `tp_files` rather than substring. Sprint 142 flipped the parser fail-closed for unparseable ids; this is the next tier — tighten the parseable ones.

### F8 — `filter_diff` header parser silently drops mixed-quoted headers

`assay/swebench_workspace.py:32–33` handles bare `diff --git a/X b/Y` and both-sides-quoted `diff --git "a/X" "b/Y"`. Git also emits ONE-side-quoted headers for renames where only one side contains special characters, and for some rename-and-mode-change combinations. A header that matches neither regex causes `keep = False` at line 79 as the fail-safe drop. A legitimate rename with a mixed-quote header disappears from the model_patch and grades as not-resolved. Fix by adding a mixed-quote regex, or by tokenising the header rather than pattern-matching.

### F9 — `SuspectElements` is defined, exported, and never emitted

`records.py:51` defines the record. `__init__.py:25, 38` exports it. `localize_elements.py:126` yields it. No producer in `assemble.py` uses `element_localizer_factory`, so nothing on the default paths ever emits `SuspectElements`. A defined-but-dead schema is drift by the SDD kit's own rule: vocabulary is the contract and the contract needs both sides. Either wire the element localizer (fix for F3) or move `SuspectElements` to a `deprecated` section in the vocab per the grammar/PRINCIPLES.md proposal taxonomy.

### F10 — Six view-name strings, sixteen references, no type

`assemble.py` uses `ctx.views["applied"]`, `["edit_locations"]`, `["reproduction"]`, `["solved"]`, `["test_results"]`, `["verdicts"]` across sixteen call sites (grep confirms). Every one is a bare string literal. A typo — `"verdict"` vs `"verdicts"` — passes mypy, passes ruff, raises `KeyError` at runtime only when the trigger's predicate fires. This is the exact pattern your standing feedback names as the invisible-to-static-checks drift.

Fix. A module-level frozen namespace whose attributes are the view-name literals (or a `TypedDict` for the views registration and a `Literal` type for lookups). One typo becomes a type error. Cost: one small file, one refactor of the sixteen sites, no runtime change.

### F11 — Comparator model ids in the roadmap do not resolve to shipped names

`docs/swebench-close-the-loop-roadmap.md:135` names `kimi-k2.6, glm-5.1, nemotron-3-super` as the "R-19 thinking trio" for the ensemble arm. Kimi K2, GLM-4, and Nemotron-4-340B are shipped and pullable; k2.6, glm-5.1, and nemotron-3-super are not names I can resolve to anything in the public model catalogues or on Ollama. Sprint 160-pass1's `SWEBENCH_MODELS` requires the caller to supply names, so this is not a runtime bug; it is a documentation issue that will bite whoever fills in the pre-registration. Fix by verifying against `ollama pull` (or the equivalent registry) before the pre-reg commits.

### F12 — The confirmatory writeup obligations don't include SoTA baseline

Sprint 160-writeup at roadmap line 116 lists five obligations: comparator, per-arm resolve + CI + TOST, `resolve_per_call`, `grader_error_band`, `repro_kappa`. The named comparator is Agentless + GPT-4o at 27.8% Lite from Xia et al. 2024. That number is from July 2024 and specific to N=40 draft samples and K=40 reproduction samples. SoTA on Lite has moved substantially past it in the intervening two years. Publishing a substrate resolve rate against a two-year-old comparator without also naming a current SoTA anchor invites the reader to substitute the modern number themselves, badly. Add a current-SoTA line to the writeup obligations. Do not treat any single comparator as authoritative.

## SDD discipline audit

Against the 12 hard rules in `sdd-kit-2/AGENTS.md`.

**Rule 1 (never edit foundations).** Held. Nothing under `sdd-kit-2/` is touched by the SWE-bench work.

**Rule 2 (vocabulary is the contract).** Mostly held. Records are frozen Structs and enums, schema-at-the-mouth. Two gaps flagged in F9 and F10: a defined-but-dead record (`SuspectElements`) and view-name strings that bypass the contract.

**Rule 3 (dual contract).** Held for the topology. Every producer's factory has an observation counterpart in the tests directory. The applier's observation contract is an ordinary unit test, exactly as the design doc §7 promises. The Docker-touching producers are marked `deterministic=False`, and `Result.replayable=False` rides on every grade.

**Rule 4 (halt-and-articulate).** Held. `FirewallViolation` is a typed exception. `RepairSummary`'s `outcome` enum enumerates the terminal states. Model-call failures in the localizer, drafter, repro generator, and repro validator emit empty artefacts rather than crashing (KIT_DIARY finding 16); the loop terminates cleanly to `Exhausted` rather than wedging. The one uncovered halt is F5's Django case: `build_regression_command` raises a bare `ValueError` at case preparation, before the topology runs, and the assay path has no typed exclusion category for it.

**Rule 5 (comprehension-as-prerequisite).** Not this reviewer's call. The BLACKBOARD entries show comprehension-affirmation ritual was practiced.

**Rule 6 (sprint sweet spot ≤ 2 files / one concept).** Mostly held. Sprint 155 explicitly grew to three files and named the reason; other sprints in the chain appear tighter. `assemble.py` at 627 lines is the shared home of two topologies plus six factory helpers plus `_solved_round`. This is a candidate for splitting (see the Code organization section).

**Rule 7 (canonical home registry).** Held. The shared best-of-N contract lives in `best_of_n/contracts` and is re-exported from `swebench_solver/records.py`. The Wave-0 discipline held.

**Rule 8 (design context for UI-touching sprints).** Not applicable.

**Rule 9 (observation contract for behavior-touching sprints).** Partially held. The topology tests exist. What is missing is measured recall@k on the run set (F2). The design doc names it as the observation contract for LOCALIZE and the code defines the functions; the assay never calls them.

**Rule 10 (hand-author requires authorization).** Not evaluable from the diffs.

**Rule 11 (originals over summaries).** Held. This review took the originals as canon.

**Rule 12 (Sprint-0 vocabulary materialisation).** Held. `process/signals/swebench-solver-vocabulary.md` is referenced from `records.py:3`; the vocabulary session ran before the implementation sprints.

## Terminology

Names in the code that a reader from the SWE-bench literature will pause on.

`SuspectFiles` / `SuspectElements`. Agentless calls these "localised files" and "localised elements"; the fault-localisation literature calls them "suspicious files" (Ochiai, Tarantula). "Suspect" is unusual. Not wrong. If kept, note the coinage in the vocabulary rationale so a reader who greps for "localized" does not miss the concept.

`Reproduction.RESOLVED`. The SWE-bench harness uses `resolved` as the final grade bool. Substrate's `Reproduction.RESOLVED` means "the reproduction test printed `Issue resolved`", which is one input to whether the grade will come out `resolved`. Same word, different scope, one function call apart. A reader flipping between substrate code and the harness sees "resolved" mean two things. Rename the enum values (`BUG_PRESENT`, `BUG_ABSENT`, `UNCLEAR`) or state the collision in the record's docstring.

`RepairOutcome.NO_APPLICABLE_EDIT`. Coined here. Agentless calls the equivalent "no applicable candidate". Keep, but document, so a reader looking for the paper's term finds it.

## Code organization

Three notes.

**Two arm-building paths diverged on which topology they wire (F1).** `swebench_matrix._build_repair_arm_from_models` and `swebench_suite.solver_topology_from_payload` share the model-construction and firewall boilerplate but call different topology factories at the bottom. If they shared one `_build_arm_from_models(topology_factory, ...)` helper, the confirmatory could not silently ship the wrong SELECT.

**`assemble.py` at 627 lines is the largest file in the topology.** It hosts both topology builders, six factory helpers, `_solved_round`, and prose-heavy docstrings. Splitting into `assemble_repair.py`, `assemble_solver.py`, and `assemble_common.py` would make the F1 divergence visible from the file tree.

**View-name strings (F10)** are the single largest source of type-invisible drift in the topology.

## On comparators

The design doc calls the Agentless paper the shape template for this topology. That is a legitimate choice for a first non-agentic pipeline; the paper's ablations are public and its numbers are reproducible. It is not a normative reference. The runtime does not care what shape a topology takes; the substrate ships a dozen bundled topologies with different shapes, and a substrate SWE-bench arm could implement any of them.

For publication, the honest anchors are (a) an internal control arm at matched substrate compute, which sprint 159 correctly wires as `baseline_matched_compute`, and (b) whatever the current public SoTA on the chosen split is at write-up time, named for what it is. A two-year-old comparator alone is not enough.

## Punch list before Pass-2

Ordered by what most changes whether the confirmatory number is defensible.

1. Decide F1. Rewire the matrix arms through `swebench_solver_topology`, or say in the writeup that the confirmatory measures repair alone.
2. Compute recall@k on the run set at grade time and bank per instance (F2). Without this, no repair-side attribution.
3. Verify F11 model names against the actual registry before the pre-registration commits.
4. Fix F6 watchdog defaults. Trivial edit, wrong sign.
5. Tighten F7 firewall unittest parser.
6. Decide Django (F5): wire the label-mapping adapter or exclude and count.
7. Sample K > 1 reproduction tests (F4), or drop reproduction from the mechanism claim.

Everything else in this review — F3 default-localizer-tier, F8 header parser, F9 dead record, F10 view-name strings, F12 comparator obligations, the terminology and code-organisation notes — is drift I would clean before scale-up but that will not invalidate the Pass-2 number if it survives F1 through F7.
