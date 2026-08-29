# Sprint 238 — `list_bundles()` helper in `bundles.py`

```yaml
---
id: 238
status: closed
phase: 6
pass_kind: functional
---
```

## scope

Add a top-level `list_bundles(bundles_root: Path | None = None) -> list[Bundle]`
to `substrate/src/substrate/bundles.py`. Enumerates every shipped
bundle directory, loads each via `load_bundle`, returns the list
sorted by name.

Prerequisite for substrate-ui sprint 034a (`GET /api/bundles`
endpoint). Today's `bundles.py` has `_bundles_root`,
`_shipped_bundle_dir`, `load_bundle`, `resolve_extends`,
`assemble_seed`, `bind_slots` — verified by grep — but no top-level
enumerator; the daemon has no way to list bundles for the UI picker
(sprint 036b) without shelling out to the filesystem, which would
couple substrate-ui to substrate's internal layout.

One file. One concept.

## prerequisites

- Piece-H sprint 231 closed (default bundles shipped).

## context_files

- `substrate/src/substrate/bundles.py` — existing loaders; add the
  helper alongside them.
- `substrate/src/substrate/topologies/session/bundle/` — shipped
  bundles' home.
- `substrate/src/substrate/topologies/applications/*.bundle/` —
  application-bundle directories.

## artifact contract → Files created/modified

- `substrate/src/substrate/bundles.py` — new `list_bundles()` function.
  Walks `_bundles_root(bundles_root)` for every subdirectory
  containing a `bundle.toml`; calls `load_bundle(dirname)` per hit;
  returns the sorted list. Handles missing root gracefully (returns
  empty list, not raise).
- `substrate/tests/test_bundles_list.py` — new. Cases: enumerates
  the five default bundles from sprint 231; empty root returns empty
  list; sorted order is stable across runs.

## signal contract → Emits

None (pure helper).

## observation contract

- `uv run python -m pytest substrate/tests/test_bundles_list.py -v`
  green.
- `uv run python -c "from substrate.bundles import list_bundles; print([b.name for b in list_bundles()])"`
  returns the five default bundle names in sorted order.

## halt conditions

- `dual_contract_fail` if a shipped bundle directory fails to load
  (points at 231-side breakage that this sprint should not paper over
  — halt instead).

## definition of done

Helper exists; test green; command-line invocation lists the five
defaults. Substrate-ui sprint 034a cleared to dispatch.
