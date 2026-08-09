# Sprint 146 — dead-runner sweep

---

```yaml
---
id: 146
status: pending
phase: swebench-close-the-loop
cadence_band: auto-within-phase
pass_kind: functional
---
```

---

## why

The deletion policy from the roadmap (§Deletion policy for this chain): superseded runners get deleted, run artifacts stay. Sprint 144 kills `assay_full_run.py` because it's superseded by the confirmatory entrypoint. Same principle applies to sibling scripts left over from the same era. Candidates named in the roadmap: `scripts/swebench_smoke.py`, `scripts/assay_swebench_smoke.py`, `scripts/assay_agent_debug.py`. Any script in `scripts/` with zero live callers whose function is now covered by the new path also goes.

## scope

- `git grep` every `.py` under `scripts/` from repo root, excluding `.git/`.
- For each script with zero live callers (no import, no reference in docs, no invocation in CI, no invocation in another script), confirm supersession by the new entrypoint or by a test that covers the same ground.
- Delete the confirmed-dead scripts.
- One consolidated `process/KIT_DIARY.md` entry names each deleted script, its last-live sha, and the sprint that superseded it.

## the check before each deletion

For each candidate script `X.py`:
1. `git grep "X" -- ':!.git'` — must return zero hits outside the script itself.
2. `grep -r "X" .github/workflows/` — must return zero.
3. `grep -r "X" docs/ process/` — hits allowed only in the KIT_DIARY entries that already narrate the script (audit trail; leave).
4. If any of the above hit unexpectedly, the script stays and the sprint's disposition notes why.

## signal contract

### Emits

No events. Static sweep.

### Invariants

- Every deletion has a `git grep` proof of zero callers, captured in the KIT_DIARY entry.
- No `process/*.jsonl` or `process/assay_*/` artifact is touched. Evidence stays.

## artifact contract

### Files deleted

- Enumerated in the KIT_DIARY entry. Candidates: `scripts/swebench_smoke.py`, `scripts/assay_swebench_smoke.py`, `scripts/assay_agent_debug.py`; final list produced by the sweep, not the sprint card.

### Files modified

- `process/KIT_DIARY.md` — one appended entry with the enumeration.

### Content assertions

- `git grep` for each deleted script name returns zero hits in tracked files (excluding the KIT_DIARY entry itself).
- CI workflows do not reference deleted scripts.

### Command exit codes

- `uv run ruff check scripts/` → 0
- `PATH="$PWD/.venv/bin:$PATH" uv run python -m pytest -q` → 0 (full suite; nothing was depending on the deleted scripts)

## observation contract

`pass_kind: functional`. Behavior change: `scripts/` has fewer files; the reader hits the confirmatory entrypoint first.

### Input fixture

- Post-sweep `ls scripts/*.py | wc -l` returns a smaller number than pre-sweep, and the diff exactly matches the KIT_DIARY entry's enumeration.
- The confirmatory smoke command from Sprint 144 still returns 0.
