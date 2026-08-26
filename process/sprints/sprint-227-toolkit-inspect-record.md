# Sprint 227 — substrate toolkit: inspect_record + progressive disclosure + HMAC cursor

```yaml
---
id: 227
status: pending
phase: daily-driver-piece-F
pass_kind: architecture
---
```

## scope

Grow `substrate_tools.py` (from sprint 226) with `make_inspect_record(records_root) -> Tool`. Filter shape: `{kinds?, seq_range?, producer?, application?, time_range?}`. Formats: `summary` (default) → `api.narration_summary`; `narrate` → `api.narrate`; `events` → `api.read_record` filtered; `first_divergence` → `api.first_divergence(a, b)`; `run_graph` → `api.run_graph`. Budget cap in tokens: `min(1024, 0.25 * driver_context_tokens)` — both operands are token counts, comparable. 1024 tokens ≈ 4 KB text at ~4 chars/token — the round-5 "4096 bytes" figure was the same target expressed in bytes, which mixed units against `driver_context_tokens`. Post-review 2026-08-25: everywhere the cap appears, it is in tokens. `driver_context_tokens` is read from the session_registry entry for the calling session. Cursor pagination with HMAC signing (per-daemon-boot random key). Cursor payload: `msgspec.json.encode({record, kinds, seq_range, producer, next_seq})`, HMAC-SHA256 signed, base64-encoded, opaque to the model.

## prerequisites

- Sprint 226 closed.

## context_files

- Sprint 226 output.
- `substrate/src/substrate/api.py` — `read_record`, `narrate`, `narration_summary`, `run_graph`, `first_divergence`.
- `substrate/src/substrate/cli.py:317-352` — reference for filter shape.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §8 (inspect_record row) + §3a (driver_context_tokens source).

## artifact contract

### Files

- `substrate/src/substrate/topologies/tool_loop/substrate_tools.py` — grow with `make_inspect_record`.

### Assertions

- Default `format="summary"` returns ≤~200 tokens.
- `format="events"` filtered by kinds returns events; overflow returns `{has_more: true, cursor: <opaque>}`; `continue_from=cursor` returns next slice.
- Budget cap: no single response exceeds `min(1024, 0.25 * driver_context_tokens)` tokens (estimated via `_est_tokens`).
- Tampered cursor → `ToolResult(ok=false, error: "invalid cursor")`.
- `application` filter reads `RunStarted.payload.topology` from the record's manifest section; `time_range` filters by event `t` field.

### Tests

- `test_inspect_record_summary_default.py`
- `test_inspect_record_filter_kinds.py`
- `test_inspect_record_filter_application.py`
- `test_inspect_record_filter_time_range.py`
- `test_inspect_record_cap_25pct.py` — cap follows driver context.
- `test_inspect_record_cursor_hmac.py` — tampered cursor rejected.

## observation contract

Session with a long record; model calls `inspect_record(record, format="summary")` first — gets counts. Escalates to `format="events", filter={kinds: ["ModelReply"], seq_range: [50, 100]}` — gets the actual assistant text. Third call with the returned cursor gets next slice.

## halt conditions

- `vocabulary_change_required` if a filter field is needed beyond the five documented.
- `dual_contract_fail` if the cap is exceeded under any filter/format combination.

## definition of done

`inspect_record` handles five formats + five filters + HMAC-signed cursor + budget cap. Sprint 228 (list_* tools) can dispatch.
