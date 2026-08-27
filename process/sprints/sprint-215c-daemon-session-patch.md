# Sprint 215c — PATCH /api/session/<id> (driver + name)

```yaml
---
id: 215c
status: closed
phase: daily-driver-piece-B
pass_kind: functional
---
```

## scope

Third of four in the sprint 215 split. Sprint 215 as carded named
four concepts (POST /end, POST /interrupt, PATCH, SIGTERM); rule 6
said split. 215a shipped POST /end; 215b halted on
`substrate_primitive_missing` (see BLACKBOARD 2026-08-26). Sprint
215c ships PATCH for the fields that already live on
`SessionManifest` and are already honored by
`_build_session_topology_from_manifest`: `driver` and `name`.

**What sprint 215c ships.**

  1. **`PATCH /api/session/<id>`** at `substrate-ui/server.py`. Body:
     `{"driver"?: "kimi-k2.6:cloud", "name"?: "renamed"}`. Every
     absent key is left untouched. Returns the updated manifest
     shape: `{"session_id", "name", "driver", ...}`.
  2. **Persistence.** The `SessionRegistry` in-memory catalog and the
     on-disk `manifest.json` both update atomically:
     `SessionRegistry.set_driver` (new) mirrors the shape of
     `SessionRegistry.set_name` (sprint 211) — atomic-write via
     `_atomic_write_json`, catalog update inside a small critical
     section.
  3. **Rename** delegates to the existing `SessionRegistry.set_name`
     (sprint 211): 409 with `existing_session_id` on collision.
  4. **Next-turn effect.** `_build_session_topology_from_manifest`
     reads `manifest.driver` on every turn, so a PATCH before the
     next `Runtime.resume` fires means the next model turn runs
     against the new driver's Responder. No live-mid-turn swap; the
     current in-flight turn (if any) completes on its prior driver.

**What is deliberately out of scope.**

  - `tools` and `per_turn`. Both need `SessionManifest` schema
    growth. `tools` is currently constructed per turn from
    `full_suite(Path(manifest.workspace))` in
    `_build_session_topology_from_manifest`, so PATCHing tools means
    growing the manifest with a `tools: list[str] | None` field and
    changing the factory to filter `full_suite` by name. `per_turn`
    is currently hardcoded to `""`. Both belong in a later
    manifest-schema-growth sprint (215e or a piece-B follow-up),
    NOT here.

## prerequisites

- Sprint 215a closed.
- Sprint 211's `SessionRegistry.set_name` seam is the shape model.

## artifact contract

### Files

- `substrate-ui/session_registry.py` — new `SessionRegistry.set_driver`
  method. `set_name` unchanged; `PATCH` handler reuses it.
- `substrate-ui/server.py` — new `_session_patch` handler method;
  new `do_PATCH` method dispatching to it.
- `substrate-ui/tests/test_server_session_patch.py` — new; ~5 cases.

### Assertions

- `PATCH /api/session/<id> {"driver": "kimi-k2.6:cloud"}` returns
  200 with the updated manifest; `SessionRegistry.get(id).driver`
  equals the new value; the on-disk manifest.json carries it too.
- `PATCH /api/session/<id> {"name": "renamed"}` returns 200; the
  by-name index resolves the new name; the old name resolves to
  None.
- `PATCH` with a colliding name returns 409 with
  `existing_session_id` (same shape as POST /api/session).
- `PATCH` on unknown session_id returns 404.
- Empty body returns 400 (nothing to patch).
- Body with unknown fields (e.g., `tools`) returns 400 naming which
  fields are not yet PATCH-able.

### Command exit codes

- `uv run python -m pytest ../substrate-ui/tests/test_server_session_patch.py -q`
  exits 0.
- Substrate-side full-suite regression clean.
- Ruff clean.

## observation contract

Sprint 215c discharges the state-mutation contract for PATCH. In-
process: create a session with `driver=deterministic`; PATCH driver
to `claude`; assert `SessionRegistry.get(id).driver == "claude"`
and the on-disk manifest carries the new value. Restart the
in-memory `SessionRegistry` (fresh instance pointing at the same
base dir); boot_scan reads manifests; the driver survives the
restart.

## halt conditions

- `dual_contract_fail` if a PATCH driver value that
  `_daemon_driver_resolver` cannot resolve (an unknown model tag)
  lands and produces silent OllamaResponder fallback. The handler
  should validate the driver name against a small allowlist or
  hand it directly to the resolver at PATCH time; whichever shape
  is picked, the contract is: an invalid driver returns 400 at
  PATCH time, not a broken next-turn.

## definition of done

PATCH driver + name live. Sprint 215d (SIGTERM graceful shutdown)
is independent and may dispatch. Sprint 215b (POST /interrupt)
stays halted until substrate publishes the primitive.
