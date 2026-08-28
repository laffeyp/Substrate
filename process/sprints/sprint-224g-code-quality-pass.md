# Sprint 224g — code-quality pass: magic strings + variable names

```yaml
---
id: 224g
status: closed
phase: testing-discipline
pass_kind: cleanup
---
```

## scope

Two adjacent code-quality gaps a pro reader would flag on day one:

1. **Magic strings.** Every string literal that is BEHAVIOR (a status
   value, a kind name, a config key) rather than DATA (a user message,
   a filename) should be a constant with a name. 224a covered the wire
   errors; this card covers the rest — session status values ("running"
   | "parked" | "interrupted" | "ended"), workspace_shape values ("flat"
   | "worktree" | "isolate"), the driver preset names ("deterministic",
   "ollama", "claude", "gemini", "cli"), the session source strings
   ("user_end", "daemon_shutdown", "user_exit"), the config keys ("defaults",
   "daemon", "session"). Each cluster becomes a Literal type or a
   typed-value module; a typo now fails at the type checker instead
   of silently matching nothing.

2. **Bad variable names.** One-letter names in non-trivial scopes and
   arbitrarily shortened names ("wt", "ws", "wt_arg", "ws_arg", "q",
   "srv", "b", "th", "r") get renamed to the concrete noun. Loop indices
   `i`, `k`, one-character math variables inside a formula, and
   idiomatic `_` for unused stay. The rule: a reader who scrolls in
   cold should know what the identifier holds without scrolling back
   to find the assignment.

Scope-limited: substrate/src/substrate/ + substrate-ui/*.py. Tests get
the same rename pass where their variables are opaque; test bodies that
already read cleanly stay.

## artifact contract

### Files

- `substrate/src/substrate/topologies/session/status.py` — new: exports
  `SessionStatus` Literal and its four values as constants.
- `substrate/src/substrate/topologies/session/prompts/config_keys.py`
  or similar — the config table keys.
- Rename pass across `substrate/src/substrate/cli.py`,
  `substrate-ui/server.py`, `substrate-ui/session_registry.py`. Not a
  mass rename; each identifier decided on the merits.

### Assertions

- `grep -rn '"running"\|"parked"\|"interrupted"\|"ended"' substrate-ui/`
  outside the new status module + tests: zero.
- `grep -c '^\s*[a-z]\s*=' substrate-ui/*.py` (single-letter assignments
  in module or function scope) drops.
- Every renamed identifier appears in git blame as a rename with a
  message naming the change.

### Tests

- All existing tests continue to pass. No new tests; this is a
  readability pass, not a behavior change.
