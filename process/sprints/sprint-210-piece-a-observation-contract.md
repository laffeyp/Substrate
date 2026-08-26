# Sprint 210 — piece A observation contract end-to-end

```yaml
---
id: 210
status: closed
phase: daily-driver-piece-A
pass_kind: observation
---
```

## scope

Fire the piece-A observation contract from TECH-SPEC §3. UI driving steps + expected log substrings + expected runtime signals + expected screenshot. Closes piece A. This is the SDD hard-rule-9 gate — piece A does not close until this sprint runs green in CI.

**Scope amendment folded 2026-08-26.** The card names a `substrate chat deterministic --script fixtures/two_turns.json --name test-piece-a` CLI subprocess harness. That CLI lands in pieces B/C/D (sprints 214-221); it does not exist yet. Rescoped in place: sprint 210 discharges the RECORD-LEVEL observation contract in-process today, using `ci_session_topology(turns=<from fixture>)` to drive the same three-turn script. The stderr-substring checks and the terminal-screenshot check defer to sprint 221 once `substrate chat` exists. The fixture `tests/fixtures/two_turns.json` lives on disk so sprint 221 picks it up verbatim.

The application-kind sequence, the per-event payload predicates, the lifecycle-event coverage (ProducerStarted / ProducerCompleted / TriggerFired), the TerminationMatched decision, and Level-3(a) replay all fire here.

## prerequisites

- Sprints 205-209 all closed.

## context_files

- Sprints 205-209 output.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §3 observation contract block (UI driving steps + expected log substrings + expected runtime signals + expected screenshot).
- `sdd-kit-2/AGENTS.md` hard rule 9 (observation contract for behavior-touching sprints).

## signal contract

### Emits

None (observation sprint). Reads what piece A emits.

### Consumes

Piece A's session topology + committed CI record.

## artifact contract

### Files created or modified

- `substrate/tests/test_session_topology_e2e.py` — new. Runs `substrate chat deterministic --script fixtures/two_turns.json --name test-piece-a` in a subprocess; captures stderr; reads the resulting record; asserts every observation-contract predicate.
- `substrate/tests/fixtures/two_turns.json` — new. `[{"text": "say hi"}, {"text": "count to five"}, {"text": "/exit"}]`.

### Content assertions

- Stderr contains: `"session test-piece-a started (record: ...)"`, `"[paused]"` twice, `"[finalised]"`.
- The record's event sequence matches exactly: `substrate.RunStarted`, `SessionStarted`, `UserMessage(turn_index=0, text="say hi")`, `substrate.TriggerFired(resume-on-user)`, `substrate.ProducerStarted(model)`, `ModelReply(turn_index=0)`, `FinalAnswer`, `substrate.ProducerCompleted(model)`, `substrate.TriggerFired(park-on-final)`, `substrate.ProducerStarted(park)`, `Park(reason="final_answer", turn_index=0)`, `substrate.TerminationMatched(decision=pause-await-input)`, `UserMessage(turn_index=1, text="count to five")`, ... (mirror for turn 1) ..., `UserMessage(text="/exit", turn_index=2)`, `substrate.TriggerFired(end-on-exit)`, `substrate.ProducerStarted(session_end)`, `SessionEnded(reason="user_exit", total_turns=3)`, `substrate.TerminationMatched(decision=finalise-run)`, `substrate.RunFinalised`.
- Terminal screenshot (captured via a small pty-driver helper) shows: prompt line, two assistant outputs each followed by a fresh prompt, then clean exit. No error output.

### Command exit codes

- `uv run python -m pytest tests/test_session_topology_e2e.py -q` exits 0.
- Full-suite regression clean (baseline set at 850+ tests; the 210 sprint adds one).

## observation contract

This IS the observation contract. Discharged when the test passes green in CI.

## halt conditions to watch

- `observation_contract_missing` — inverse: this sprint IS the discharge; if the harness cannot be authored, halt piece A itself.
- `dual_contract_fail` if any expected substring is absent or any expected signal missing.

## definition of done

`test_session_topology_e2e.py` green in CI. Piece A closes. Pieces B, C, D, F unblock (piece E dispatches independently after piece 0). Session topology is the confirmed load-bearing foundation for the daily driver.
