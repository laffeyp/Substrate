# session — locked topology vocabulary

**Status: RATIFIED — v0.2.1 (2026-09-02).** Sprint 068 adds `SessionWarning.kind` value `"fragment_source_failed"` and optional payload field `source_name: str?`. Additive per the § H convention; §§ A-I byte-preserved from v0.2. Surfaces fragment-source Producer failures as operator-visible warnings on the record.

**Status: RATIFIED — v0.2 (2026-09-01).** Sprint 058 adds two application event kinds — `PromptFragment` and `PromptComposed` — plus the `PromptSource` enum for `PromptFragment.source`. Additive per the § H convention: §§ A-H byte-preserved from v0.1; the new material lives in § I. Ratifies the SDD entry gate for the prompt-composition arc (sprints 058-066) that rebuilds prompt composition as Producer emissions instead of inline string concatenation.

**Status: RATIFIED — v0.1 (2026-08-25).** Architect ratified in `substrate/process/BLACKBOARD.md ## Decisions` on 2026-08-25 (see the entry naming this doc + sprint 202 close). Locks the eight application event kinds the daily-driver session topology emits per `TECH-SPEC-2026-08-25-round6.md` §3 + §3a. Sprint 203 (substrate-ui side v0.6 lock + pairing) dispatches on this ratification; sprint 204 (canonical-home registry + piece-0 close) follows.

Designed BEFORE code (Sprint-0 discipline per sdd-kit-2 hard rule 12). The topology records are frozen msgspec Structs, topology-local, registered in `substrate/process/WORKING_AGREEMENT.md`; this doc locks their fields, the §G dual-contract audit against substrate-ui grader tags (sprint 203), and the cadence rules for ambient kinds. Strict validator-extras (project posture).

Design: `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §3 (topology + events), §3a (transcript renderer + cadence), §1.6.5 (seed assembler). Product-spec derivation: `PRODUCT-SPEC-2026-08-17-round12.md` §3, §4, §4a.

Home: `substrate/src/substrate/topologies/session/` (piece A of the daily driver, sprint 205 authors the Structs; this doc locks their contract).

## A. Case convention

Two shapes ride the record; two casing rules.

- **PascalCase** — msgspec Structs the topology declares via `producer_kind(schemas=[...])` at `substrate/src/substrate/kernel/topology.py:137`. Matches the kernel's own reserved lifecycle set (`substrate.RunStarted`, `substrate.TriggerFired`, `substrate.ProducerCompleted`, …). All eight kinds in v0.1 (§§ B-E) use PascalCase.
- **SCREAMING_SNAKE** — reserved for future wire events with no dedicated Struct that the kernel itself might add. Application code (the daemon at `substrate-ui/server.py`) cannot emit through `_Lifecycle` per F-API-6 (`import-linter` at `cli.py:2-8`); every application signal is a Producer emission with a Struct schema. v0.1 has no wire events; the convention is documented for future kernel additions only.

`SessionCompositeSpec` (mentioned in earlier draft rounds) is a daemon-internal dataclass returned by `pair_coding_application`; it will live at `substrate/src/substrate/topologies/applications/pair_coding_composite.py` (Sprint 225 authors it — the file does not exist yet), never lands on a substrate record, and is deliberately not in this lock.

## B. Session lifecycle records

Three kinds bracket every session record: `SessionStarted` opens at seq 1; `SessionEnded` closes the record; `SessionEndRequested` is an external injection the daemon uses on `POST /api/session/<id>/end`.

### SessionStarted

| Field | Type | Meaning |
|---|---|---|
| `session_id` | `str` | ULID prefixed `s_`; matches the manifest at `~/.substrate/sessions/<session_id>/`. |
| `seed` | `str` | Assembled per §1.6.5 (role prompt + bundle methodology + project context + task + baseline). Verbatim — every future turn reads this from the record. |
| `driver_model` | `str` | The driver's name (e.g. `"kimi-k2.6:cloud"`, `"claude"`, `"deterministic"`). |
| `driver_context_tokens` | `int` | Driver's declared context window (§3a lookup). Drives the rolling-window K. |
| `tool_suite` | `tuple[str, ...]` | Tool names the topology composed at open — deterministic order. |
| `workspace_path` | `str` | Absolute path where `edit_file`/`write_file`/`bash` operate. |
| `workspace_shape` | `str` | `"flat" \| "worktree" \| "isolate"` per §9c product spec Mode 1/2/3. |
| `bundle` | `str \| null` | Bundle name if any. |
| `baseline` | `dict[str, Any]` | The full auto-baseline dict (repo_root, branch, readme_head, git_diff, commit, cwd/user/hostname). |
| `parent_session_id` | `str \| null` | Non-null when the session was opened as a standing sub-agent from a delegate call. |
| `parent_seq_at_call` | `int \| null` | Seq on the parent's record at the moment of the delegate call. |

Stratum: **event**.

### SessionEnded

| Field | Type | Meaning |
|---|---|---|
| `reason` | `str` | One of `"user_exit"` (model saw `/exit`), `"user_end"` (daemon POST /end), `"timeout"` (200-turn cap), `"daemon_shutdown"` (SIGTERM). Four values, four distinct paths. |
| `total_turns` | `int` | Count of UserMessage kinds on the record at close. |

Stratum: **event**. Terminal for the record — followed only by `substrate.RunFinalised`.

### SessionEndRequested

| Field | Type | Meaning |
|---|---|---|
| `reason` | `str` | `"user_end"` \| `"daemon_shutdown"`. The daemon injects this via `Runtime.resume` (external event, `runtime.py:409-450`); the `end-on-user-end` trigger fires `session_end` which emits `SessionEnded` with the same reason. |

Stratum: **event**. At most one per session. Never emitted by the topology itself; always daemon-injected.

## C. Turn records

Three kinds compose each user turn: `UserMessage` opens; zero or more `ModelReply` + `ToolCall`/`ToolResult` pairs run between; `Park` closes the turn and pauses the topology awaiting the next `UserMessage`.

### UserMessage

| Field | Type | Meaning |
|---|---|---|
| `text` | `str` | What the user typed (or what the daemon injected). |
| `turn_index` | `int` | 0-based; monotonically increasing across the session. |
| `assembled_prompt` | `str` | The exact bytes the daemon fed to the model: `per_turn` prefix (from §7b bundle) + `text`. Recorded so debug is deterministic. |
| `slash_source` | `str \| null` | Provenance: `"chat"` (typed) \| `"/context"` (slice attached) \| `"delegate"` \| `"resume"`. |

Stratum: **event**. `turn_index` values are contiguous and start at 0.

### ModelReply

| Field | Type | Meaning |
|---|---|---|
| `text` | `str` | Model reply text. |
| `model_usage` | `dict[str, Any]` | From `substrate.adapters.models.ModelUsage` — prompt_tokens, completion_tokens, wall_ms, model, estimated. |
| `turn_index` | `int` | Matches the enclosing UserMessage's turn_index. |

Stratum: **event**. Zero or more per turn (tool-loop may fire model multiple times).

### Park

| Field | Type | Meaning |
|---|---|---|
| `awaiting` | `str` | `"UserMessage"` in v0.1. Leaves room for other await kinds. |
| `turn_index` | `int` | The turn that just parked. |
| `reason` | `str` | `"final_answer"` (model produced FinalAnswer) \| `"model_error"` (model producer failed) \| `"interrupt"` (POST /interrupt cancelled the model producer). |

Stratum: **event**. Exactly one after each `FinalAnswer`, `substrate.ProducerFailed{producer.kind:"model"}`, or `substrate.ProducerCancelled{producer.kind:"model"}`.

## D. Transcript compaction (ambient)

### TranscriptCompacted

| Field | Type | Meaning |
|---|---|---|
| `strategy` | `str` | `"rolling_window"` in v0.1. `"summary_tail"` in v1.5. `"semantic"` deferred. |
| `dropped_seq_range` | `tuple[int, int]` | Inclusive seq range of the events dropped from the threaded prompt. Non-empty when the event fires. |
| `kept_seq_start` | `int` | First seq threaded into the current model prompt. Always strictly greater than `dropped_seq_range[1]`. |
| `reason` | `str` | `"driver_window_exceeded"` (K forced the drop) \| `"K_bound"` (K < len(turns) even with headroom) \| `"bundle_changed"` (mid-session bundle PATCH re-assembled the seed). |
| `tokens_before` | `int` | Estimated token count of the pre-compaction prompt (word-count proxy). |
| `tokens_after` | `int` | Estimated token count of the post-compaction prompt. `tokens_after ≤ tokens_before`. |

Stratum: **ambient**.

**Cadence.** At most one per `model` producer firing. Never fires when `turns_dropped == 0` — the model producer yields it only when the renderer's `RenderedTranscript.compaction_events` is non-empty. Grader invariant: for every `TranscriptCompacted{seq=S}`, no other `TranscriptCompacted` appears in `[S-1, S]`.

## E. Session-warning event

### E.1 SessionWarning

A frozen msgspec Struct emitted by a small `session_warning` producer inside `session_topology`. The producer fires once at session-open when a condition trips (initial: `seed_alone_exceeds`) and once per subsequent condition (e.g. `bundle_changed` on a PATCH that swaps the bundle). Reaching into the kernel's private `_Lifecycle` from daemon code would break the F-API-6 discipline (`import-linter` at `cli.py:2-8`); a Producer keeps the emission inside the topology where every other application signal lives.

`session_warning` producer schema: `[SessionWarning]`. Trigger: `warn-on-condition` — subscribes to a small daemon-injected `SessionWarningRequested` kind (parallel to `SessionEndRequested`); daemon POSTs it via `Runtime.resume` at session-open when a condition trips, and again mid-session on `PATCH /api/session/<id> {bundle: <new>}` that changes the name.

Renamed from `SESSION_WARNING` (SCREAMING_SNAKE convention from an earlier draft where the record wrote it directly). PascalCase now that it is a Struct.

| Field | Type | Meaning |
|---|---|---|
| `kind` | `str` | The condition. v0.1 values: `"seed_alone_exceeds"`, `"bundle_changed"`. |
| `seed_tokens` | `int?` | Present when `kind == "seed_alone_exceeds"`. Estimated seed token count. |
| `driver_context_tokens` | `int?` | Present when `kind == "seed_alone_exceeds"`. The threshold the seed exceeded. |
| `old_bundle` | `str?` | Present when `kind == "bundle_changed"`. |
| `new_bundle` | `str?` | Present when `kind == "bundle_changed"`. |

Stratum: **ambient**. Every `SessionWarning` is a Producer emission with a subject producer ref on the envelope (`session_warning`), not a bare `_Lifecycle` frame with `producer=null`.

**Cadence.** At most one per `(session_id, kind)` pair. A second `SessionWarning{kind:"seed_alone_exceeds"}` on the same session_id is a grader violation. `bundle_changed` fires only on a PATCH that actually swaps the bundle name — a same-name PATCH emits nothing.

**§A convention update.** Section §A named `SESSION_WARNING` as the one wire event in v0.1. That was wrong per F-API-6: daemon code cannot emit into `_Lifecycle`. v0.1 has zero wire events with no Struct; every kind is PascalCase and Producer-emitted. §A's convention rule stands (SCREAMING_SNAKE reserved for genuine daemon-side wire events), but v0.1 uses none.

## F. Invariants (the `checkSessionBookends` grader)

The substrate-ui grader `checkSessionBookends` at v0.6 (sprint 203) enforces these against the record. Every session's record satisfies each rule.

1. Exactly one `SessionStarted` per record, at seq 1 (seq 0 is `substrate.RunStarted`).
2. Exactly one `SessionEnded` per record OR the record's status is `paused` at grader read time. A finalised record with no `SessionEnded` is a violation.
3. No repeated `substrate.RunStarted` on one `session_id` across resumes. `Runtime.resume` restores the run_id from the existing manifest per `runtime.py:409-450`; a second RunStarted would signal a resume bug.
4. Every `UserMessage{turn_index=N}` at seq S is followed at a seq greater than S by at least one of `FinalAnswer`, `substrate.ProducerFailed{producer.kind:"model"}`, or `substrate.ProducerCancelled{producer.kind:"model"}` before the next `UserMessage` OR the record's terminal event. Grader-checkable from seq alone; `t` is supplementary per substrate's own convention and not used here.
5. Every `Park` is preceded — at a strictly lower seq within the same `turn_index` — by exactly one terminal matching its `reason`. `Park{reason:"final_answer"}` by exactly one `FinalAnswer`; `Park{reason:"model_error"}` by exactly one `substrate.ProducerFailed{producer.kind:"model"}`; `Park{reason:"interrupt"}` by exactly one `substrate.ProducerCancelled{producer.kind:"model"}`. Matches §C's three-terminal contract.
6. `TranscriptCompacted.dropped_seq_range` is a contiguous seq range strictly below `kept_seq_start`.
7. `SessionWarning` fires at most once per `(session_id, kind)` pair.
8. `turn_index` values on UserMessage kinds are contiguous starting at 0.

## G. Dual-contract audit (paired to substrate-ui v0.6)

Per BOOTSTRAP.md § "Dual-contract audit," every behavior tag on the substrate side pairs with a view/structural target on the substrate-ui grader side. Sprint 203 (`substrate-ui/signals/versions/0.6.json`) authors the paired UI tags. Bidirectional table:

| Substrate kind | Substrate-ui pairing | Pairing shape |
|---|---|---|
| `SessionStarted` | `DRIVER_SESSION_STARTED` | named tag |
| `UserMessage` | `USER_MESSAGE_INJECTED` | named tag |
| `ModelReply` | `PANE_SCROLLED{model_reply_ref}` | structural payload on a v0.6 tag (`PANE_SCROLLED` is new in v0.6; `model_reply_ref` in `optional_payload` carries the substrate seq of the reply that caused the scroll) |
| `Park` | `PARK_LANDED` | named tag |
| `SessionEnded` | `DRIVER_SESSION_ENDED` | named tag (v0.5's `SESSION_ENDED` is browser page unload — different object; the `DRIVER_` prefix keeps v0.6 a strict superset of v0.5 per Architect ratification 2026-08-25) |
| `SessionEndRequested` | `DRIVER_SESSION_END_REQUEST_ISSUED` | named tag (ratified 2026-08-25) |
| `TranscriptCompacted` | `TRANSCRIPT_COMPACTED_LANDED` | named tag |
| `SessionWarning` | `DRIVER_SESSION_WARNING_EMITTED` | named tag |

Every row's UI target must exist in `substrate-ui/signals/versions/0.6.json` at sprint 203's close. A missing pairing is a `vocabulary_change_required` halt on piece 0.

## H. Ratification signature

- **v0.1** — Sprint 202 close, 2026-08-25. Locks the eight session-topology kinds ahead of piece A (sprint 205 authors the Structs). Architect ratifies in `substrate/process/BLACKBOARD.md ## Decisions` — the Decision entry unblocks piece A dispatch per sprint 204.
- **v0.2** — Sprint 058 close, 2026-09-01. Adds two kinds (`PromptFragment`, `PromptComposed`) and the seven-value `PromptSource` enum. Additive; §§ A-H byte-preserved from v0.1. Structs live at `substrate/src/substrate/topologies/session/__init__.py`; kind-name constants at `substrate/src/substrate/topologies/session/vocabulary.py`.

*Additions follow the swebench-solver-vocabulary pattern: bump the header status to `RATIFIED — v0.X`, add a new lettered section at the bottom, byte-preserve prior sections. Never re-flow.*

## I. v0.2 — prompt composition (2026-09-01, sprint 058)

Two Structs and one enum name the fragment / composer shape the prompt-composition arc (sprints 058-066) rebuilds around. Motivation: every existing composition site (`session/__init__.py::_model_factory` at ~L301/L334/L349, `session/transcript.py::_render`, `tool_loop/delegate.py::_prefix_context_slice`) builds prompt text via inline f-string or `"\n\n".join(parts)`. The composed prompt reaches the model but leaves zero record trace. Replay cannot reconstruct which fragment came from where; `record diff` cannot show a fragment-level change; a View cannot count fragments per session or measure tokens per source. Two typed events fix that at the primitive layer, without adding kernel vocabulary.

### PromptFragment

Emitted by each fragment-source Producer (sprints 060-064). One per source per relevant firing: session-open sources fire once at `substrate.RunStarted`; turn-scoped sources fire once per relevant turn.

| Field | Type | Meaning |
|---|---|---|
| `source` | `str` | One of the seven `PromptSource` values below. Identifies which producer emitted this fragment. |
| `text` | `str` | The fragment contents, as the model will read them. Verbatim. |
| `precedence` | `int` | Composer ordering key. Lower fires earlier in the composed text. Reserved band: `role=0`, `bundle_personality=3`, `bundle_methodology=5-9`, `per_turn=10`, `wrap_up=15`, `tools_suite=20`, `parent_context=30`, `user_message=100`. |
| `provenance` | `dict[str, Any]` | Source-specific audit trail. `role`: `{"role_name": <str>, "resolved_from": <path>}`. `bundle_*`: `{"bundle_name": <str>, "extends_chain": [<names>]}` or `{"chain_position": <int>}`. `parent_context`: `{"parent_record_root": <str>, "parent_seq_range": [lo, hi], "kinds": [...]}`. `per_turn`, `tools_suite`, `user_message`: `{}` or small source-specific dicts. Not typed further at this layer; the source's own tests pin its provenance shape. |

Stratum: **event**. Multiple per session (one per source per firing); zero when a source's input is empty (empty per_turn, no bundle, no parent context).

### PromptComposed

Emitted by the composer Producer (sprint 059) exactly once per model firing. Carries the assembled prompt plus the seq references of every fragment that composed it, so a reader can trace back through the record without re-executing the composition.

| Field | Type | Meaning |
|---|---|---|
| `text` | `str` | The assembled prompt the model receives. Bytes-identical to what the driver reads. |
| `fragment_seqs` | `tuple[int, ...]` | Seq of every `PromptFragment` that composed into `text`, in composition order (lowest precedence first). Empty tuple when the cohort was empty (`text == ""`). |
| `total_tokens` | `int` | Estimated token count of the composed text (chars/4 heuristic per `transcript.py`). |
| `strategy` | `str` | `"precedence_join"` in v0.2. Leaves room for a v0.3 template strategy. |

Stratum: **event**. Exactly one per model firing anchor (per turn in the common case; the wrap-up path may fire the composer a second time on the same turn — sprint 064 pins the choice).

### PromptSource enum

Seven string values name the initial fragment sources. Extending the enum bumps the session vocabulary version (v0.2 → v0.2.1 → v0.3 as sources land in sprints 060-064). Kind-name constants at `session/vocabulary.py`.

| Value | Meaning |
|---|---|
| `per_turn` | Manifest `per_turn` string, session-scoped, precedence 10. Sprint 060 wires. |
| `role` | Four-layer role prompt (`session/roles.py::resolve_role_prompt`), session-scoped, precedence 0. Sprint 061 wires. |
| `bundle_methodology` | Bundle methodology slot text (walking the extends chain), session-scoped, precedence 5.0-5.9. Sprint 062 wires. |
| `bundle_personality` | Bundle personality slot (caller-wins across extends chain), session-scoped, precedence 3. Sprint 062 wires. |
| `parent_context` | Delegate context slice from parent record, session-scoped, precedence 30. Sprint 063 wires. |
| `tools_suite` | `suite_describe(tools)` output, session-scoped, precedence 20. Sprint 064 wires. |
| `user_message` | Current turn's UserMessage text, turn-scoped, precedence 100. Sprint 064 wires (uniform shape). |

### Cadence

`PromptFragment` fires at its source's own trigger anchor (`substrate.RunStarted` for session-scoped sources; `UserMessage` for turn-scoped sources). `PromptComposed` fires on the model producer's input anchor, after the current turn's fragment cohort has landed. Grader invariant: every `PromptComposed{seq=S}` at model firing M has `fragment_seqs` containing only fragments whose seq is strictly less than S; the composition is causal.

### Dual-contract audit (v0.6 substrate-ui pairing not yet authored)

The § G table (v0.1) pairs every substrate session kind with a substrate-ui grader tag. The v0.2 pair extends by two rows once sprint 059 lands a live emit site: `PromptFragment` pairs with a UI tag TBD when composer telemetry surfaces in the console; `PromptComposed` pairs with a UI tag TBD when the prompt inspector surfaces. Both are companion-sprint work on the substrate-ui side; not blocking for v0.2 ratification.

## J. v0.2.1 — fragment-source failure warning (2026-09-02, sprint 068)

Additive extension to `SessionWarning`. `kind` gains one value; an optional payload field lands. The pre-arc `SessionWarning` shape stays: existing consumers reading `kind`, `seed_tokens`, `driver_context_tokens` are unaffected.

### SessionWarning — v0.2.1 additions

`SessionWarning.kind` gains value `"fragment_source_failed"`. Fires when any producer whose kind is in `FRAGMENT_SOURCE_KINDS` emits `substrate.ProducerFailed`. The set is documented at `src/substrate/topologies/session/vocabulary.py::FRAGMENT_SOURCE_KINDS`: `per_turn_fragment`, `role_fragment`, `bundle_methodology_fragment`, `bundle_personality_fragment`, `parent_context_fragment`, `tools_suite_fragment`, `user_message_fragment`.

New optional payload field:

| Field | Type | Meaning |
|---|---|---|
| `source_name` | `str?` | Present when `kind == "fragment_source_failed"`. Names the failed producer's kind (e.g., `"role_fragment"`). Absent (null) for every other kind value. |

**Cadence.** At most once per `(session_id, source_name)` pair per session. A repeated failure on the same source (e.g., a bundle whose slot ambiguity trips on every turn) fires the SessionWarning ONCE, not per turn — the trigger uses PerEvent policy but the source_name-keyed dedup lives on the reader's side. The grader invariant carries over from § F #7 (v0.1's per-kind cadence).

**Composer / model behavior after a fragment-source failure.** The per-turn composer chain (`per_turn_fragment → user_message_fragment → composer`) subscribes to `{substrate.ProducerCompleted, substrate.ProducerFailed}` from sprint 068 onward. A failed link still advances the chain; the composer's cohort simply lacks the failed fragment. `PromptComposed.text` emits truncated. Model runs. Session runs to completion. The SessionWarning is the operator-visible signal that the composed prompt was degraded.

### Ratification signature

- **v0.2.1** — Sprint 068 close, 2026-09-02. Additive extension for fragment-source failure surfacing. § A-J byte-preserved from prior locks.
