# Sprint 073 — boundary-validator sweep + `ListTarget` declaration

```yaml
---
id: 073
status: closed
phase: 9
pass_kind: string-discipline
closed_at: 2026-09-02
closed_by: substrate main HEAD after this card
scope_note: `ListTarget(StrEnum)` declared in `src/substrate/cli.py`; `/list` argv routed through `ListTarget(raw)` at the CLI seam and dispatched on enum members. `DriverParamKey` members keyed the `allowed` dict in `session_registry.set_driver_params`; every downstream `if key == "..."` predicate migrated to `key_enum is DriverParamKey.<MEMBER>`. `DriverFamily(raw)` seated at three seam sites in `substrate-ui/server.py`: `_daemon_driver_resolver` (line 176), `_responder_for` (line 518, now with an explicit ValueError naming the offending value), the two `model == "ollama"` querystring dispatches at lines 2101 and 2234. Gates: ruff format + ruff check + mypy --strict all green; 1182 pass / 5 skip / 11 deselect on the full pytest run. The two red lines (`test_grep_finds_pattern_in_workspace`, `test_list_records_read_back_by_model`) reproduce on baseline HEAD with the sprint stashed — pre-existing real-model flakes in llama3.2:1b's tool-argument shape, unrelated to string-literal discipline.
---
```

## Product-spec conformance

**Fulfills:** the last leg of the string-literal discipline arc. Sprint 070 declared the closed-set StrEnum classes; sprint 071 handled producer/trigger constants; sprint 072 handled tool names. This card sweeps the three deferred boundary-validation sites.

## Scope

Three sweeps.

**1. `ListTarget(StrEnum)` in `cli.py`** — declare the enum; sweep `cli.py:1154-1182`'s string switch to validate the argv value via `ListTarget(raw)` at the top of the CLI handler and dispatch on the enum members.

**2. `DriverFamily` boundary validation in `substrate-ui/server.py`** — every daemon handler that reads `body["driver"]` as a family classification validates via `DriverFamily(raw)` at the top. Substrate-ui is TypeScript on the frontend and Python on the server side; the Python server file gets the sweep. Concretely: `substrate-ui/server.py:176, 518, 2101, 2234` — every `if name == "deterministic"` / `if model == "ollama"` predicate resolves through the enum.

**3. `DriverParamKey` in `session_registry::set_driver_params`** — the `allowed` dict at `session_registry.py:572` migrates from raw-string keys to `DriverParamKey` members; each `if key == "think"` etc. below migrates.

## Files modified

- `src/substrate/cli.py` — new `ListTarget(StrEnum)`; sweep of the list-target dispatch.
- `substrate-ui/server.py` — DriverFamily validation at each seam.
- `src/substrate/session_registry.py` — DriverParamKey use in the driver_params validator.
- Tests for ListTarget round-trip; existing session_registry tests should stay green since the wire strings are unchanged.

## Observation contract

- Full suite green.
- CLI test: invalid list-target argv value produces a non-zero exit with the offending value named.
- session_registry tests still green.

## Definition of done

Every external string that enters substrate through the daemon or CLI is validated to a typed value at the seam. Downstream signatures use the typed value. The three deferred drift classes from sprint 072 all have named-symbol homes and validators.
