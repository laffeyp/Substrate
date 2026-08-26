# session — locked topology vocabulary

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

*Additions follow the swebench-solver-vocabulary pattern: bump the header status to `RATIFIED — v0.X`, add a new lettered section at the bottom, byte-preserve §§ A-H. Never re-flow.*
