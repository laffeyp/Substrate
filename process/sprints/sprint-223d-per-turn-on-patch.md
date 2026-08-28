# Sprint 223d — `per_turn` on PATCH /api/session/<id>

```yaml
---
id: 223d
status: closed
phase: piece-B-gap-fill
pass_kind: functional
---
```

## scope

TECH-SPEC §7 line 656 declares `PATCH /api/session/<id> {driver?, tools?,
per_turn?}`. Sprint 217e wired `driver` and `tools`; `per_turn` still
lives in `_NOT_YET` and PATCH rejects it with 400. This card wires the
field through — the manifest carries the string; the session topology
builder (`_build_session_topology_from_manifest`) prefixes it to every
UserMessage.assembled_prompt per §7b (`per_turn.md`).

`per_turn` is one string; folder shape (§7b `per-turn/*.md` concatenation)
belongs to a later card if it lands at all.

## prerequisites

- Sprint 217e closed (PATCH wiring pattern in place).

## artifact contract

### Files

- `substrate-ui/session_registry.py` — `SessionManifest.per_turn: str = ""`
  field; round-trip in `_manifest_to_dict`/`_manifest_from_dict`;
  `set_per_turn(session_id, text: str)`.
- `substrate-ui/server.py` — move `per_turn` from `_NOT_YET` to
  `_PATCHABLE`; validate as string; `_build_session_topology_from_manifest`
  reads `manifest.per_turn` and passes into the session topology's
  `per_turn` kwarg (already accepted by the topology per spec §5 line 402).

### Assertions

- PATCH with `{"per_turn": "Think step by step."}` returns 200 and
  manifest.json carries the string.
- Next `/turn` produces a UserMessage whose `assembled_prompt` starts with
  the per_turn text.
- PATCH with `per_turn: null` clears the string to `""`.
- PATCH with `per_turn: 42` returns 400.
- `boot_scan` preserves `per_turn` across daemon restart.

### Tests

- `substrate-ui/tests/test_server_session_patch_per_turn.py` — five cases:
  set string, prefix appears on next turn, clear via null, invalid type
  → 400, survives reboot.

## observation contract

`curl -X PATCH /api/session/<id> -d '{"per_turn":"Say hello first."}'`
returns 200; the next `/turn`'s UserMessage on the record includes the
prefix in `assembled_prompt`.

## halt conditions

- `dual_contract_fail` if the manifest carries `per_turn` but the topology
  does not honor it on the next turn.
- `vocabulary_change_required` if the session-topology signature needs a
  new field beyond `per_turn: str`.
## signal contract

Emits: (none — daemon PATCH + assembled_prompt prefix — no runtime emit sites).

