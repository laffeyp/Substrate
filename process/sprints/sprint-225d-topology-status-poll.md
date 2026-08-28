# Sprint 225d — GET /api/topology/<name>/status?run_id=<id>

```yaml
---
id: 225d
status: closed
phase: daily-driver-piece-E
pass_kind: functional
---
```

## split rationale

Fourth of four sub-cards splitting sprint 225. Closes the async loop
that 225a's `await_completion=false` shape opens.

## scope

- `GET /api/topology/<name>/status?run_id=<id>`.
- Reads the run's record via `api.read_record`; classifies status per
  the same rules `_scan_record_status` uses (RunFinalised → finalised;
  torn → failed; empty → running; anything else with a tail → running).
- Returns `{run_id, status, record_root, elapsed_seconds, output?}`
  per TECH-SPEC §8 line 1057.
- 404 on unknown run_id (no record dir).

## artifact contract

### Files

- `substrate-ui/server.py` — new handler + GET routing branch.
- Piggybacks on `_RUNS: dict[str, RunHandle]` from 225a for
  `elapsed_seconds` bookkeeping.

### Assertions

- After 225a's `await_completion=false` returns, polling status
  transitions from `running` → `finalised` within a bounded number
  of poll intervals.
- Terminal status carries `output` extracted from the record's
  application-terminal envelope (Solved / Verdict / Synthesis).

### Tests

- `substrate-ui/tests/test_server_topology_status_225d.py`

## observation contract

`POST /api/topology/best_of_n_verified/run` with
`await_completion=false` → poll `/api/topology/best_of_n_verified/status?run_id=<id>`
until `status == "finalised"`.

## definition of done

Async application dispatch works end-to-end. Piece E closes.
