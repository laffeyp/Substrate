# Sprint 055 — SessionRegistry auto-hydrates, or warns loudly

```yaml
---
id: 055
status: open
phase: 7
pass_kind: correctness
---
```

## Product-spec conformance

**Fulfills:** the same discipline that closed sprint 050's
`record_root=None` warning — a default that is also a load-bearing
precondition must either be safe or fail loud. Product spec §6 says a
standing sub-agent's manifest at `~/.substrate/sessions/<id>/manifest.
json` "survives daemon restart"; the substrate side must not require
callers to know a magic method call is what makes that survival real.

**Consumes:** the `SessionRegistry` class moved into substrate by
sprint 054. No new dependencies.

## Motivation

Post-054 audit surfaced the pattern (KIT_DIARY finding 39 recurrence).
Constructing `SessionRegistry(base=<existing manifests>,
session_topology_factory=…)` returns an EMPTY in-memory catalog. The
on-disk state is intact but `reg.by_name("existing")` returns `None`,
`reg.list_all()` returns `[]`, and `reg.get("s_existing")` returns
`None`. A caller who does not know to call `reg.boot_scan()` treats
the base as empty and either creates a duplicate session or reports
"no sessions found" incorrectly.

Every production caller (substrate-ui/server.py:2819) calls
`boot_scan()` at startup. That works because someone knew the pattern.
A fresh caller — a CLI, an MCP client, a test author — gets a silent
bug. Sprint 054's own Phase A unit test hit exactly this and had to be
patched.

## Scope

One of the two: auto-hydrate at construction, or warn at first access.

**Option 1 (preferred).** `SessionRegistry.__init__` calls
`self.boot_scan()` at the end. `boot_scan` becomes idempotent (it
already is — repeated calls re-read disk and repopulate the same
dict). Callers who want the current explicit-boot shape pass
`auto_boot=False` and call it themselves.

**Option 2 (fallback if Option 1 has a side-effect issue).**
`__init__` sets `self._hydrated = False`; every public read method
(`by_name`, `get`, `list_all`, `list_children`) checks the flag and
calls `boot_scan()` on first read, one-time. Failure of that first
scan warns loudly and marks hydrated so the warning fires only once.

Halt-and-articulate if Option 1 turns out to have hidden coupling: the
existing substrate-ui daemon startup runs `boot_scan` BEFORE binding
the HTTP handlers, so the daemon expects a specific ordering
(`SessionRegistry(...)` → adjust config → `boot_scan()` → serve).
Audit that path first. If the daemon truly needs a beat between
construction and hydration, Option 2 is the right call.

## Prerequisites

- Sprint 054 closed (SessionRegistry lives in substrate).

## Context files

- `src/substrate/session_registry.py` — `__init__` at ~L245, `boot_scan`
  at ~L298. Public read methods at `by_name` (~L654), `get` (~L657),
  `list_all` (~L660), `list_children` (~L663).
- `substrate-ui/server.py:2805-2820` — the current construct-then-scan
  sequence; audit for hidden ordering dependencies.
- `tests/test_session_registry_core.py::test_registry_survives_a_fresh_
  instance_at_same_base` — the test that hit this class of bug.
  Update after the fix so the assertion no longer needs the manual
  `reg2.boot_scan()` call.

## Artifact contract → Files modified

- `src/substrate/session_registry.py` — one edit at `__init__` (Option
  1) or on every read method (Option 2). Add `auto_boot: bool = True`
  kwarg for callers who want the old shape.
- `tests/test_session_registry_core.py` — drop the manual `boot_scan()`
  from the survival test; add an explicit `auto_boot=False` test that
  proves the opt-out still works.
- `substrate-ui/server.py:2819` — if Option 1, delete the redundant
  `boot_scan()` call (kept for backward-compat but no-op after the
  constructor already scanned). Comment naming the sprint keeps the
  intent legible for anyone reading blame.

## Signal contract → Emits

None. Mechanism-level correctness fix, no new tags.

## Observation contract

- `tests/test_session_registry_core.py` — the survival test passes
  WITHOUT the manual `boot_scan()`.
- New test `test_registry_auto_boot_can_be_opted_out` — constructing
  with `auto_boot=False` reproduces the empty-catalog behaviour;
  explicit `boot_scan()` still hydrates.
- New test `test_registry_manual_boot_stays_supported` — the Option 1
  no-op case: after auto-hydration, calling `boot_scan()` again is
  safe and returns the same result.
- Every existing substrate-ui test still green (the shim's re-exports
  do not change; the substrate-ui server still calls `boot_scan()`
  and it stays a no-op).

## Halt conditions

- `spec_ambiguity` if Option 1's construction-time I/O turns out to
  clash with the daemon's expected ordering (config adjustments
  between construct and hydrate). Fall back to Option 2.
- `bridge_mapping_required` if any consumer relies on the empty-
  catalog behaviour immediately post-construction (grep at start of
  work). Should not exist; audit anyway.

## Definition of done

A caller who writes `SessionRegistry(base=…, session_topology_factory
=…)` gets a registry that already reflects on-disk state. Explicit
opt-out preserved via `auto_boot=False`. The load-bearing precondition
becomes visible at the seam, not hidden behind knowledge no docstring
carries.
