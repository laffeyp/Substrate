# Sprint 219 — CLI REPL + SSE streaming during blocked turn

```yaml
---
id: 219
status: closed
phase: daily-driver-piece-D
pass_kind: architecture
---
```

## scope

Add the REPL loop to `chat` (sprint 218). Cooked-mode stdin read via a `_readline_with_interrupt(prompt="> ")` helper (raises KeyboardInterrupt on SIGINT, EOFError on Ctrl+D). Background thread `_sse_stream(session_id)` opened at session start reads `GET /api/session/<id>/events` and prints each new event as it lands (ModelReply text streams; ToolCall/ToolResult as compact one-liners; substrate.* only at `--verbose`). Main thread never blocks on the daemon — it blocks on stdin. Streaming happens under the SSE thread; `_daemon.turn` returns after the event has already surfaced.

## prerequisites

- Sprint 218 closed.

## context_files

- Sprint 218 output.
- `substrate/src/substrate/cli.py:162` — existing 20ms poll interval pattern.
- `substrate/src/substrate/cli.py:317-352` — `cli.tail` streaming pattern.
- `substrate/src/substrate/api.py` — `attach`, `LiveRecord`, `follow`.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §6 REPL block + streaming rules.

## artifact contract

### Files

- `substrate/src/substrate/cli.py` — REPL loop; `_sse_stream` background thread; `_render_stream_line` formatter.

### Assertions

- ModelReply text appears on stdout BEFORE `_daemon.turn` returns (test asserts the timing).
- ToolCall renders as `→ read_file("app.py")`; ToolResult as `← ok (1240 bytes)` or `← FAIL: <error>`.
- substrate.* events suppressed by default; `--verbose` emits them dimmed.
- Ctrl+C during turn (§sprint 220 wires this); Ctrl+D exits (§sprint 220 wires this).

### Tests

- `test_cli_chat_streams_during_turn.py` — ModelReply prints before daemon.turn returns.
- `test_cli_stream_formatter.py` — the three line shapes.

## observation contract

Manual/scripted: fire `substrate chat deterministic`, type `say hi`; assistant text streams progressively, not in one blob at the end.

## halt conditions

- `comprehension_failed` if the REPL/SSE-thread ownership rules cannot be stated in one paragraph.


## signal contract

Emits: (none — CLI + SSE reader — reads envelopes, does not emit them).

## definition of done

Streaming works. Sprint 220 (Ctrl+C/D/SIGHUP + env) can dispatch.
