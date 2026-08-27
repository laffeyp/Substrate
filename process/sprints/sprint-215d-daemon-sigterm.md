# Sprint 215d — SIGTERM graceful shutdown + reason plumbing

```yaml
---
id: 215d
status: closed
phase: daily-driver-piece-B
pass_kind: functional
---
```

## scope

Fourth of four in the sprint 215 split. Ships the SIGTERM path plus
the one substrate-side change it needs to deliver the parent-card
assertion.

**What sprint 215d ships.**

  1. **`SessionEnded.reason` reflects the SessionEndRequested source.**
     `session/__init__.py::end-on-user-end` currently hardcodes
     `reason="user_end"` in its input_builder. This sprint reads
     `ctx.event.payload["source"]` and maps `"daemon_shutdown"` →
     `reason="daemon_shutdown"`; every other source (including absent)
     stays `reason="user_end"`. The trigger's subscription, starts,
     and policy are unchanged, so the topology fingerprint stays the
     same and every committed record replays identically. The trigger
     comment gains one line naming the mapping.
  2. **`_shutdown_all_sessions()`** in `substrate-ui/server.py`. For
     every registered session whose status is not `ended` or
     `interrupted`, injects `SessionEndRequested(session_id, source=
     "daemon_shutdown")` via `SessionRegistry.turn_sync` with a 10 s
     timeout. Sequential — parent-card wording is `wait up to 10s per
     session for graceful pause, then exit`. Best-effort per session:
     an exception on one session does not stop the loop; that
     session's record stays whatever `turn_sync` left it (parked or
     interrupted).
  3. **SIGTERM installer** in `main()`. `signal.signal(SIGTERM,
     handler)` where the handler calls `_shutdown_all_sessions()`
     then `srv.shutdown()` then `sys.exit(0)`. Idempotent —
     reentrancy from a second SIGTERM during shutdown is guarded by
     a threading.Event so the second signal is a no-op.

**What is deliberately out of scope.**

  - The subprocess-daemon end-to-end test (spawn daemon, SIGTERM it,
    assert exit code + record state on next boot). That harness is
    queued for a piece-B integration sprint (parent card 214's
    named subprocess harness sprint 214d). This sprint's tests
    exercise `_shutdown_all_sessions()` in-process against the real
    SessionRegistry + turn_sync, which is the same code path the
    signal handler runs.

## prerequisites

- Sprint 215a closed (POST /end proves the SessionEndRequested
  round-trip works).
- Sprint 215c closed (PATCH proves manifest mutation persists).

## artifact contract

### Files

- `substrate/src/substrate/topologies/session/__init__.py` — one-
  line change to the `end-on-user-end` input_builder + comment.
- `substrate-ui/server.py` — `_shutdown_all_sessions()` function;
  SIGTERM installer in `main()`.
- `substrate-ui/tests/test_server_daemon_shutdown.py` — new; ~4
  cases.
- `substrate/tests/test_session_topology_bundled.py` — regression
  check that the CI record still round-trips (the input_builder
  change is fingerprint-neutral, but the assertion pins it).

### Assertions

- `_shutdown_all_sessions()` on two parked sessions writes
  `SessionEnded{reason: "daemon_shutdown"}` to each record;
  `substrate.RunFinalised` follows each; both manifests transition
  to `"ended"`.
- An already-ended session is skipped (no second turn fired).
- A session whose `turn_sync` raises does not stop the loop; the
  other sessions still end cleanly.
- A boot_scan on a fresh SessionRegistry pointing at the same base
  dir sees `status="ended"` for the shutdown-ended sessions (not
  `"interrupted"`).
- The existing CI record for `session_topology` still round-trips
  bit-identically after the input_builder change (fingerprint
  unchanged).

### Command exit codes

- `uv run python -m pytest ../substrate-ui/tests/test_server_daemon_shutdown.py -q` exits 0.
- `uv run python -m pytest tests/test_session_topology_bundled.py -q` exits 0.
- Substrate-side full-suite regression clean (excluding the pre-
  existing `test_instrument_ablation_delta` real-model transience).
- Ruff clean.

## observation contract

In-process: create two sessions with `SessionRegistry.create`; fire
one /turn each so both have RunStarted + UserMessage + ModelReply +
Park on their records; call `_shutdown_all_sessions()`. Assert each
record's tail carries `SessionEnded{reason: "daemon_shutdown"}` and
`substrate.RunFinalised`. Reboot the registry against the same base
dir; `list_all()` shows both sessions at `status="ended"`.

## halt conditions

- `dual_contract_fail` if the CI record round-trip breaks after the
  input_builder change (would mean the topology fingerprint is
  fingerprint-sensitive to input_builder, contrary to the
  `TriggerReg` shape at `kernel/topology.py:97`).

## definition of done

SIGTERM path lands. Piece B daemon-side is: 214a-c (core endpoints
+ SSE) + 215a (POST /end) + 215c (PATCH) + 215d (SIGTERM). Sprint
215b (POST /interrupt) remains blocked on the substrate primitive.
Sprint 216 (queue cap + 410) inherits the five piece-B review
deferrals.
