# Sprint 230 — bundle slot declaration + binding + fallback algorithm

```yaml
---
id: 230
status: pending
phase: daily-driver-piece-H
pass_kind: architecture
---
```

## scope

Grow `bundles.py` (from sprint 229) + `applications/registry.py` (from sprint 223) with the slot declaration + binding + fallback per TECH-SPEC §9. Every topology's `manifest.toml` may declare a `[slots]` block: `rubric = { kind = "prose", required = false, default = "bundle:methodology" }` (kinds: `prose`, `line`, `bool`, `int`, `choice`; default: literal | `"bundle:<field>"` | `"none"`). At `run_topology(name, inputs, bundle=<dict>)` dispatch, `bind_slots(name, bundle) -> dict` merges caller values, falls back to defaults (looking up bundle fields where declared), raises `SlotUnfilledError` on missing required.

## prerequisites

- Sprint 229 closed.
- Sprint 223 closed (application registry — reads `[slots]` from manifest).

## context_files

- Sprint 229 output: `bundles.py`.
- Sprint 223 output: `applications/registry.py`.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §9 (slot declaration + binding).

## artifact contract

### Files

- `substrate/src/substrate/bundles.py` — new `bind_slots(topology_name, caller_bundle_dict) -> dict`.
- `substrate/src/substrate/topologies/applications/registry.py` — grow `ApplicationSpec` with `slots: dict[str, SlotSpec]`.

### Assertions

- Caller value overrides default: `bind_slots("code_review", {rubric: "..."})` → `resolved["rubric"] == caller value`.
- `default = "bundle:methodology"` falls back to `default_bundle.methodology`.
- `default = "none"` + `required = true` → `SlotUnfilledError` at `run_topology` dispatch → typed `ToolResult(ok=false)`.
- `default = "none"` + `required = false` → resolved value is `None`.
- Literal default (`false`, `5`, `"you"`) → resolved value is the literal.

### Tests

- `test_bundle_slot_binding_caller_wins.py`
- `test_bundle_slot_binding_default_bundle_fallback.py`
- `test_bundle_slot_binding_literal_default.py`
- `test_bundle_slot_missing_required_raises.py`

## observation contract

Session model calls `run_topology("code_review", inputs={diff: "..."}, bundle={rubric: "focus on auth changes"})`. `bind_slots` merges: `rubric` from caller, other slots from `code_review.bundle/`. The child topology receives all slots resolved.

## halt conditions

- `dual_contract_fail` if binding leaks a missing required as a silent `None`.

## definition of done

Slot binding works four ways (caller wins, bundle fallback, literal default, none-required-raises). Sprint 231 (default bundles) can dispatch.
