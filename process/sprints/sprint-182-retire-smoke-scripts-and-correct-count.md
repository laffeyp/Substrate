# Sprint 182 — Retire heavy-topology satellite smokes + correct Sprint 173 count (closes R6)

---

```yaml
---
id: 182
status: closed
phase: 1
pass_kind: functional
---
```

## scope

Round-2 R6: Sprint 173 close-note reported "three scripts still importing the heavy topology"; grep on the tree shows three direct imports (`flask_solve.py`, `solve_instance.py`, `assay_swebench_run.py`) plus two satellite imports (`docker_runner_smoke.py`, `regression_seam_smoke.py`) — five files reaching the retired topology's world. Round-2 R6 flagged a different count (four) and named different files; both round-1 and round-2 counts were partial. Sprint 182 retires the two satellite-importing smoke scripts to `scripts/_deprecated/` per hard rule 12 and corrects the running count.

## files moved

- `scripts/docker_runner_smoke.py` → `scripts/_deprecated/docker_runner_smoke.py` (via `git mv`, body preserved)
- `scripts/regression_seam_smoke.py` → `scripts/_deprecated/regression_seam_smoke.py` (via `git mv`, body preserved)

## files created

- `scripts/_deprecated/README.md` — names each retired script, its revival path, and Sprint 182's count correction. First inhabitant of `scripts/_deprecated/`; Sprint 175's CI guard fails on any commit deleting a file under this directory.

## why these two and not all five

- `docker_runner_smoke.py` and `regression_seam_smoke.py` exercise satellite modules of the retired heavy topology (`select_docker`, `select_exec`, `select_regression`). Neither test path is on any confirmatory route under the design-v3 revert. Retire cleanly.
- `flask_solve.py`, `solve_instance.py`, `assay_swebench_run.py` remain in `scripts/` as legacy reproduction/debug utilities. They still work against the deprecated topology (which itself remains in-tree with a `DeprecationWarning` and the `_deprecated/README.md` at the topology level). A follow-on sprint may migrate them to `swebench_repair_topology` or retire them under the same discipline; Sprint 182 does not touch them because the migration would strip most of their observable behavior (they were built around the heavy topology's shape).

## contracts

- `scripts/_deprecated/` is the first `_deprecated/` under `scripts/`; Sprint 175's `check_deprecated_preserved.sh` guard covers it.
- No test suite change — the retired smokes were not on any test path.
- The `_deprecated/README.md` documents the round-2 R6 count correction so a later reviewer inherits the truthful shape without opening this sprint card.

## done

Two moves + one README + a count correction filed in the README rather than by editing Sprint 173's closed card (no in-place edits). The retirement follows the same shape KIT_DIARY 38 named for the heavy topology itself.
