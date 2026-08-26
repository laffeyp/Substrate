# Sprint 209 — session topology bundled + CI record

```yaml
---
id: 209
status: pending
phase: daily-driver-piece-A
pass_kind: functional
---
```

## scope

Register `"session"` in `substrate/src/substrate/topologies/bundled.py:BUNDLED` with a CI-mode factory: `DeterministicResponder(seed=0)` driver, a scripted two-turn `test.script`, `driver_context_tokens=4096`, tools = `CALCULATOR`, `per_turn=""`, `max_turns=200`, `turn_max_steps=4`, `session_id="s_CI"`, workspace at a temp path. Generate committed `substrate/src/substrate/topologies/session/records/ci_mode.record/` via `scripts/gen_topology_records.py`. `demo replay session` walks the record; `demo run session` reproduces it byte-for-byte.

## prerequisites

- Sprint 208 closed.

## context_files

- Sprint 205-208 output.
- `substrate/src/substrate/topologies/bundled.py:65-86` — the BUNDLED dict.
- `substrate/scripts/gen_topology_records.py` — record generator.
- `substrate/src/substrate/topologies/tool_loop/records/ci_mode.record/` — reference committed record shape.

## signal contract

### Emits

Full session-topology signal set on the CI record.

### Consumes

Bundled dispatch via `substrate demo run session` and `substrate demo replay session`.

## artifact contract

### Files created or modified

- `substrate/src/substrate/topologies/bundled.py` — one new row `"session": _session` plus a `_session` factory.
- `substrate/src/substrate/topologies/session/records/ci_mode.record/events-000001.open.jsonl` — regenerated.
- `substrate/src/substrate/topologies/session/records/ci_mode.record/manifest.json` — regenerated.

### Content assertions

- `substrate topology list` includes `session`.
- `substrate demo replay session` walks the committed record without error.
- `substrate demo run session --root /tmp/session-run` produces a record whose `first_divergence` against the committed record is `None`.
- The committed record contains: RunStarted, SessionStarted, two turns (UserMessage → ModelReply → FinalAnswer → Park), SessionEnded (script terminates), RunFinalised.

### Command exit codes

- `substrate demo replay session` exits 0.
- `substrate demo run session --root /tmp/session-run` exits 0. Post-review 2026-08-25: the CI script ends with `/exit` so `SessionEnded{user_exit}` lands and the run finalises cleanly — no author choice; one exit code. The scripted fixture at `topologies/session/records/ci_mode.record/` reflects this closed shape.
- `uv run python -m pytest tests/test_session_topology_bundled.py -q` exits 0.

## observation contract

`substrate demo run session` produces the expected event trace. Diff against the committed CI record is empty. The demo is the piece-A wiring proof; sprint 210 fires the full observation contract from TECH-SPEC §3.

## halt conditions to watch

- `dual_contract_fail` if `first_divergence` returns anything non-None between demo-run and committed record.

## definition of done

`session` registered in BUNDLED. CI record committed and replay-clean. Sprint 210 (observation contract end-to-end) can dispatch.
