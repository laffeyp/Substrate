# WORKING_AGREEMENT.md — Substrate

*Project-specific overrides and additions on top of `sdd-kit-2/AGENTS.md`. The Agent reads AGENTS.md first (the methodology) then this file (the project specifics). This file augments; it never overrides AGENTS.md hard rules. When the two conflict, AGENTS.md wins.*

---

## Project identity

- **Project name:** Substrate
- **Project type:** Python library + CLI (concurrent streaming dataflow runtime)
- **Primary language(s):** Python 3.12+ (CI matrix 3.12, 3.13, 3.14); asyncio
- **Primary build commands:** `uv run pytest` (suite) · `uv run substrate conformance` (release gate) · `uv run mypy --strict` (public-API type gate) · `uv run ruff check`
- **Adopted SDD kit version:** `sdd-kit-2` (read-only canon at `../sdd-kit-2/`)
- **License:** Apache-2.0 (product D-1)

---

## Project class

**Backend / data-pipeline** + **CLI / command-line** + (optional extras) **LLM-integration**. Consult `TECHNIQUES.md` Section 2 → those three subsections during sprint composition. Notable class techniques in play: Wave-0 carry / pre-filled contract files (the public API surface is consumed by many subsystems); N.INT integration sprints at wave boundaries; always-emit-summary + paired-incident; operator-chain category alignment; exit-codes-as-contract; stdout-for-data/stderr-for-narration; flag-driven instrumentation; external-SDK reverse-engineer-first (msgspec, rfc8785).

---

## Project scope (verbatim from BLACKBOARD ## Decisions)

> *Pending first Architect ratification. The proposed scope is in `BLACKBOARD.md ## Surfaced for review` (PROPOSED_DECISION, 2026-06-12). Once ratified into `## Decisions`, restate it here verbatim.*

---

## Canonical specs (the corpus this project implements)

| Spec | Canonical file | Draft |
|---|---|---|
| Kernel semantics (eight primitives, append cycle, replay) | `kernel_spec/v15.md` | v15 |
| Product (requirements F-*, N-*, conformance §7, reference topologies §8, decisions D-1..D-9) | `product_spec/draft7.md` | DRAFT 7 |
| Technical (byte layout, writer cycle, public API, constants §19) | `technical_spec/draft5.md` | DRAFT 5 |
| Design (API ergonomics, CLI UX, error UX) | `design_spec/draft1.md` | DRAFT 1 |

Superseded drafts under `product_spec/`, `technical_spec/`, `kernel_spec/` are audit-trail history (no deletions, hard rule 12); cite only the canonical drafts above.

---

## Canonical home registry

*Per AGENTS.md hard rule 7. Seeded from technical spec §16 (public API) + §3 (record format). Firms up as architecture sprints land; add rows as types stabilize. Import root is the package name (B-Q-1, unresolved — placeholder `substrate`).*

| Type / module | Canonical home (planned) | Notes |
|---|---|---|
| `Event`, `BlobRef`, `ProducerRef`, `Subscription` | `substrate/types.py` | Frozen msgspec Structs; the on-disk envelope (tech §3.4). Sole declaration. |
| `Producer`, `View` (Protocols) | `substrate/protocols.py` | `start(input) -> AsyncIterable[Event]`; `update`/`value`. |
| `TopologyBuilder`, registry | `substrate/topology.py` | One builder method per primitive (design §4.1). |
| `Runtime`, `RunResult`, the append cycle / writer | `substrate/runtime.py` | Single writer; the append cycle (tech §6). |
| Admission queue, control queue | `substrate/runtime.py` | Bounded `asyncio.Queue`; control bypasses admission. |
| Firing policies (`Once`, `PerEvent`, `PerKey`, `WhileTrue`), cooldowns (`Logical`, `WallClock`) | `substrate/triggers.py` | Tech §10. |
| Standard Views (`BufferView`, `KindCount`, `PerKindLatest`, started/completed counts) | `substrate/views.py` | F-VIEW-2. |
| Standard policies (`cancel_all_others`, `let_finish`, `quiescence_with_watchdog`, `threshold_count`, `all_completed`, `subtree_cancellation`, `pause_await_input`, `any_of`, `all_of`) | `substrate/policies.py` | F-LIFE-2. |
| Canonical encoding (RFC 8785 pipeline, type whitelist, `B_hash`/`B_disk`) | `substrate/encoding.py` | Tech §4. |
| Run record on disk (segments, sealing, frame/CRC, manifest, blob store, recovery) | `substrate/record.py` | Tech §3, §5. |
| Replay engine (Levels 1–3b) | `substrate/replay.py` | Tech §12. |
| Live attach (follower) | `substrate/attach.py` | Tech §13. |
| Inspection / provenance / divergence | `substrate/inspect.py` | Tech §14; `explain_producer`, `trace_ancestry`, `view_at`, `decisions_between`, `first_divergence`. |
| Test helpers (`assert_event`, `assert_no_event`, `assert_sequence`) | `substrate/testing.py` | F-API-4 / tech §15. |
| Public API re-exports | `substrate/api.py` | F-API-6: `substrate.cli` may import only this. |
| CLI (`run`, `replay`, `inspect`, `validate`, `tail`, `conformance`, `resume`, `stats`) | `substrate/cli.py` | Click + Rich; public API only. |
| The locked vocabulary | `signals/0.1.json` | Produced by Sprint 0. Loaded, not hand-edited. |

---

## External SDK bridge mappings

*Per AGENTS.md hard rule 10 / technique 46. The first sprint that imports an SDK without a bridge mapping here MUST halt with `bridge_mapping_required`. Reverse-engineer the real API surface before authoring against it. To be completed in a `pass_kind: bridge` sprint before the encoding/record sprints dispatch.*

### msgspec (`>=0.21,<0.22`)
- **Used for:** Struct definitions, schema validation at the bus boundary, `msgspec.to_builtins()` (input to the JCS pipeline), `msgspec.json.schema()` for `RunStarted` schema descriptors, pre-built `msgspec.json.Decoder` per (kind, version).
- **Critical surface (verify against installed version before use):** `msgspec.Struct(frozen=True)`; frozen-Struct mutation raises; `msgspec.json.Decoder(Type)` / `.decode(bytes)`; `msgspec.to_builtins(obj)`; `msgspec.json.schema(Type)` → JSON Schema draft 2020-12. *Status: STUB — reverse-engineer and pin before the validation/encoding sprints.*

### rfc8785 (pinned)
- **Used for:** RFC 8785 (JCS) canonical JSON encoding — the bytes everything hashes over (`B_hash`).
- **Critical surface:** the dump/encode entry point producing canonical bytes from Python builtins. CI runs the RFC 8785 conformance vectors every commit. *Status: STUB — reverse-engineer and pin before the encoding sprint.*

### python-ulid, click, rich
- python-ulid: `run_id` generation. click: CLI parsing. rich: terminal output. Document surfaces before the CLI sprints.

---

## Vocabulary discipline overrides

- **Validator-extras posture:** **strict.** Payload fields not declared in the schema raise at emit time (emission becomes `substrate.ProducerEmittedInvalidEvent` with reason `non_canonical_value`/`schema_violation`). Rationale: matches the substrate's own product principle 4 — bus-boundary validation is *mandatory and non-configurable*; a documentation-only posture would contradict the product the project ships.
- **View-payload-universal convention:** the substrate has no `view` *category* in the UI sense — Views are runtime projections, not rendered scenes. The dual contract's "view-side counterpart" maps instead to **the run record on disk**: every behavior tag's effect must be reconstructable from the persisted log (replay Level 1/2). The dual-contract audit (BOOTSTRAP Step 9) pairs each behavior tag with a record-observable assertion (a sequenced event + a `view_at`/`decisions_between` reconstruction), not a screen element. Documented in the rationale doc.
- **Reserved namespace:** kernel/control-plane kinds use the `substrate.` prefix (F-OBS-5); Producer-declared kinds MUST NOT collide. The vocabulary JSON marks each tag's namespace.
- **Vocabulary location:** `signals/0.1.json` (default). Rationale doc: `signals/0.1-rationale.md`. Open proposals: `signals/proposals.json`.

---

## Build and verification commands

*The Architect runs these; the Agent does not silently retry failed builds (reports exit code + last 200 lines).*

- **Primary build / test:** `uv run pytest` — expected exit 0
- **Release gate:** `uv run substrate conformance` (the 17 checks) — expected exit 0
- **Type gate (public API):** `uv run mypy --strict` — expected exit 0
- **Lint/format:** `uv run ruff check` / `uv run ruff format --check` — expected exit 0
- **Perf floor (N-PERF-1):** `uv run pytest-benchmark` at the reference shape — ≥100K appends/sec; ≤20% regression vs previous release tag (conformance check 15)
- **Canonical-encoding stability:** RFC 8785 conformance vectors — byte-identical, every commit

---

## Observation contract environment

*Substrate has no UI/simulator. The "observation" surface is the run record on disk + the CLI reading it. Behavior-touching sprints (writer cycle, replay, record, attach, CLI) declare an observation contract whose driving step runs a topology (or a recorded fixture) and whose assertions are: expected sequenced events in the JSONL trace, expected `assert_event`/`assert_sequence` results, expected exit code, expected `replay --level N` outcome, expected `inspect`/`tail` output substrings. Tools: `pytest`, the CLI subcommands, `assert_event`/`assert_no_event`/`assert_sequence` (tech §15), and a confirmed-good run record as a regression fixture (F-API-4 / technique 38).*

---

## Hand-author authorization log

*Per AGENTS.md hard rule 10. Explicit hand-authorizations logged here.*

- None to date.

---

## Tone canon (CLI / error strings)

The substrate's user-facing strings (CLI output, error messages, `tail`/`inspect` lines) follow the design spec's structured-output discipline:

- **Structured output everywhere; never natural language from the runtime.** `explain_producer` returns a typed `Explanation`, not prose. Errors carry typed fields (`error_kind`, `at_path`, `sequence`).
- **Sequence numbers everywhere identification happens.** "At seq 1247" — never "around the third trigger."
- **Vocabulary discipline (product principle 6 / design §2):** the eight words (Producer, Bus, View, Predicate, Trigger, Route, TerminationPolicy, Topology) and no anthropomorphic synonyms ("agent", "actor", "speaker") and no marketing reframes ("workflow", "step", "task"). This applies to docs, CLI output, log fields, AND code identifiers.
- **No emoji** (kit tone canon + design spec). Registration errors follow the design §6.1 shape: where → one-line summary → what's wrong → upstream constraint → inline fix.
- Tonal constraints bind Layer 7 (Evidence) for any payload field carrying user-visible strings.

---

## Custom techniques (project-specific orchestration, layered on top of the kit)

*The Architect mandated maximal use of parallel agent teams and worktree isolation. The kit defers these to TECHNIQUES Section 3 ("compose with any orchestrator"); they are NOT in the kit canon, so they live here as project techniques. They sit ON TOP of the kit discipline and never bypass it: the dual contract, the Rubber Duck Pass, the vocabulary lock, and hard rule 10 (no silent hand-author) still gate every close.*

- **CT-1 — Parallel subagent teams (fan-out → synthesize → adversarially verify).** Decomposable work (research strands; per-subsystem vocabulary drafting; per-dimension review) is fanned out to concurrent subagents, synthesized by the Supervisor hat, then adversarially verified by independent agents before anything lands. Pattern: Workflow `pipeline`/`parallel`. Apply when the work-list is independent and the conclusion (not the file dumps) is what matters.
- **CT-2 — Originals over summaries for every spawned agent (hard rule 11, enforced).** Every subagent prompt transmits *file paths to read* (the kit foundations/grammar/TECHNIQUES, the canonical specs, the locked vocabulary) — never my summary of them. An agent that hasn't read the originals for its slice halts. This is the load-bearing transmission discipline; summary-induced drift is the documented failure mode.
- **CT-3 — Per-sprint git worktree isolation for parallel implementation.** When two or more implementation sprints touch file-disjoint slices and could run concurrently, each runs in its own git worktree (`Agent` `isolation: "worktree"`) so parallel file mutation can't conflict; results merge back via the Architect's integration-manager review (technique 21). Worktrees are EXPENSIVE and only used when agents genuinely mutate files in parallel — NOT for read-only research or for sprints that return structured proposals to the Supervisor (Sprint 0 is the latter: no worktrees needed). Requires git (initialized).
- **CT-4 — Best-of-N for high-stakes architecture sprints.** For architecture-band sprints establishing load-bearing contracts (encoding, writer cycle, record format), generate N independent candidate implementations from different angles, score against the dual contract + conformance checks, synthesize from the winner grafting the best of runners-up. Deferred-in-kit (Section 3); used here because the substrate's contracts are conjunctive and a wrong contract is expensive. Never lands a candidate that fails its dual contract.
- **CT-5 — Conformance-check-as-acceptance-spine.** The 17 conformance checks (product §7) and R-1..R-3 (§8) are the project's integration proofs. Every implementation wave ends with an N.INT sprint asserting the relevant checks pass end-to-end (technique 16). Each conformance check maps to the sprints that satisfy it (tech §21 table is the seed).

---

## Sprint cadence policy

- **Phase 0 (Vocabulary Session):** plan-mode (Architect drives; ratifies the locked vocabulary + rationale).
- **Phase 1+ (implementation):** **auto-within-phase (Architect directive 2026-06-13: "keep going autonomously, parallelize as much as possible, never make stuff up, stop and research if any issues, refer to the original docs").** The Agent dispatches Wave/sprint chains without per-card go-ahead, surfacing to BLACKBOARD only on a genuine halt (spec ambiguity, unverifiable API, dual-contract fail, vocabulary-change-required). Discipline unchanged: author against the locked vocabulary + canonical specs; verify external API surfaces from their real docs before use (bridge-mapping-required halt if undocumented); dual contract + Rubber Duck Pass at every close; never invent vocabulary or APIs.

---

## Project-specific halt conditions

*In addition to AGENTS.md base halts.*

- `spec_ambiguity` — a sprint needs a semantic the canonical specs underspecify (vs. a vocabulary gap). Surface with the exact spec section + the ambiguity. Resume: Architect rules, or cuts a spec revision (specs are revised additively — new draft, prior preserved).
- `conformance_unmapped` — a sprint's artifact is needed by a conformance check but no sprint chain yet covers that check end-to-end. Surface for wave re-planning.

---

*WORKING_AGREEMENT.md for Substrate. Project class backend/library + CLI. Strict validator-extras. Orchestration (teams + worktrees + best-of-N) layered on top of the kit as project techniques CT-1..CT-5, never bypassing the dual contract or vocabulary lock. Canonical specs: kernel v15, product DRAFT 7, technical DRAFT 5, design DRAFT 1.*
