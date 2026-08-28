# Sprint 224d — delete `_agent_legacy` no-registry fallback

```yaml
---
id: 224d
status: closed
phase: testing-discipline
pass_kind: correctness
---
```

## scope

`server.py:_agent` currently falls through to `_agent_legacy` when
`_SESSION_REGISTRY is None`. That branch exists because three pre-bridge
tests in `test_server.py` wire the server without a registry. It is code
shaped to pass tests, not tests shaped to verify code — the spec
(§7 line 690) names the legacy path as "one release," not "the fallback
whenever a caller lacks a registry."

Delete the fallback. Fix the three tests to either initialize a real
registry (real) or pass `legacy=true` explicitly (real). If a caller
hits `/api/agent` without a registry in production, that is a 503
worth surfacing — not a silent legacy-shape response.

## artifact contract

### Files

- `substrate-ui/server.py` — remove the `if _SESSION_REGISTRY is None:
  self._agent_legacy(q); return` branch. Replace with a real 503.
- `substrate-ui/tests/test_server.py` — the three failing tests either
  install a real registry or pass `legacy=true`.

### Assertions

- `_agent` with `_SESSION_REGISTRY = None` and no `legacy=true` returns
  503, not 200.
- Test suite stays 160/160 green.
