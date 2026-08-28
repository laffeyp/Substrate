# Sprint 220 — CLI Ctrl+C / Ctrl+D / SIGHUP handlers + SUBSTRATE_SESSION env

```yaml
---
id: 220
status: closed
phase: daily-driver-piece-D
pass_kind: functional
---
```

## scope

Wire three signals and one env var to the REPL from sprint 219. Ctrl+C: while `_turn_in_flight=True` → `POST /api/session/<id>/interrupt` (piece B sprint 215); while idle → print `(no turn in flight; type /exit or press Ctrl+D to end)` and continue. Ctrl+D (EOF): `POST /api/session/<id>/end` with reason `"user_end"`; break out of REPL. SIGHUP (terminal close): CLI catches, POSTs nothing, exits cleanly; session stays parked and survives. Set `os.environ["SUBSTRATE_SESSION"]` to `session.name or session.session_id` before every `_daemon.turn` call so bash-tool subprocesses inherit it.

## prerequisites

- Sprint 219 closed.
- Sprint 215 closed (`/interrupt` and `/end` endpoints live).

## context_files

- Sprint 218-219 output.
- `substrate/src/substrate/topologies/tool_loop/tools.py:212` — bash tool subprocess.run — verifies env inheritance.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §6 signal handling table.

## artifact contract

### Files

- `substrate/src/substrate/cli.py` — signal handlers + env setter.

### Assertions

- SIGINT during turn → daemon receives `/interrupt`; record shows `substrate.ProducerCancelled` on `model` producer within 200ms.
- SIGINT idle → hint printed; REPL loop continues; session stays `paused`.
- Ctrl+D → daemon receives `/end`; session status `ended`; REPL exits.
- SIGHUP → REPL exits cleanly; session stays `paused` in `substrate session ls` after CLI exit.
- Bash tool inside a session sees `$SUBSTRATE_SESSION` set to the session's name-or-id.

### Tests

- `test_cli_ctrl_c_interrupts_only_turn.py`
- `test_cli_ctrl_d_ends_session.py`
- `test_cli_sighup_parks.py`
- `test_cli_substrate_session_env.py`

## observation contract

Manual: `substrate` bare, type `bash echo $SUBSTRATE_SESSION`; assistant runs the tool and prints the session id. During a long-running turn (slow driver), press Ctrl+C; assistant call cancels, session parks, prompt returns.

## halt conditions

- `dual_contract_fail` if any of the four signals reaches a different path than documented.

## definition of done

Three signals routed correctly; env inherited. Sprint 221 (slash-command router) can dispatch.
