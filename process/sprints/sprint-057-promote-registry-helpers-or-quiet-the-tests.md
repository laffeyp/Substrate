# Sprint 057 — promote the private registry helpers, or stop patching them

```yaml
---
id: 057
status: open
phase: 7
pass_kind: hygiene
---
```

## Product-spec conformance

**Fulfills:** no product-spec clause directly. Discipline: an
underscore-prefixed name is a promise that no one outside the module
touches it. Substrate-ui tests reach for four private helpers plus the
`api` module handle on `session_registry`. Sprint 054's re-export shim
now formalises the leak by listing them in `__all__`. The shape works;
it lies about what is public.

**Consumes:** the shim substrate-ui/session_registry.py from sprint 054.

## Motivation

The leaked names, live count from `grep -rn "from session_registry import
_" substrate-ui/`:

- `_manifest_to_dict` — used by `test_session_manifest_survives_daemon_
  restart.py` to build fixtures the daemon writes to disk.
- `_manifest_from_dict` — same, read side.
- `_record_state` — used by `test_session_registry_first_turn_uses_run
  .py` to assert torn-record classification.
- `_scan_record_status` — same.
- `api` (module handle) — every torn-record test monkeypatches
  `sreg.api.read_record` to inject `RecordGapError`.

Two of the four helpers (`_scan_record_status`, `_manifest_from_dict`)
have legitimate public shape — they're read projections over on-disk
state, the same class as `read_record` or `narrate`. The other two
(`_manifest_to_dict`, `_record_state`) exist for test-fixture and
test-assertion convenience only. And the `api`-module patch is a test-
double, not a real consumer surface.

## Scope

Two decisions, one per helper class.

**Read projections (`_scan_record_status`, `_manifest_from_dict`):**
promote. Drop the underscore prefix. Add short docstrings that name
their role in the public shape (companion to `read_record` +
`narration_summary`). Re-export as public names from
`substrate.session_registry`; the shim re-exports them under the same
new name. Every test import becomes a public import; the semantics do
not change.

**Test-fixture helpers (`_manifest_to_dict`) and `_record_state`:**
keep private. Rewrite the two tests that reach for them:
- `_manifest_to_dict` — replace with a small test-side helper that
  writes a `SessionManifest` to disk via `_atomic_write_json` +
  `msgspec.to_builtins`. The pattern is 6 lines in the test file.
- `_record_state` — the test asserts torn/interrupted/ended
  classification. Replace with an assertion against
  `_scan_record_status` (now public) — same information, different
  shape. If the test genuinely needs the (state, cause) tuple, expose
  a public `session_state(record_root) -> (SessionStatus, cause)` on
  the registry.

**`api` monkeypatch:** unchanged. This is a real Python pattern —
patching a module attribute to inject a fault — and works cleanly
through the shim because module objects are singletons. Not a promote
question.

## Prerequisites

- Sprint 054 closed.

## Context files

- `src/substrate/session_registry.py` — the four helpers at their
  definition sites.
- `substrate-ui/session_registry.py` — the shim's `__all__`.
- `substrate-ui/tests/test_session_manifest_survives_daemon_restart.py`
  — `_manifest_to_dict` + `_scan_record_status` importers.
- `substrate-ui/tests/test_session_registry_first_turn_uses_run.py` —
  `_record_state` importer.
- `substrate-ui/tests/test_session_registry_boot_scan_preserves_ended
  .py` — `_scan_record_status` importer.

## Artifact contract → Files modified

- `src/substrate/session_registry.py` — rename `_scan_record_status`
  → `scan_record_status`, `_manifest_from_dict` → `manifest_from_dict`.
  Add one-line docstrings naming their role as read projections. Keep
  the old names as deprecated aliases for one sprint so any consumer
  the grep missed still resolves; log a `DeprecationWarning` on their
  use.
- `substrate-ui/session_registry.py` — shim exports the new public
  names; drops the deprecated ones from `__all__` (still resolvable
  by name, just not listed as sanctioned surface).
- Three substrate-ui tests updated: patch imports, replace the two
  `_record_state` call sites with `scan_record_status` reads OR a
  new `session_state` wrapper (pick per test).

## Signal contract → Emits

None (no new vocabulary; renames are non-behavioural).

## Observation contract

- Every substrate-ui test that imported the old private names still
  passes.
- `grep -rn "from session_registry import _" substrate-ui/` → zero
  hits for the two promoted names; the two kept-private names are
  gone from tests entirely.
- `substrate-ui/session_registry.py` `__all__` drops
  `_manifest_to_dict`, `_manifest_from_dict`, `_record_state`,
  `_scan_record_status`; adds the two public names.
- `DeprecationWarning` from the shim's deprecated aliases fires
  exactly zero times in a green test run (all consumers migrated).

## Halt conditions

- `bridge_mapping_required` if `_record_state` returns state the
  public `scan_record_status` cannot express (the cause tuple).
  Expose `session_state()` publicly, don't force callers into a
  lossy shape.
- `dual_contract_fail` if the deprecation-warning path fires on a
  substrate-ui test — means a consumer of the old name was missed;
  fix the caller.

## Definition of done

The two helpers with legitimate public shape are public. The two
that don't are still private and no test touches them. The shim's
`__all__` reads as a real public surface, not a leak sheet.

## Non-goals

- No behaviour change. Renames only, plus one small test-side helper
  where a test used `_manifest_to_dict` for fixture setup.
- Not touching the `api`-module monkeypatch shape — it's a legitimate
  test-double pattern.
