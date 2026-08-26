# Sprint 204 — canonical-home registry + piece-0 ratification

```yaml
---
id: 204
status: closed
phase: daily-driver-piece-0
pass_kind: architecture
---
```

## scope

Add the 17 daily-driver entities from TECH-SPEC-2026-08-25-round6 §1.6.1 to `substrate/process/WORKING_AGREEMENT.md` under a new `## Canonical home registry — daily driver` section. Architect ratifies the whole piece-0 arc (sprints 202-204) in one Decision entry, unblocking piece A dispatch. This is the last piece-0 sprint and the gate for every downstream sprint.

## prerequisites

- Sprint 202 closed and ratified.
- Sprint 203 closed and ratified.

## context_files

- `sdd-kit-2/AGENTS.md` — hard rule 7 (canonical home registry) + hard rule 12 (Sprint-0 vocabulary materialization).
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §1.6.1 (the 17-row registry).
- `substrate/process/WORKING_AGREEMENT.md` — for style parity and where to insert.
- `substrate/process/signals/session-vocabulary.md` (from 202) and `substrate-ui/signals/versions/0.6.json` (from 203) — cross-reference in the ratification entry.
- `substrate/process/BLACKBOARD.md` — the ratification lands in `## Decisions`.

## signal contract

### Emits

None (documentation).

### Consumes

The read files above.

## artifact contract

### Files created or modified

- `substrate/process/WORKING_AGREEMENT.md` — append a `## Canonical home registry — daily driver` section with the 17 rows from TECH-SPEC §1.6.1.
- `substrate/process/BLACKBOARD.md` — one new `## Decisions` entry ratifying the piece-0 arc.

### Content assertions

- The new WORKING_AGREEMENT section contains one row per entity from §1.6.1: session record, session manifest, name index, session workspace (Mode 1), session worktree (Mode 2), delegate child dir, session registry, bundle, bundle assembler, application registry, application manifest, role prompts, substrate config, daemon socket, daemon pidfile, signal vocabulary substrate side, signal vocabulary substrate-ui side, vocabulary rationale.
- Every row names the canonical home path AND the owner AND the sprint that creates or owns it.
- The BLACKBOARD ratification entry cites: sprint 202 (session-vocabulary.md v0.1 lock), sprint 203 (UI v0.6 lock + pairing), sprint 204 (registry), and states "piece A (session topology) may dispatch."

### Command exit codes

- `grep -c "^| " substrate/process/WORKING_AGREEMENT.md` — the count increases by at least 18 (one header row + 17 entities).
- The Decision entry is discoverable: `grep "2026-08" substrate/process/BLACKBOARD.md | grep -i "piece-0\|piece 0\|daily-driver.*ratif"` returns at least one line.

## observation contract

The observation is the Architect reading the three ratification artifacts (0.6.json substrate, 0.6.json UI, registry section) end to end, and writing the Decision entry with `piece A may dispatch` as its closing sentence. That sentence is the gate downstream sprints read.

## halt conditions to watch

- `awaiting_architect_decision` — the whole sprint IS the ratification. The Decision entry closes it.
- `dual_contract_fail` — if the registry section reveals an entity in TECH-SPEC §1.6.1 with no owner sprint, halt and surface for a task-breakdown revision.

## definition of done

WORKING_AGREEMENT has the new section. BLACKBOARD Decision entry names v0.6 (both sides) as locked and explicitly unblocks piece A. Sprint 205 (session topology skeleton + Structs) can dispatch on read.

Piece 0 closes here. Every downstream sprint (205-232 in substrate/process/sprints/, 033-onward in substrate-ui/sprints/) reads the Decision entry at open and refuses to dispatch if it is absent.

**Post-review 2026-08-25.** Sprint 202's output filename corrected from `signals/0.6.json` to `signals/session-vocabulary.md` (topology vocab convention on this repo — `swebench-solver-vocabulary.md` + `applications-vocabulary.md` are the precedents; substrate kernel JSON at 0.1/0.2 does not bump for application signals).
