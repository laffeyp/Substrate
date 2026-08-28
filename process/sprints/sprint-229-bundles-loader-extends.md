# Sprint 229 — bundles.py loader + extends chain resolution

```yaml
---
id: 229
status: closed
phase: daily-driver-piece-H
pass_kind: architecture
---
```

## scope

Author `substrate/src/substrate/bundles.py`. Public API:

- `load_bundle(name) -> Bundle` — reads `~/.substrate/bundles/<name>/bundle.toml` + prose slots + corpus paths + retrieval config + tools allowlist. Handles file-or-folder shape at every prose slot: `methodology.md` OR `methodology/*.md` (concatenated in filename-sort order with `---` separators). `BundleShapeError` if both present at the same slot.
- `resolve_extends(name, seen=frozenset()) -> list[Bundle]` — C3 linearisation with cycle detection (`BundleCycleError`) and depth cap 8. Returns bundles in resolution order (base first).
- `assemble_seed(bundle, session_task="") -> str` — concat per TECH-SPEC §1.6.5 order: personality → resolved-extends methodologies → this bundle methodology → project context → session task → baseline.

`Bundle` = frozen msgspec Struct with `name, description, schema_version, extends, methodology, personality, per_turn, corpus_paths, retrieval_kind, tools_enabled`.

## prerequisites

- Sprint 210 closed (piece A — the seed feeds session_topology).

## context_files

- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §9 (`bundle.toml` shape + extends + slot handling) + §1.6.5 (seed assembly order).
- `substrate/src/substrate/kernel/topology.py` — reference for frozen-Struct pattern.
- Python `tomllib` (stdlib).

## artifact contract

### Files

- `substrate/src/substrate/bundles.py` — new.

### Assertions

- Bundle with only file slots loads. Bundle with only folder slots loads with correct concat order.
- Bundle with both `methodology.md` and `methodology/` → `BundleShapeError` with message naming the slot.
- Cyclic extends → `BundleCycleError` naming the cycle path.
- Extends chain depth > 8 → `BundleChainTooDeepError`.
- Diamond extends → first-occurrence-wins per C3.
- `assemble_seed` order matches §1.6.5.

### Tests

- `test_bundle_load_and_assemble.py`
- `test_bundle_extends_composition.py`
- `test_bundle_extends_cycle.py`
- `test_bundle_extends_diamond.py`
- `test_bundle_shape_error.py`
- `test_bundle_folder_slot.py`
- `test_bundle_extends_depth_cap.py`

## observation contract

Fixture bundle `team-review` that extends `code-review`; `assemble_seed` produces text with personality first, code-review methodology, then team-review methodology, in that order. Byte-compared against a committed expected.txt.

## halt conditions

- `bridge_mapping_required` if `tomllib` or msgspec need mapping (both stdlib-or-already-in-tree; not likely).

## definition of done

Loader + extends + assembler work. Sprint 230 (slot binding) can dispatch.
