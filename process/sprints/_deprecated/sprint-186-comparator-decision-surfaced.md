# Sprint 186 — Surface R2 comparator decision for Architect ruling

---

```yaml
---
id: 186
status: pending
phase: 0
pass_kind: docs
---
```

## scope

Round-2 R2: the equivalence comparator pinned in `docs/preregistrations/2026-08-swebench-lite.preg.json` is Agentless + GPT-4o = 27.8% resolve on Lite (Xia et al. 2024). Substrate has never run Agentless. The comparator is a number produced elsewhere on a different codebase, a different harness pin, a different environment. Any environmental shift is a confound the equivalence math cannot see.

Sprint 186 is a HALT sprint, not an implementation sprint. It surfaces the decision to `## Surfaced for review` and names the two Architect-callable options. The next sprint dispatches after the Architect rules.

## the decision

**Option (a): run Agentless on this substrate.** Install Agentless, run against the same 300 Lite instances with the same swebench harness pin the confirmatory uses, capture its resolve rate as the comparator. Pin THAT number in the pre-reg. The equivalence math then compares like-to-like. Cost: several days of Docker + GPT-4o token spend + integration work to wire Agentless into a callable script that respects the same harness invocation. Benefit: a comparator that defends without a paper citation.

**Option (b): drop the external-comparator claim.** Reframe the confirmatory as within-substrate comparisons only (single_draft_baseline vs n_drafts_no_correction vs n_drafts_repair vs n_drafts_repair_ensemble vs baseline_matched_compute). The equivalence claim becomes "the ensemble beats the compute-matched single-model baseline by δ or does not." No external comparator; no equivalence-to-published-SoTA framing. Cost: loses the "equivalent to Agentless + GPT-4o" headline. Benefit: honest, smaller, ready to fire when the boundary producers land.

## Architect ruling required

The decision is not a bug to close mechanically. It rests on: how much the "equivalence to Agentless" framing matters for the substrate story vs how much the days of Agentless-integration work matter for shipping the confirmatory soon. Both options have honest engineering behind them; neither is obviously right.

## files created

- `process/sprints/sprint-186-comparator-decision-surfaced.md` — this card. Status stays `pending` until the Architect rules.

## contracts

- No code change.
- BLACKBOARD entry names the decision and asks for the ruling.
- The next sprint (187 or later, per the ruling) dispatches only after `## Decisions` carries the Architect's call.

## what does not happen without the ruling

- The Pass-1 pre-registration (`docs/preregistrations/2026-08-swebench-verified.preg.json`) does not freeze. Design v3 § S10 says freeze the pre-reg before firing; the comparator field is one of the required fields.
- The paper's argument (currently marked as position, not authority) does not update.
- The two-option roadmap-v2 sprint sequencing waits.

## done

The halt surfaced. The card is on disk with `status: pending`. The BLACKBOARD entry names the decision. Sprint 187+ dispatches after the ruling.
