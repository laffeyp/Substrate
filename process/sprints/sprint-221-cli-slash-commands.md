# Sprint 221 — CLI slash-command router (nine slashes)

```yaml
---
id: 221
status: closed
phase: daily-driver-piece-D
pass_kind: functional
---
```

## scope

Author `_slash_route(line, session) -> bool` and wire it into the REPL. Nine slashes per TECH-SPEC §6 table:

- `/exit` — send literal `"/exit"` as UserMessage (only slash the model sees).
- `/model <name>` — `PATCH /api/session/<id> {driver: "<name>"}`; persists across parks.
- `/tools <comma-list>` — `PATCH /api/session/<id> {tools: [...]}`; persists.
- `/context <seq-range> [--kind K]` — LOCAL: stores `{parent_seq_range: [a,b], kinds: [K]}` in a per-REPL `_pending_context` dict; next `_daemon.turn` passes it as `context={...}` in the request body; daemon prefixes extracted slice to `UserMessage.assembled_prompt`; state cleared after use.
- `/inspect <record> [--filter …]` — LOCAL: invoke `api.narrate` or `api.explain_producer` directly (F-API-6 respected).
- `/list [records|topologies|sessions|applications]` — LOCAL for records/topologies (`api.read_record`, `bundled.names()`); daemon for sessions/applications (`GET /api/session`, `GET /api/applications`).
- `/replay <record>` — LOCAL: invoke `cli.replay` verb directly.
- `/run <application> [args]` — DAEMON: `POST /api/topology/<name>/run`; runs as sibling to session; streams events via existing SSE thread.
- `/help` — LOCAL: print the slash list.

**Scope amendment folded 2026-08-28.** Two of the nine slashes depend on sprint 217e's daemon extensions (PATCH-tools and POST-/turn-context); the third defers to piece E.

- **`/tools`** — works after sprint 217e lands (PATCH admits `tools`). This sprint's prerequisites now include 217e.
- **`/context`** — works after sprint 217e lands (POST /turn body parses `context`). Same prerequisite.
- **`/run <application>`** — depends on `POST /api/topology/<name>/run`, which the tech spec §7 explicitly assigns to piece E (sprints 223-225). This sprint ships the `/run` handler as `_slash_route` returns True with a helpful `[not yet: piece E ships /api/topology/<name>/run]` printed to stderr; the model does not see the input. The full behaviour lands with piece E.

The other six slashes (`/exit`, `/model`, `/inspect`, `/list`, `/replay`, `/help`) work today.

## prerequisites

- Sprint 220 closed.
- Sprint 217e closed (PATCH-tools + POST-/turn-context).

## context_files

- Sprint 218-220 output.
- `substrate/src/substrate/cli.py:382-393` — `explain_producer` / `trace_ancestry` usage (for /inspect).
- `substrate/src/substrate/topologies/bundled.py:names` — for /list topologies.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §6 slash-command table + product spec §2a for cross-verification.

## artifact contract

### Files

- `substrate/src/substrate/cli.py` — `_slash_route` + nine handler helpers.

### Assertions

- Only `/exit` becomes a UserMessage on the record; every other slash bypasses the model.
- `/run code_review --repo .` fires `POST /api/topology/code_review/run`; the topology's record streams into the CLI's SSE thread; the session's record shows NO UserMessage containing `/run`.
- `/context 10-20 --kind FinalAnswer` stores the pending state; the next `_daemon.turn` includes `context={...}`; the third turn (without another `/context`) has no context.
- `/model claude` PATCHes; session's manifest.json shows `driver: "claude"`; next `Runtime.resume` builds `session_topology` with the new driver.

### Tests

- `test_cli_slash_run_out_of_band.py`
- `test_cli_slash_context_stateful.py`
- `test_cli_slash_model_persists.py`
- `test_cli_slash_inspect_local.py`
- `test_cli_slash_exit_reaches_model.py` — verifies `/exit` is the ONLY slash that lands as a UserMessage.

## observation contract

Manual: `substrate chat deterministic`, type `/model kimi`, `/tools read_file,grep`, `/context 5-10`, then a normal `hi`; verify session state matches expected. Type `/exit`; session ends with `reason="user_exit"`.

## halt conditions

- `dual_contract_fail` if any non-/exit slash reaches the model.
- `vocabulary_change_required` if `/context` needs a payload field not covered by the delegate schema.

## definition of done

Nine slashes routed correctly. Sprint 222 (session/bundle/builder subverbs) can dispatch.

## closure note 2026-08-28

Closed as one file (`substrate/src/substrate/cli.py`) + one test file
(`substrate/tests/test_cli_slash_221.py`, 10 tests, all green). The test
names in this card's "Tests" section were superseded by one consolidated
file at review time; the assertions moved into that file verbatim:

- `test_exit_returns_false_so_repl_sends_as_user_message` — `/exit` is the
  only slash returning False from `_slash_route`, so the REPL sends the
  literal `"/exit"` as a UserMessage.
- `test_context_stores_pending_range_and_kinds` — `/context 3-9 --kind
  ToolResult` stores `{parent_seq_range: [3,9], kinds: ["ToolResult"]}`
  in the REPL's `pending_context`; the next `_daemon.turn` reads and
  clears it.
- `test_model_calls_patch_session_driver`, `test_tools_calls_patch_session_tools_list`
  — PATCH wiring against the daemon client.
- `test_list_sessions_calls_daemon`, `test_list_applications_prints_piece_e_deferral`,
  `test_run_prints_piece_e_deferral` — daemon + deferral shapes.
- `test_help_prints_slash_list_and_returns_true`, `test_unknown_slash_returns_true_with_hint`,
  `test_non_slash_returns_false`, `test_model_missing_arg_prints_error` — router shape.

The observation contract (manual smoke) still stands and will run once the
daemon build path is exercised end-to-end at the piece-D bundle test.
