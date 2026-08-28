# Sprint 224f — typed markers for slash deferrals + direct boot_scan branch test

```yaml
---
id: 224f
status: closed
phase: testing-discipline
pass_kind: test-add
---
```

## scope

Two small items grouped by "typed contract, not string assertion":

1. Sprint 221's `/run` and `/list applications` write hint text to
   stderr; tests assert `"piece-E" in body`. If the hint text drifts,
   the test breaks or (worse) passes on a spelling coincidence. Replace
   the assertion target with a typed marker: `_slash_route` sets
   `pending_context["_deferred"] = "run"` (or `"list_applications"`)
   whenever it hits a piece-E deferral. Tests assert on the marker.
   The human-readable stderr line stays as-is; the test contract moves
   off the prose.

2. `session_registry.py:boot_scan` at lines 290-295 preserves `"ended"`
   as terminal. Only `test_fresh_session_transitions_to_ended_and_survives_reboot`
   exercises the branch, end-to-end. Add a direct test that writes an
   `"ended"` manifest to disk and asserts `boot_scan` leaves it
   `"ended"` — even when `_scan_record_status` would return `"parked"`
   (missing record dir) or `"interrupted"` (torn record). This isolates
   the branch from any downstream drift.

## artifact contract

### Files

- `substrate/src/substrate/cli.py` — router sets `_deferred` marker.
- `substrate/tests/test_cli_slash_221.py` — assertions target the
  marker, not string content of the stderr line.
- `substrate-ui/tests/test_session_registry_boot_scan_preserves_ended.py`
  — new file, two tests.

### Assertions

- After `/run coding_flow`, `pending_context["_deferred"] == "run"`.
- After `/list applications`, `pending_context["_deferred"] ==
  "list_applications"`.
- `boot_scan` over a manifest.json with `"status": "ended"` and NO
  record dir leaves the reloaded status `"ended"`.
- Same, with a torn record dir: still `"ended"`.
