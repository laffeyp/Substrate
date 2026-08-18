# Sprint 187 — `swebench_repair_topology` dual-mode default responders (roadmap v2 S2, part 1 of 2)

---

```yaml
---
id: 187
status: closed
phase: 1
pass_kind: functional
---
```

## scope

Roadmap v2 § "Sprint 2" says the repair topology gains dual-mode + bundled.py registration + a committed CI record. Sprint 187 lands the dual-mode piece — `responders: list[Responder] | None = None`; when None, defaults to `[DeterministicResponder(seed=i) for i in range(n)]`. Matches the pattern every other bundled topology uses per `docs/adding-a-topology.md`. Existing callers passing an explicit responders list behave identically.

Bundled-registration + CI-record commit is Sprint 188 (roadmap v2 S2, part 2 of 2) — the fixture-repo factory needs a deterministic on-disk path, which is real work worth its own sprint card. Sprint 188 card filed on disk per the Sprint 183 primitive-plus-consumer discipline before Sprint 187 closes.

## files modified

- `src/substrate/topologies/swebench_solver/assemble.py` — `responders` typed `list[Responder] | None`, defaults to None; when None, populated with `DeterministicResponder(seed=i)` per slot before the topo builds. Docstring extended.

## files created

- `tests/test_swebench_repair_topology_dual_mode.py` — two substance tests:
  1. `responders=None` runs against deterministic defaults and produces `RepairSummary` on the record.
  2. Explicit `responders=[...]` still works — preserves the pre-Sprint-187 contract.

## contracts

- 2/2 tests pass; ruff clean; mypy strict clean.
- 20 broader swebench tests still pass (test_swebench_solver, test_assay_swebench_suite, test_assay_swebench_matrix).
- Every existing production caller (matrix arms via `_build_solver_arm_from_payload`; the deprecated heavy topology's callers) passes an explicit responders list — Sprint 187 does not change their behavior.

## primitive-plus-consumer discipline (Sprint 183 rule)

- **Primitive.** The optional `responders` parameter.
- **In-sprint consumer.** The new substance test at `tests/test_swebench_repair_topology_dual_mode.py`. Tests do not count under Sprint 183's rule.
- **Named next-sprint consumer.** Sprint 188 (roadmap v2 S2, part 2 of 2): bundled-registration and CI-record commit. Card filed at `process/sprints/sprint-188-swebench-repair-bundled-registration.md` before Sprint 187 closes.

## done

Two files (one modified, one new). Dual-mode landed. Sprint 188 queued for the bundled registration + CI record.
