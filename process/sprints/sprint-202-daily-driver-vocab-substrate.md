# Sprint 202 — daily-driver vocabulary lock (substrate side)

```yaml
---
id: 202
status: closed
phase: daily-driver-piece-0
pass_kind: architecture
---
```

## scope

Author `substrate/process/signals/session-vocabulary.md` — a topology-scoped vocabulary doc following the same shape as `swebench-solver-vocabulary.md` and `applications-vocabulary.md` on disk today. Locks eight new event kinds the daily-driver session topology emits: seven Structs (`SessionStarted`, `UserMessage`, `ModelReply`, `Park`, `SessionEnded`, `SessionEndRequested`, `TranscriptCompacted`) plus one wire event (`SessionWarning`), each with stratum, category, field table, and invariants per TECH-SPEC-2026-08-25-round6 §2.5 and §3.

**Correction (post-review 2026-08-25).** Round-6 tech spec §2.5 said `substrate/process/signals/0.6.json`. That path was wrong: the substrate signals folder holds the kernel vocab as versioned JSON (0.1.json, 0.2.json — reserved `substrate.*` lifecycle kinds) alongside per-topology Markdown vocab docs. The session topology adds no reserved kinds; its signals are application-level msgspec Structs declared via `producer_kind(schemas=[...])`. The lock belongs in a Markdown doc colocated with `swebench-solver-vocabulary.md`. Header carries `Status: RATIFIED — v0.1 (2026-08-25)`; future additions bump per hard rule 12 (byte-preserved earlier sections).

`SessionCompositeSpec` is not in the lock — it is a daemon-internal dataclass, never lands on a substrate record.

**Case convention.** msgspec Structs use PascalCase (matching kernel's `substrate.RunStarted`, `substrate.TriggerFired`). Wire events that carry no Struct — internal records the runtime emits directly via `_Lifecycle` — use SCREAMING_SNAKE (matching `substrate-ui` grader tags). `SessionWarning` is the one wire event; the seven Struct kinds are PascalCase. Documented at the top of the file. Author `substrate/process/signals/0.6-rationale.md` naming why each kind exists, which product-spec requirement it satisfies, and its dual-contract pairing target on the substrate-ui grader side (TECH-SPEC §13.5 table). File parses as msgspec-validatable JSON; `grep` for reserved-namespace collisions returns none; the rationale doc has one paragraph per kind.

## prerequisites

- Sprint 201 closed (2026-08-14; SWE-bench arc topology-attachment surface).
- Round-6 tech spec ratified in `## Decisions` (or explicit "dispatch on tech-spec-round-6" note).

## context_files

Read in full before authoring:

- `sdd-kit-2/AGENTS.md` — hard rules 2 (vocabulary is the contract), 12 (Sprint-0 vocabulary materialization).
- `sdd-kit-2/grammar/PRINCIPLES.md` — the eleven-layer stack, non-negotiable commitments.
- `sdd-kit-2/grammar/BOOTSTRAP.md` — Vocabulary Session procedure, strata, invariants, dual-contract audit.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` — §2.5 piece 0 deliverables; §3 event Structs; §3a cadence rules; §13.5 dual-contract pairing table.
- `current-design-direction/PRODUCT-SPEC-2026-08-17-round12.md` — §3, §4, §7b, §8 for the requirements the kinds satisfy.
- `substrate/process/signals/0.5.json` (previous locked version — for style + shape parity).
- `substrate/process/signals/0.5-rationale.md`.
- `substrate/process/BLACKBOARD.md` — `## Decisions` for project scope.
- `substrate/process/WORKING_AGREEMENT.md`.

## signal contract

### Emits

None. This sprint authors documentation + a locked JSON; the runtime does not emit anything new until piece A dispatches (205).

### Consumes

The read files above.

## artifact contract

### Files created or modified

- `substrate/process/signals/session-vocabulary.md` — new. Follows `swebench-solver-vocabulary.md` shape: header status line, home path in `src/substrate/topologies/session/`, per-kind field table, invariants block, dual-contract audit table (cross-references substrate-ui grader tags from sprint 203).

### Content assertions

- Header carries `Status: PROPOSED — v0.1 (2026-08-25)` and names `substrate/src/substrate/topologies/session/` as the home. Flips to `RATIFIED` on sprint 204's Architect Decision entry.
- One § per kind: heading is the kind name; body is a field table (name : type — meaning), a "stratum" line, a "cadence" line for ambient kinds, and an invariants list.
- Eight kinds present (all PascalCase Structs; no wire events in v0.1); none uses `substrate.*` reserved prefix.
- Dual-contract audit § pairs each behavior kind with its substrate-ui grader tag from sprint 203 or names a typed gap-proposal.
- §F grader invariants are seq-based, not wall-time-based (`t` is supplementary per substrate 0.1.json).
- §F #5 covers all three `Park.reason` values (final_answer, model_error, interrupt), matching §C's three-terminal contract.
- The doc reads clean under the eight-word tone canon (no anthropomorphic synonyms; no LLM tells).

### Command exit codes

- `grep -c '^## ' substrate/process/signals/session-vocabulary.md` returns at least 8 (§§ A-H).
- `grep -c '^### ' substrate/process/signals/session-vocabulary.md` returns at least 8 (one per kind).
- No `substrate.` prefix on any locked kind: `grep -E '^### substrate\.' substrate/process/signals/session-vocabulary.md` exits 1 (no matches).

## observation contract

Documentation sprint; no runtime behavior. The observation is: Architect reads both files end to end, ratifies in `substrate/process/BLACKBOARD.md ## Decisions` with a one-paragraph entry naming v0.6 as the daily-driver vocabulary lock. That Decision entry is the observation contract's discharge.

## strata + cadence rules to include

Copy from TECH-SPEC §2.5 strata table + §3a cadence paragraph. Every kind's row in `0.6.json` names its stratum. Ambient kinds (`TranscriptCompacted`, `SessionWarning`) each carry their cadence invariant in the `invariants` list.

## invariants to include

Per TECH-SPEC §2.5 "Invariants":

- Every `SessionStarted` is followed by exactly one `SessionEnded` OR the record is `paused`.
- No repeated `substrate.RunStarted` on one session_id across resumes.
- Every `UserMessage` reaches at least one `FinalAnswer` OR a `substrate.ProducerFailed{producer.kind:"model"}` within `turn_max_steps × model_timeout` wall time.
- Every `Park{reason: "final_answer"}` is preceded by exactly one `FinalAnswer` at the same `turn_index`.
- `TranscriptCompacted.dropped_seq_range` is a contiguous seq range strictly below `kept_seq_start`.
- `SessionWarning` fires at most once per (session_id, condition_kind) pair.

## halt conditions to watch

- `vocabulary_change_required` — if authoring surfaces a needed kind not in the tech spec's nine.
- `observation_contract_missing` — if a behavior kind (SessionStarted, UserMessage, Park, SessionEnded, SessionCompositeSpec) has no clear dual-contract pairing target on the substrate-ui side; propose a typed gap in the rationale doc.
- `awaiting_architect_decision` — the sprint closes only when the Architect ratifies. Surface the ratification request to `## Surfaced for review`.

## definition of done

`session-vocabulary.md` exists and reads clean. Content assertions pass. Sprint 203 (UI-side lock + pairing) can read this Markdown and produce its matching `substrate-ui/signals/versions/0.6.json`. Architect has ratified (Decision entry present in `substrate/process/BLACKBOARD.md ## Decisions`).
