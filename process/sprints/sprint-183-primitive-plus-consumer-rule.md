# Sprint 183 — Add primitive-plus-consumer clause to WORKING_AGREEMENT (closes external round-2 R7)

---

```yaml
---
id: 183
status: closed
phase: 0
pass_kind: docs
---
```

## scope

Round-2 R7: three sprints (164 Budget, 170 RunUnpublishable, 172 Budget UserWarning) landed substrate primitives with zero live consumers in production paths at close. Each closed clean because the primitive's tests passed; each left the tree with surface area whose real-path correctness is untested. Sprint 170's runner wire waited five sprints for Sprint 177 to close the mirage.

Sprint 183 adds a dual-contract clause to `WORKING_AGREEMENT.md`: every sprint that lands a substrate primitive must EITHER wire a live production consumer in the same sprint OR name the sprint that will (card filed on disk, dispatched within one working session).

The rule lives under a new `## Primitive-plus-consumer discipline (Sprint 183, external round-2 R7)` section, inserted between the existing SWE-bench boundary section and the Vocabulary discipline overrides. Every existing sprint stays closed under its original discipline; the rule applies to sprints dispatching after ratification.

## files modified

- `process/WORKING_AGREEMENT.md` — new section added.

## contracts

- Doc-only change.
- The rule names two allowed shapes (in-sprint consumer OR named next-sprint consumer), a grace clause for kernel-enforcement splits (Sprint 164 → Sprint 165 shape), and what does NOT count as a consumer (tests, docs, `notes` mentions).
- Every future primitive sprint's `notes` section must satisfy the clause; a card failing to name a consumer trips at Architect review time.

## done

One file. Prevents R7's accumulation pattern from repeating.
