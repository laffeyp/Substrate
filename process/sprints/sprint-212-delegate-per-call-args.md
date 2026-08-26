# Sprint 212 — delegate per-call args (model, child_session_name, context, baseline)

```yaml
---
id: 212
status: closed
phase: daily-driver-piece-C
pass_kind: architecture
---
```

## scope

Extend `make_delegate` at `substrate/src/substrate/topologies/tool_loop/delegate.py:187` with three new constructor kwargs (`session_registry`, `parent_session_id`, `parent_record_root`) and grow the returned `Tool.run(a)` to read per-call args from a dict: `task` (required), `model`, `child_session_name`, `context`, `baseline`, `timeout_seconds`. Extend the `Tool.schema` field at `delegate.py:274` from the current one-property `{task}` to the six-property JSON schema per TECH-SPEC §5.

## prerequisites

- Sprint 211 closed.

## context_files

- Sprint 211 output: `substrate-ui/session_registry.py`.
- `substrate/src/substrate/topologies/tool_loop/delegate.py:187-275` — existing `make_delegate` (do not break existing callers).
- `substrate/src/substrate/topologies/tool_loop/tools.py:437-460` (`parse_tool_call`, `_named_to_positional`) — how tool-call args flow.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §5 (four dispatch paths + schema shape).

## artifact contract

### Files

- `substrate/src/substrate/topologies/tool_loop/delegate.py` — grow constructor + `Tool.run` + schema.

### Assertions

- Every existing test in the tree that calls `make_delegate(...)` still passes without change (backwards compatibility — new args all default `None`).
- New tests confirm the six-property schema is present on the returned `Tool.schema` and visible to `ollama_tools(suite)`.
- `Tool.run(a)` where `a[0]` is a dict reads all six per-call fields; where `a[0]` is a plain string, treats it as `task` (backwards compat with the old shape).

### Tests

- `tests/test_delegate_backwards_compat.py` — every existing delegate call still works.
- `tests/test_delegate_schema_six_fields.py`.

## observation contract

**Scope amendment folded 2026-08-26.** The original observation contract asserts three dispatch behaviors (model swap, context slice, baseline override). All three require the same dispatch-wiring surface: a caller-supplied resolver mapping the model tag to a Responder (path 2), a `parent_record_root` reader for `context.parent_seq_range` (path 3), and a hook into the child topology's baseline-build seam (paths 3 + 4). Sprint 213's title is "delegate four dispatch paths" — that's the correct home for every one of these behaviors. Rescoped in place: sprint 212 discharges the PARSE + SCHEMA + BACKWARDS-COMPAT layer today. The five per-call optional args land in `args_dict` inside `Tool.run` and are visible to the sprint 213 wiring; the schema declares all six properties with the `x-args-passthrough` marker so `_named_to_positional` no longer drops trailing optionals when a middle arg is absent (a real bug in the sprint 212 wire — see the test file). Sprint 213 fires the four dispatch paths against these parsed values.

## halt conditions

- `vocabulary_change_required` if the new schema fields collide with an existing tool's args.
- `dual_contract_fail` if any pre-existing test regresses.

## definition of done

Delegate accepts six per-call args. Existing callers unchanged. Schema declares all six. Sprint 213 (four dispatch paths) can dispatch.
