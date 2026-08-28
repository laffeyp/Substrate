# Sprint 234 — delegate.py hygiene split into a package

```yaml
---
id: 234
status: pending
phase: hygiene
pass_kind: architecture
---
```

## scope

REVIEW-2026-08-28 F6 also flagged `src/substrate/topologies/tool_loop/delegate.py`
at 663 lines. The piece-C review (2026-08-25) had already named the
split in its finding 11: "delegate.py at 592 lines — hygiene split
into `delegate/dispatch.py` + `delegate/context.py` + `delegate/model.py`
when the seam settles." The seam has settled — piece C closed, piece B
closed, pieces D and E have not further modified it. The natural moment
to split is now, before piece G roots the current shape.

Target layout under `substrate/src/substrate/topologies/tool_loop/delegate/`:

- `delegate/__init__.py` — re-exports the public surface
  (`make_delegate`, `SESSION_ENDED_MID_DELEGATE`, plus any Struct or
  Tool that outside callers import). Wildcard re-export from
  `dispatch.py`.
- `delegate/dispatch.py` — `make_delegate` factory, cross-thread
  worker + `_run_child_to_answer`, timeout + cancel-grace path.
- `delegate/context.py` — `_prefix_context_slice` + related helpers
  (context slice cap, event-boundary drops).
- `delegate/model.py` — the delegate's schema declaration (`Tool.schema`
  for delegate) + `_named_to_positional` mapping if used.
- `delegate/session_bind.py` — the SessionRegistry integration path
  (per-call `child_session_name`, `SessionEndedMidTurn` handling).

Every existing import continues to work through `delegate/__init__.py`
re-exports. Substrate-ui's `session_errors.py` reads
`SESSION_ENDED_MID_DELEGATE` from `substrate.topologies.tool_loop.delegate`;
that import continues to work after the split (re-exports).

## prerequisites

- Sprint 233 closed (cli hygiene split establishes the split pattern).

## artifact contract

### Files

- `substrate/src/substrate/topologies/tool_loop/delegate/` (new package,
  5 files).
- `substrate/src/substrate/topologies/tool_loop/delegate.py` — deleted;
  git history preserves.

### Assertions

- Every existing delegate test passes (52 in `tests/test_delegate*.py`).
- `substrate.topologies.tool_loop.delegate.make_delegate` importable
  under the same name.
- `SESSION_ENDED_MID_DELEGATE` importable under the same name.
- Every file in `delegate/` under 250 lines.

### Tests

- Existing 52 delegate tests pass unchanged.
- `test_delegate_package_reexports.py` — imports every previously-
  exported symbol from `substrate.topologies.tool_loop.delegate`.

## signal contract

Emits: (none — hygiene split; no runtime emit sites in the diff).

## observation contract

Delegate wire behavior — child record shape, timeout, cancel-grace,
`session_ended_mid_delegate` tag — unchanged. Existing tests are the
observation contract.

## halt conditions

- `dual_contract_fail` if any test drifts.

## definition of done

Every existing test passes; `delegate.py` is gone; `delegate/` is a
package.
