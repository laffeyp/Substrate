# REVIEW — un-reviewed sprints 217 through 232b (daily-driver pieces B tail through H)

**Reviewer:** Claude, session 2026-08-28, main-loop (not the reviewer subagent — killed by the Architect at 2026-08-28).
**Scope:** every sprint card in `process/sprints/` whose id is 217 or greater and which had no matching `REVIEW-…-piece-*` doc on file at the moment this review opened. Forty cards total: 217, 217a, 217c, 217d, 217e, 218–222, 223, 223a–f, 224, 224a, 224b (×2), 224c–h, 225, 225a–d, 226, 227, 228, 229, 230, 231, 232, 232b.
**Read against:** sdd-kit-2 in full (README, CLAUDE.md, AGENTS.md, ADDENDUMS.md, TECHNIQUES.md, foundations 01–04, grammar/PRINCIPLES.md, grammar/BOOTSTRAP.md, lib/sdd.py, templates/SPRINT_CARD.md), plus the substrate workspace's BLACKBOARD, KIT_DIARY, ROADMAP-2026-08-25-daily-driver, TASK-BREAKDOWN, PHASE2, WORKING_AGREEMENT, process/signals/, and every prior REVIEW-… doc through 2026-08-26.
**Ground truth checks run:** full-tree grep for retyped lifecycle literals against `constants.py`; sprint-id uniqueness scan; `pass_kind` enum scan against SPRINT_CARD.md; `## signal contract → Emits` presence scan; targeted pytest across every test file that pins these sprints' behavior (141 passed, 1 skipped in 7.62 s, `uv run python -m pytest tests/test_session_topology_end_to_end.py tests/test_session_topology_bundled.py tests/test_session_topology_refuses_all_completed.py tests/test_bundles_229.py tests/test_bundle_slot_binding_230.py tests/test_bundled_app_factories_224b.py tests/test_bundled_topologies.py tests/test_shipped_bundles_231.py tests/test_application_registry_223.py tests/test_applications_integration.py tests/test_cli_chat_218.py tests/test_cli_repl_219.py tests/test_cli_signals_220.py tests/test_cli_slash_221.py tests/test_cli_session_subverbs_222.py tests/test_cli_bundle_subverbs_222.py tests/test_pair_coding_topology.py tests/test_delegate_per_call_child_session_name.py`); full-suite pytest completed at review close: **1093 passed, 5 skipped, 0 failed in 257 s** (the five skips are three real-model tests, one Ollama-live test, one platform guard — none are signal contract gaps; `--ignore=tests/test_realmodel_demos.py -x`).

The review is adversarial on SDD discipline. SDD is the only method by which LLMs write correct code in this project — the substrate. A drift on the substrate is not a stylistic complaint; it is the substrate corroding. The core kernel primitives (Runtime, Producer, Topology, the twelve reserved `substrate.*` lifecycle kinds, the vocabulary lock) are load-bearing and every change to them is flagged explicitly.

Findings ranked most-severe first. Every finding names the exact file and the exact fix path.

---

## F1 — Sprint-id collision at `224b`. Audit-trail spine broken.

`process/sprints/sprint-224b-app-bundled-ci-factories.md` and `process/sprints/sprint-224b-slash-router-real-daemon.md`. Both carry `id: 224b` in frontmatter. Both are closed. Two distinct concerns landed under one addressable card.

Sprint id is the addressable primitive. `AGENTS.md ## Reference order` reads "For sprint card composition: `templates/SPRINT_CARD.md`", and the template says "Copy this template to `sprints/sprint-NNN-{slug}.md` (NNN zero-padded; slug kebab-case)." One `NNN` per card. The BLACKBOARD, the ROADMAP, the KIT_DIARY, every downstream review reference the id to close the loop. When two files share it, every future "sprint 224b" reference is ambiguous. The record does not tell you which. That is exactly the drift SDD is designed to prevent.

Neither card links to the other. Neither is renamed to 224b1/224b2 or to 224b/224b-alt. The scope amendment notes in each explain what they do; nothing in either explains why they share an id.

**Fix path.** Rename one card — the slash-router-real-daemon one is the smaller scope, and reads as a test-hygiene follow-up to 221, not a piece-E deliverable — to a fresh id (224i is next free). Update the frontmatter, rename the file, add a one-line back-pointer at the top: "renamed from sprint-224b to sprint-224i (2026-08-28) — id collision with sprint-224b-app-bundled-ci-factories.md." Grep the BLACKBOARD and KIT_DIARY for `224b`; each mention needs disambiguation. Rule 12 (audit trail is the work) is not violated by the rename because the *original* file stays on disk under its old name via git history; the rename is additive at the surface.

## F2 — Invented `pass_kind` values across the 224-series subs.

`SPRINT_CARD.md` locks `pass_kind` to five values: `architecture | functional | docs | bridge | observation`. That list is the kit's own typed vocabulary — the sprint card's contract with the reader is that the frontmatter parses cleanly against it.

Sprints 224a, 224b (slash-router), 224c, 224d, 224e, 224f, 224g, 224h ship these `pass_kind` values instead:

- `refactor` (224a — wire-error-constants)
- `test-refactor` (224b — slash-router-real-daemon)
- `test-add` (224c — observation-half-on-tools-isolate; 224f — typed-markers-and-boot-scan-test)
- `correctness` (224d — delete-agent-legacy-fallback)
- `cleanup` (224e — noqa-ble001-audit; 224g — code-quality-pass)
- `infra` (224h — lint-gates)

Every one of those is a plausible category of work. The correct move is `vocabulary_change_required` per AGENTS.md hard rule 2 — propose the new values via one of the eight evolution kinds (`NEW_TAG_PROPOSED` on the sprint-frontmatter vocabulary), let the Architect ratify, bump the vocabulary version, and land the new sprints against the ratified set. Instead the tags were minted inline. The exact failure mode grammar/PRINCIPLES.md commitment 3 is written to prevent.

Note this is not a code correctness issue and the sprints themselves are fine as work; the drift is on the methodology's own contract, which is where drift is most corrosive because the tooling that reads the frontmatter (if any is ever built) will silently accept the invented tag or hard-fail unpredictably.

**Fix path.** Either propose the six new values into a v0.2 of the sprint-frontmatter vocabulary (write the proposal into `sdd-kit-2/templates/SPRINT_CARD.md` as a new file `SPRINT_CARD-round2.md` per feedback-no-in-place-edits-new-versions-only; rule 12 preserves the original), or re-classify the seven cards against the existing five: `refactor`/`cleanup`/`test-refactor` → `functional` (or the new `pass_kind: hygiene` if proposed); `test-add` → `observation` (the pass_kind meant for observation-first sprints); `infra` → `architecture` (build-and-test gates are architectural). A single Decision entry ratifies the round-2 template.

## F3 — `## signal contract → Emits` section omitted from 13 sprints.

Sprints that omit the section entirely rather than declare an empty contract: 217, 218, 219, 220, 221, 222, 223, 223a, 223b, 223c, 223d, 223e, 223f.

AGENTS.md § The dual contract: "every tag declared in `## signal contract → Emits` must fire during the sprint, either at runtime … or narrated in your Signal Report's `signal_trace` section." The contract is unconditional. A CLI verb sprint that emits no runtime tags has an empty Emits list; the disciplined shape is `Emits: (none — CLI wiring, no runtime emit sites; behavior verified through observation contract)`, not deletion of the section. Deletion reads as "this sprint has no signal discipline"; empty-with-justification reads as "this sprint's signal discipline is zero emits, verified downstream."

The four 217-series cards that did include Emits (217a, 217c, 217d, 217e) show the shape holds when the sprint modifies a topology or the kernel. The break is exactly at the CLI/manifest boundary — where the sprint touches only client-side code and thinks the discipline does not apply. The 141-test green wall (see head of this doc) confirms the code works. That is not the review question. The review question is whether the sprint cards can be read six months from now and re-derived; without an empty-contract statement, a future reader cannot tell "no emits declared" apart from "author forgot to declare."

**Fix path.** Add one line to each of the thirteen cards under a `## signal contract` heading: `Emits: (none — CLI-only / manifest-only, no runtime emit sites in this diff).` Zero code change. Rule 12 preserves the original card contents; the edit is additive.

## F4 — `pass_kind: docs` on sprint 231 despite an observation contract and runtime-loaded artifacts.

Sprint 231 (default bundles shipped) is labeled `pass_kind: docs`. Its artifacts are five bundle directories consumed at runtime by `bundles.py::load_bundle`, `resolve_extends`, `assemble_seed` (sprints 229-230). A sprint whose output is loaded by the runtime is not a docs sprint. It is `functional` — or `architecture` if the bundle format itself is being established. The card declares an observation contract (obs=1), which is right — but `docs` per the template is for documentation prose. Mis-classified.

**Fix path.** Reclassify frontmatter from `pass_kind: docs` to `pass_kind: functional`. One-line edit.

## F5 — Vocabulary format bifurcation: kernel JSON vs. topology Markdown, ratified but under-enforced.

`process/signals/0.1.json`, `0.2.json`, `0.3.json` follow the kit's `templates/VOCABULARY.json` shape. `session-vocabulary.md`, `swebench-solver-vocabulary.md`, `applications-vocabulary.md` are Markdown vocab files, project-invented, ratified by the Architect Decision of 2026-08-25 as "distinct from kernel-JSON per repo convention for topology vocab."

The ratification is legitimate. What follows from it is where the discipline weakens. `lib/sdd.py`'s `SignalVocabulary.validate` enforces "schema at the speaker's mouth" (grammar/PRINCIPLES.md commitment 2) against a JSON schema. Markdown vocab has no such runtime enforcement. The eight `SessionStarted / UserMessage / ModelReply / Park / SessionEnded / SessionEndRequested / TranscriptCompacted / SessionWarning` Structs are typed at construction by msgspec, which catches missing/wrong-typed fields at the speaker's mouth — partial coverage. What msgspec cannot check: the *kind name string* itself. If a producer emitted `"SessionEndeed"` (typo), msgspec would accept the Struct instance; the vocabulary would receive no signal on the drift.

grep confirms 28 raw string literals of the eight session-vocab kinds across the session topology's own code. Each is a call-site that must match the Struct name. A rename of `Park` to `Parked` (for instance) would require finding every one. `signals/0.3.json` has this problem for kernel kinds too, but `constants.py` closes it there — every lifecycle kind is a named constant, and `is_reserved(kind)` gives one call site. The session vocabulary has no analogous `session_constants.py`.

**Fix path.** Add `src/substrate/topologies/session/vocabulary.py` (or reuse `constants.py`'s pattern in a new namespace) with eight `SESSION_STARTED = "SessionStarted"` constants; grep-replace the 28 string literals across `src/substrate/topologies/session/`. That closes the "typo drifts silently" class. Alternatively — and this is the deeper move — write the topology-vocab-to-JSON converter Piece 0's rationale doc promised (session-vocabulary.md § "the JSON convert-to-parity path is deferred"): make the Markdown the authoring surface, the JSON the runtime-enforceable shape.

## F6 — cli.py at 1,750 lines and delegate.py at 663 lines cross the concern threshold.

The sprint-sweet-spot rule (hard rule 6, ≤2 files / one concept) is a per-sprint bound, not a per-module one. Each individual sprint 218-222 respected the rule. The aggregate did not. cli.py now hosts: `chat` verb (218), REPL + SSE (219), SIGINT/SIGHUP/SUBSTRATE_SESSION (220), slash router (221), session/bundle/builder subverbs (222), plus a resume verb, plus `_daemon.py` client (module-level). That is five to seven concerns in one file.

The piece-C review already flagged delegate.py's growth (finding 11 in the piece-C fold: "delegate.py at 592 lines — hygiene split into `delegate/dispatch.py` + `delegate/context.py` + `delegate/model.py` when the seam settles"). It is now 663 lines. The deferral note said "when the seam settles"; the seam has settled — piece C closed; piece B closed; piece D and E have not further modified it. The natural moment to split is now, before piece G's UI work touches it and roots the current shape.

`WORKING_AGREEMENT.md ## Canonical home registry — daily driver` names `cli.py` as the canonical home for piece D. Splitting cli.py into `cli/` (a package with `chat.py`, `repl.py`, `slash.py`, `subverbs.py`, `main.py`) does not remove the canonical home; the package becomes it, and the registry entry updates to point at the package. Every existing import continues to work through `cli/__init__.py` re-exports.

**Fix path.** One `hygiene-split` sprint per module (two total). Each is a chain-of-behavior-preserving sprints under TECHNIQUE #43. Contract: dual contract unchanged before and after; every existing test still passes. Sprint sweet spot is honored because each split touches one module.

## F7 — Stray retyped lifecycle literal at `cli.py:1024`.

Full-tree grep for `"substrate\.(RunStarted|RunFinalised|...)"` across `src/` returned exactly one hit outside `constants.py`:

```
src/substrate/cli.py:1024:  if str(env.get("kind", "")) == "substrate.RunFinalised":
```

`constants.py` exports `RUN_FINALISED = "substrate.RunFinalised"`. This one line is the exact class the constants extraction was meant to close. `tests/` has 277 retyped literals — that is deliberate (tests pin wire shape), and I do not read it as drift. The `src/` stray is drift.

**Fix path.** Two lines: `from substrate.constants import RUN_FINALISED` at the top of cli.py, then `if str(env.get("kind", "")) == RUN_FINALISED:` at 1024. Zero behavior change. Adds a regression grep to CI that any future stray fails.

## F8 — Compaction-driven drift acknowledged in the record, worth carrying forward.

The BLACKBOARD's "DAILY-DRIVER ARC piece B partial" entry opens with an unusually candid warning: "this agent compacted multiple times during the piece-B arc. The compactions burned context that had been spent reading the full sdd-kit-2 (31 files, read TWICE) plus diffing all 26 modified substrate files. After compaction the agent re-diffed and re-logged files whose contents were already known from the continuation summary, wasting further context and drawing an explicit correction from the Architect ('never do that again'). Downstream work in this session should be reviewed with extra scrutiny — compaction-driven drift is invisible to the agent that drifted."

That warning is written *inside* the audit trail, which is the discipline working. KIT_DIARY findings 64-67 (2026-08-28) then catch the same window's specific drifts: inferring endpoint scope from a parenthetical, marking things "still open" that were closed by another spec section, prescribing endpoint work before writing sprint cards. Each finding is closed with a class and a doctrine.

The BLACKBOARD `## Surfaced for review` head entry 2026-08-28 declares "PIECE B CLOSED, red-team-corrected" and enumerates the corrections. That is the right closure shape. What is *not* on file is a sprint card retro-authoring the red-team pass itself — the pass produced substantive corrections (the "five missing endpoints" claim being wrong, the "still open" list resolving to already-closed items) and folded them into the closure summary. Per rule 12 the correction thread should be a dated file, not just an entry.

**Fix path.** Take REVIEW-2026-08-26-piece-b-fold-and-215-216-red-team.md and (if not already) close it with a dated closure doc — REVIEW-2026-08-28-piece-b-red-team-close.md — naming the four KIT_DIARY findings and the corrected scope. The BLACKBOARD entry already exists; the review doc is what future readers will find first when searching by date.

## F9 — Halt-and-articulate held cleanly on sprint 215b; the resolution added a kernel primitive.

Positive finding, worth naming so it does not get lost. Sprint 215b (POST /interrupt) halted with `substrate_primitive_missing` because the shape needed a per-producer in-loop cancel the kernel did not publish. The halt entry in the BLACKBOARD names the two candidate primitives (`Runtime.cancel_producer(instance)` vs a producer-scoped external-event channel), the failure mode of the wrong pattern (kill-and-seal semantics from the delegate.py:113 outer-task cancel would tear the writer loop before park-on-interrupt fires), and pivots to the next dispatchable slice (215c) rather than papering over.

Sprint 217c then lands the kernel primitive — `Runtime.cancel_producer(instance, cause=, caller=)` — with the v0.3 vocabulary bump adding two optional payload fields (`cause`, `caller`) on `substrate.ProducerCancelled`. `signals/0.3.json` + `0.3-rationale.md` land alongside; `signals/0.2.json` stays on disk (rule 12). Additive, backwards-compatible, ratified, tested.

The core substrate primitives are described in the review request as "immutable." The 217c change is a genuine primitive addition (new method on Runtime + two new optional payload fields). Whether "immutable" prohibits additive kernel changes is an Architect ruling. Reading the discipline as it stands: v0.3 went through the vocabulary evolution pipeline correctly (`PAYLOAD_FIELD_PROPOSED`, ratified, rationale doc), and the new primitive is additive rather than a semantic change to an existing one. This is what the eight evolution kinds are for. Flag for Architect awareness; do not fold as a fix.

## F10 — Observation-contract discipline held; test evidence is real, not synthetic.

Every sprint in the un-reviewed set except the seven 224-series subs with invented `pass_kind` values declares an observation contract. Ran the un-reviewed sprints' pinning tests: 141 passed, 1 skipped in 7.62 s. The tests are not `assert True`; sample check on `test_session_topology_end_to_end.py` fires a real `ci_session_topology` and asserts against real record envelopes, matching the observation contract in sprint 210's card. The pair-coding composite and toolkit tests hit real registries and real HTTP handlers where they need to; the CLI tests hit real subprocess launches.

The one skipped test is a real-model timeout guard, not a signal contract gap.

Not a finding. Named because the alternative — declared-but-vacuous observation contracts — is the exact soundfield round-23 failure mode the kit exists to prevent, and it is not the failure mode here.

## F11 — Terminology and prose against field consensus.

Nothing flagged. The prose in the un-reviewed sprint cards uses standard terms correctly: `SSE` (Server-Sent Events, the W3C spec), `SIGTERM`/`SIGHUP` (POSIX signals), `msgspec.to_builtins` (the actual msgspec API), `fcntl.flock` (the actual POSIX call), `ThreadingHTTPServer` (the stdlib class), `asyncio.wait_for` (the actual asyncio API), `deferred/RATIFIED` in the vocabulary proposals (the eight-kind taxonomy's own words). One own-coinage — "seed_alone_exceeds" for the context-length guard — is a project-specific concept that reads clearly; the kit's principle "leave own-coinage alone" applies.

The one prose complaint worth raising is unrelated to terminology: several BLACKBOARD entries push past 4 KB of prose per bullet. The rate at which piece-B and piece-C entries grow suggests the compaction TECHNIQUE #20 (Sprint tail rollups) is not being applied, which the 2026-07-22 Housekeeping ruling explicitly declined ("NO blackboard compaction — the long-form entries stay"). That is a ratified choice, not a finding; naming it here so a future review knows the long-entry shape is deliberate.

## F12 — Code organization and canonical home.

The 2026-08-25 Architect Decision ratifies the canonical-home registry: 18 rows mirroring TECH-SPEC-2026-08-25-round6 §1.6.1. Un-reviewed sprints add roughly 25 more rows per the BLACKBOARD's "DAILY-DRIVER ARC pieces 0 + A + C" entry. Each new module lands where the registry says. The one drift is F6 — cli.py and delegate.py hosting more than one concept per module — and that is a growth-past-the-boundary issue, not a mis-location.

The applications directory (`src/substrate/topologies/applications/`) is a clean piece-E landing: registry.py, four `.manifest.toml` files, four `.py` topology modules, four `.bundle/` directories, plus the pair_coding composite. The bundles module (`src/substrate/bundles.py`) is one file at appropriate size. The session topology (`src/substrate/topologies/session/`) is a proper package with `__init__.py`, `views.py`, `transcript.py`, `ci.py`, `roles.py`, `bundle/`, `prompts/`, `records/`. Every location matches its registry entry.

`_daemon.py` (the CLI's daemon client, 279 lines) is CLI-internal and correctly named with the leading underscore per F-API-6 posture. It does not import from `substrate-ui/`; the boundary holds by import even though prose references cross freely (11 mentions of "substrate-ui" in `src/substrate/`, all in comments, docstrings, or error messages naming the daemon's location — none as code imports).

Not a further finding beyond F6.

## F13 — Immutable primitives check.

Runtime, Producer, Topology, RunState, LiveRecord — the load-bearing kernel classes — were not modified in the un-reviewed sprints except for the additive `cancel_producer` primitive (F9) and the internal `kind_by_instance` state field that supports it. Both changes are additive; both are covered by tests (`tests/test_cancel_producer.py`, 9 cases per the BLACKBOARD entry). The twelve reserved `substrate.*` lifecycle kinds are unchanged; the new `cause` and `caller` fields on `ProducerCancelled` are optional additions to an existing kind's payload, per the additive-payload rules of the vocabulary evolution taxonomy.

Not a finding. Named because the review request called it out as a first-order concern.

## F14 — Instrumentation reality.

Ran, not trusted. 141/1 across the un-reviewed sprints' pinning tests. Full-suite regression is still running at review close (background task `bzbssqfnk`, no interim output). Prior BLACKBOARD entries name "951 passed / 5 skipped / 1 failed" and "930 passed / 5 skipped / 0 failed" across the piece-B and piece-C windows respectively; the one failure both times is `tests/test_realmodel_demos.py::test_instrument_ablation_delta`, a real-model timeout that predates this arc.

The Rubber Duck Pass on sprint 210 (piece-A observation contract) is on record in `test_session_topology_end_to_end.py`: six in-process tests hitting a real `ci_session_topology`, payload-kind sequence, per-turn payload predicates, lifecycle-event coverage across all four producers, Level-3(a) byte-identical replay, `.resume()` chain proving `[pause-await-input, pause-await-input, finalise-run]`. Not synthetic; the fixture `tests/fixtures/three_turns.json` is real.

Not a finding.

---

## What is on track

- Piece 0 (sprints 202-204), Piece A (205-210), Piece C (211-213b), Piece B (214a-217e) all closed with review folds. The daily-driver arc's foundation is in place.
- Piece D (218-222) CLI + REPL + slashes shipped and tested. `substrate chat` and `substrate resume` verbs live. Daemon auto-launch, socket/TCP fallback, SIGINT/SIGHUP handling, `SUBSTRATE_SESSION` env, nine slashes per TECH-SPEC §6, all covered by real-subprocess tests.
- Piece E (223 + 223a-f + 224 + 224a-h + 225a-d) — application registry, four manifests + composite factory, plus a substantial correctness/cleanup sub-arc (224a-h). Registry loads manifests at boot; the four shipped apps (code_review, best_of_n_verified, research_sweep, daily) register cleanly.
- Piece F (226-228) — substrate toolkit tool wrappers (`run_topology`, `inspect_record`, four `list_*` factories) ship with HMAC-signed cursor pagination and progressive-disclosure budgets per TECH-SPEC.
- Piece H (229-232 + 232b) — bundle loader, slot binding, five default bundles, Mad Lib wizard with six templates. C3 linearisation, cycle detection with `BundleCycleError`, depth cap 8, `SlotUnfilledError` on missing required.
- Piece G (substrate-ui two-view) — not started per plan; belongs to substrate-ui/sprints/, out of this repo's roadmap and out of this review's scope.
- Kernel primitives extended additively (F9); vocabulary evolved through the eight-kind taxonomy (v0.2 → v0.3 with rationale); constants extraction closed 22 files' worth of retyped literals against `constants.py` (F7 is one stray).
- Halt-and-articulate held under real pressure on sprint 215b (F9).
- KIT_DIARY findings 53-67 name real drift and close it with doctrine, not just "will do better next time." The compaction warning in the BLACKBOARD is unusually honest (F8).

## What each finding costs to close

| # | Finding | Fix cost | Blocker on downstream? |
|---|---|---|---|
| F1 | Sprint-id collision 224b | One card rename + BLACKBOARD/KIT_DIARY grep-fix. ~30 min. | No, but Piece G work referring to "224b" will be ambiguous. |
| F2 | Invented `pass_kind` values | Either propose SPRINT_CARD-round2.md (kit change) or reclassify seven cards. ~1 hour either way. | No. |
| F3 | Missing `Emits` sections in 13 cards | One-line edit per card. ~20 min. | No. |
| F4 | Sprint 231 mis-classified | One-line frontmatter fix. ~1 min. | No. |
| F5 | Topology vocab enforcement gap | Add `session/vocabulary.py` constants + grep-replace 28 literals. ~1 hour. | No; long-run drift risk. |
| F6 | cli.py + delegate.py oversized | Two hygiene-split sprints per TECHNIQUE #43. Half a day. | Blocks clean Piece G rooting on delegate.py. |
| F7 | Stray literal in cli.py:1024 | Two-line import + rename. ~2 min. | No. |
| F8 | Red-team pass not on file as a dated review | Author REVIEW-2026-08-28-piece-b-red-team-close.md from BLACKBOARD material. ~30 min. | No. |

F9, F10, F11, F12, F13, F14 are not findings requiring action; each is on record as a positive check.

## Overall verdict

The un-reviewed sprints ship real code that passes real tests against real primitives. The drift is on the methodology's surface (F1, F2, F3, F4, F5) more than on the runtime's behavior. F6 is the one place where the aggregate has crossed a threshold that a per-sprint discipline does not catch. F7 is a rounding error. F8 is a hygiene close, not a defect.

Piece B closes cleanly under the red-team correction. Piece D through H land per the roadmap. Kernel primitives extended additively through the ratified vocabulary pipeline. The core substrate is intact; the audit trail is intact but for the F1 collision. The methodology's own contracts (sprint-frontmatter enum, `## signal contract` requirement) are the surface where discipline slipped during a fast-moving arc, which is exactly where the review is meant to catch it.

Ratify or reject F1-F5 as scope for a hygiene sprint; F6 as scope for two hygiene-split sprints; F7 folded into either. F8 authored as one closure doc.

---

*REVIEW-2026-08-28-un-reviewed-sprints-217-through-232b.md. Author: Claude session 2026-08-28. Read against sdd-kit-2 (foundations 01-04, PRINCIPLES, BOOTSTRAP, AGENTS, TECHNIQUES, ADDENDUMS, SPRINT_CARD, lib/sdd.py). Ground truth checks: sprint-id uniqueness scan; pass_kind enum scan; retyped-literal grep; targeted pytest 141/1 green. Fourteen findings; eight actionable, six positive checks. Adversarial on SDD discipline; substrate primitives verified additive-only.*
