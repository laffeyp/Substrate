# Sprint 239 — `substrate/process/signals/current.json` symlink

```yaml
---
id: 239
status: pending
phase: 6
pass_kind: docs
---
```

## scope

Add `substrate/process/signals/current.json` as a symlink to the
highest-versioned vocabulary file in the same directory. Document the
convention in `substrate/process/WORKING_AGREEMENT.md`'s canonical
home registry.

Companion to substrate-ui sprint 033a — the ui-side syncer wants to
follow a single stable pointer instead of hard-coding version numbers.
Per REVIEW-2026-08-28 G8: a lookup surface every downstream reader
uses IS a contract change, however small; it gets its own card so
future removal or shape change goes through the same discipline.

Two files (one symlink, one doc). One concept.

## prerequisites

- None.

## context_files

- `substrate/process/signals/` — versioned vocab files
  (0.1.json, 0.2.json, 0.3.json as of this writing).
- `substrate/process/WORKING_AGREEMENT.md` — canonical home registry.

## artifact contract → Files created/modified

- `substrate/process/signals/current.json` — new symlink → the
  highest-versioned vocab file present (0.3.json today).
- `substrate/process/WORKING_AGREEMENT.md` — new row in the canonical
  home registry:
  `| signals/current.json | symlink → highest committed signals/<version>.json; bumped when a new version locks |`.

## signal contract → Emits

None (docs sprint).

## observation contract

- `readlink substrate/process/signals/current.json` prints the
  highest-versioned filename in the directory.
- `python -c "import json; d = json.load(open('substrate/process/signals/current.json')); print(d['vocabulary_version'])"`
  prints the version this points at.
- `substrate/process/WORKING_AGREEMENT.md` contains the new registry
  row.

## halt conditions

- `dual_contract_fail` if the symlink target does not exist or is not
  the highest-versioned file.

## definition of done

Symlink on disk; registry row on disk; both readable. substrate-ui
sprint 033a cleared to consume the pointer.
