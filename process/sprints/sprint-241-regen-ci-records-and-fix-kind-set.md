# Sprint 241 — regenerate session/daily CI records + fix kind-set assertion

```yaml
---
id: 241
status: closed-2026-08-31
phase: 6
pass_kind: functional
---
```

## Product-spec conformance

**Fulfills:** the piece-A observation contract (TECH-SPEC §3 + product spec §3, §9a) after sprint 240 wired the SessionStarted instrument. Closes REVIEW-2026-08-31-session-topology-vs-specs.md COR-1 (two failing tests, plus the two `test_bundled_topologies.py[session,daily]` failures the full-suite pass surfaced).

**Consumes:** sprint 240 (SessionStarted instrument). No new substrate behavior.

## Scope

Sprint 240 added the `session_started` producer_kind + RunStarted instrument. Downstream:

- `src/substrate/topologies/session/records/ci_mode.record/` was frozen 2026-08-28 16:03 — before sprint 240 landed at 20:00. Fresh runs diverge at seq 0 (RunStarted payload hash differs; topology fingerprint carries the new producer_kind).
- `src/substrate/topologies/applications/records/daily.ci_mode.record/` inherits the same drift because the `daily` application wraps `session_topology`.
- `tests/test_session_topology_e2e.py:97` asserts `set(kinds) == {"UserMessage","ModelReply","FinalAnswer","Park","SessionEnded"}` — never got `"SessionStarted"` added.

Rule-6 stretch acknowledged: three files touched (the regen script runs, updating two record dirs; one test file edited). One concept — post-240 fixture reconciliation.

## prerequisites

- Sprint 240 closed (SessionStarted instrument live).

## context_files

- `scripts/gen_topology_records.py` — the regen driver. Loops over `bundled.BUNDLED`.
- `tests/test_session_topology_e2e.py` — the kind-set assertion.
- `tests/test_session_topology_bundled.py` — the byte-identical replay test.
- `tests/test_bundled_topologies.py` — the currency gate that surfaced the `[daily]` + `[session]` failures under full-suite load.

## artifact contract → Files created/modified

- `src/substrate/topologies/session/records/ci_mode.record/` — regenerated. Post-run: fresh RunStarted payload hash + SessionStarted envelope at seq 2 + downstream envelopes shift by one seq.
- `src/substrate/topologies/applications/records/daily.ci_mode.record/` — regenerated (via the same script pass; every bundled topology regenerates in one invocation).
- `tests/test_session_topology_e2e.py` — one-line edit at the kind-set assertion: add `"SessionStarted"` to the expected set. Same for the `ordered_head` assertion if it enumerates the same shape.

## signal contract → Emits

None (no new emit sites). Every existing emit site in the session topology stays.

## observation contract

- `uv run python scripts/gen_topology_records.py` completes cleanly; two CI record dirs regenerated.
- `uv run python -m pytest tests/test_session_topology_bundled.py::test_bundled_session_matches_committed_record -q` → PASS.
- `uv run python -m pytest tests/test_session_topology_e2e.py::test_piece_a_ci_wrapper_observation_contract -q` → PASS.
- `uv run python -m pytest tests/test_bundled_topologies.py -q -k 'session or daily'` → PASS.
- `uv run python -m pytest tests/test_session_topology_*.py tests/test_session_started_instrument.py -q --timeout=60` → 21/21 PASS.

## halt conditions

- `dual_contract_fail` if the regenerated record still diverges (means sprint 240's instrument is non-deterministic in a way replay cannot re-fire).
- `awaiting_architect_decision` if the regen surfaces further drift beyond the four named failures.

## definition of done

Two CI record dirs regenerated; three test files pass; every session-topology test green.
