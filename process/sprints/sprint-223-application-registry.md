# Sprint 223 — application registry + manifest scan

```yaml
---
id: 223
status: closed
phase: daily-driver-piece-E
pass_kind: architecture
---
```

## scope

Author `substrate/src/substrate/topologies/applications/registry.py` with `load_manifests() -> dict[str, ApplicationSpec]`. Scans `topologies/applications/*.manifest.toml` via `importlib.resources.files` + `tomllib`. Returns `{name: ApplicationSpec(name, description, runs, inputs_schema, output_kind, default_bundle, slots)}`. Daemon (piece B) calls it at boot; exposes `GET /api/applications` returning the flat list.

## prerequisites

- Sprint 204 closed (piece 0 done). Independent of piece A.

## context_files

- `substrate/src/substrate/topologies/applications/__init__.py` — the existing aggregate; flat module shape.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §7.6 (flat `applications/*.manifest.toml` shape + roles-to-models binding via inputs schema).
- Python `tomllib` (stdlib since 3.11) — parse target.

## artifact contract

### Files

- `substrate/src/substrate/topologies/applications/registry.py` — new.
- `substrate-ui/server.py` — GET /api/applications hook + boot-time `load_manifests()` call.

### Assertions

- `load_manifests()` returns `{}` when no manifests exist; returns the parsed dict when they do.
- `ApplicationSpec` fields typed via msgspec Struct.
- `GET /api/applications` returns a JSON list of the parsed specs.

### Tests

- `test_application_registry_empty.py`
- `test_application_registry_parses_valid.py` (fixture manifest).
- `test_application_registry_rejects_malformed.py`.

## observation contract

Fire `GET /api/applications` against a daemon with three fixture manifests; assert three entries returned with correct fields.

## halt conditions

- `vocabulary_change_required` if the manifest schema needs a field not covered by round-6 §7.6.

## definition of done

Registry scans + loads. Sprint 224 (four shipped manifests + BUNDLED registration) can dispatch.
