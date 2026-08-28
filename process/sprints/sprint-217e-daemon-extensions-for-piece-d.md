# Sprint 217e — daemon extensions prerequisite to piece D

```yaml
---
id: 217e
status: pending
phase: daily-driver-piece-B-to-D-bridge
pass_kind: architecture
---
```

## scope

Three small extensions to the daemon that piece D's slash router and REPL depend on. None ship a new endpoint; each extends an existing one within its documented shape.

**1. PATCH accepts `tools`.** Sprint 215c shipped PATCH `{driver, name}` and returned 400 for `tools`, `per_turn`, `workspace`, `workspace_shape`, `bundle`, `seed`. Tech spec §4 lists `{driver?, tools?, per_turn?}` as the PATCH body; §6's `/tools <list>` slash needs `tools` accepted. This card promotes `tools` from `_NOT_YET` to `_PATCHABLE`. `SessionRegistry.set_tools(session_id, tools)` writes the tool allow-list to a new manifest field (`SessionManifest.tools: tuple[str, ...] | None`); `_build_session_topology_from_manifest` reads it and constructs the topology with `tools=full_suite(...)` filtered by the allow-list (empty allow-list means full_suite). One-turn latency — next `Runtime.resume` sees the new set. `per_turn`, `workspace`, `workspace_shape`, `bundle`, `seed` stay in `_NOT_YET` (piece H / piece E for later).

**2. POST /turn body accepts `context`.** Tech spec §4 lists `POST /api/session/<id>/turn` request as `{"text": "...", "context": {...}?}`. Today `_session_turn` reads `text` only. This card parses `context` when present, validates its shape (`{parent_seq_range: [int, int], kinds: [str, ...]}`), forwards it into the `resume_event_builder` closure, which extracts the parent-record slice via the existing `delegate._extract_context_slice` helper and prefixes the extracted text to `UserMessage.assembled_prompt`. `UserMessage.text` stays as the raw user text; `assembled_prompt` grows the prefix. The topology's model producer already reads `assembled_prompt` (session/__init__.py:184).

**3. UDS transport alongside TCP.** Tech spec §6 says every CLI verb POSTs to `~/.substrate/daemon.sock` (UDS) with fallback to TCP. Today the daemon binds TCP `127.0.0.1:8765` only. This card adds a UDS listener sharing the same `Handler` class via a second server (`socketserver.UnixStreamServer` under the same `ThreadingHTTPServer` bases). Both listen simultaneously; the CLI tries UDS first and falls back to TCP. Existing tests keep hitting TCP; new tests hit UDS.

## prerequisites

- Piece B closed (sprints 214a-217d).

## context_files

- `substrate-ui/server.py:1489-1520` — `_PATCHABLE`, `_NOT_YET`, PATCH handler.
- `substrate-ui/server.py:770-820` — `_session_turn` and its `resume_event_builder`.
- `substrate-ui/server.py:314-316,1776` — TCP bind + `ThreadingHTTPServer` construction.
- `substrate-ui/session_registry.py:275-320` — `set_name`, `set_driver` shape to mirror for `set_tools`.
- `substrate/src/substrate/topologies/tool_loop/delegate.py:191-241` — `_extract_context_slice` (reused for /turn context).
- `substrate/src/substrate/topologies/session/__init__.py:180-190` — `_model_factory` reads `assembled_prompt`.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §4 body shapes; §6 transport section.

## signal contract

### Emits

- None new. All three extensions ride existing envelopes.

### Consumes

- `substrate-ui/session_registry.py` — new `set_tools` method; `SessionManifest` grows `tools` field.
- `substrate-ui/server.py` — PATCH handler admits `tools`; `_session_turn` parses `context`; `main()` binds UDS alongside TCP.

### Invariants

- Existing PATCH body `{driver}` or `{name}` unchanged.
- Existing POST /turn body `{text}` unchanged.
- Existing TCP endpoint at `127.0.0.1:8765` unchanged.
- `SessionManifest.tools: tuple[str, ...] | None = None` — default None means "no restriction" (topology uses full_suite).
- Context slice cap of 8 KiB per delegate's `_CONTEXT_SLICE_CAP_BYTES`.

## artifact contract

### Files created

- `substrate-ui/tests/test_server_session_patch_tools.py` — 4 cases: PATCH tools lands on manifest; next turn sees the restricted suite; empty list means full suite; malformed list returns 400.
- `substrate-ui/tests/test_server_session_turn_context.py` — 4 cases: context={} passes through; context with seq range prefixes assembled_prompt; malformed context returns 400; missing parent record fails cleanly.
- `substrate-ui/tests/test_server_uds_transport.py` — 3 cases: UDS socket created at boot; POST /api/session over UDS succeeds; TCP still works.

### Files modified

- `substrate-ui/session_registry.py` — `SessionManifest.tools` field; `set_tools(session_id, tools)` method mirroring `set_driver`; `_manifest_from_dict` / `_manifest_to_dict` round-trip `tools`.
- `substrate-ui/server.py` — `_PATCHABLE` gains `"tools"`; PATCH handler validates + calls `set_tools`; `_build_session_topology_from_manifest` reads `manifest.tools` and filters `full_suite`; `_session_turn` parses `context` from the body, threads it through the closure, prefixes `assembled_prompt`; `main()` spawns a second `ThreadingHTTPServer` bound to UDS at `~/.substrate/daemon.sock`, sharing the same `Handler`.

### Content assertions

- `grep '"tools"' substrate-ui/server.py` shows tools inside `_PATCHABLE` and no longer inside `_NOT_YET`.
- `grep 'set_tools\|SessionManifest.tools' substrate-ui/session_registry.py` shows the new method + field.
- `grep 'UnixStreamServer\|daemon.sock' substrate-ui/server.py` shows UDS bind.
- `SessionManifest.tools` round-trips through `_manifest_from_dict` and `_manifest_to_dict`.

### Command exit codes

- `cd substrate && uv run python -m pytest ../substrate-ui/tests/test_server_session_patch_tools.py ../substrate-ui/tests/test_server_session_turn_context.py ../substrate-ui/tests/test_server_uds_transport.py -q` exits 0 (11 cases).
- Full substrate-ui suite exits 0.
- Ruff clean.

## observation contract

Not applicable (small endpoint extensions; record-level tests cover behavior).

## halt conditions

- `substrate_primitive_missing` — none expected; every extension uses existing primitives.
- `dual_contract_fail` — if PATCH tools does not persist across `Runtime.resume` calls, or the context slice does not appear in the model's assembled_prompt.

## definition of done

PATCH accepts tools; POST /turn accepts context; UDS listener bound alongside TCP. Piece D dispatch cards (218 onward) can proceed without daemon-side drift.
