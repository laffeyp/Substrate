# Sprint 144 — confirmatory entrypoint; kill the second door script

---

```yaml
---
id: 144
status: pending
phase: swebench-close-the-loop
cadence_band: auto-within-phase
pass_kind: functional
---
```

---

## why

`scripts/assay_full_run.py:62` calls `Runtime(root).run(topo)` directly, bypassing `run_arm_on_case`. That's how the 108/291 run produced a `Counter` over `RepairSummary` outcomes instead of a `Report` with pass_hat_k, CIs, matched compute, and provenance. Kill the script; add one entrypoint that goes through the harness.

Deletion policy for this chain (roadmap §Deletion policy): the run's evidence stays (`process/assay_full/qwen3-coder_480b-cloud/` and `process/swebench-lite-full-qwen3coder480b-20260627.jsonl` — untouched); the tool that produced it goes. KIT_DIARY carries the last-live sha and the sprint that superseded it.

## scope

- Author `scripts/assay_swebench_confirmatory.py` — thin CLI that: loads instances → `prepare_swebench_case` for each → invokes `run_arm_on_case` per (arm, case, trial) → writes cells via the assay control plane. For this sprint: one arm (`swebench_repair_topology`), one model, one trial per case — the smoke slice; the arm matrix lands in Sprint 157.
- Delete `scripts/assay_full_run.py`.
- Append a KIT_DIARY entry naming the last-live sha and this sprint number.

## signal contract

### Emits

The topology's existing kinds (no new events).

### Invariants

- The new entrypoint touches the runtime only through `run_arm_on_case`.
- `assay_full_run.py` does not exist post-sprint.
- Run artifacts under `process/assay_full/` and `process/swebench-lite-full-qwen3coder480b-20260627.jsonl` are unchanged.

## artifact contract

### Files created

- `scripts/assay_swebench_confirmatory.py` — the new entrypoint.

### Files deleted

- `scripts/assay_full_run.py`.

### Files modified

- `process/KIT_DIARY.md` — append finding entry.

### Content assertions

- `scripts/assay_swebench_confirmatory.py` imports `run_arm_on_case`, not `Runtime` directly for the solver path.
- `git grep assay_full_run` returns zero hits (excluding `.git/`).

### Command exit codes

- `uv run ruff check scripts/assay_swebench_confirmatory.py` → 0
- `uv run mypy scripts/assay_swebench_confirmatory.py` → 0
- Smoke: `uv run python scripts/assay_swebench_confirmatory.py --limit 3 --model llama3.2:1b --arm swebench_repair --outdir process/assay_smoke_142/` → 0; produces per-case cells + a `Report`.
- `PATH="$PWD/.venv/bin:$PATH" uv run python -m pytest -q` → 0 (full suite; no test depends on `assay_full_run.py`).

## observation contract

`pass_kind: functional`. Behavior change: the tree has one solver entrypoint, not two.

### Input fixture

- 3-instance SWE-bench Lite slice (deterministic pick: first 3 alphabetically). Smoke run produces a JSON `Report` with per-arm `pass_hat_k`, non-zero `elapsed_ms` (via metered responder if `--model` is real), and `provenance_status=verified` on each cell.
- `git grep -r assay_full_run` from the repo root returns zero hits in tracked files.
