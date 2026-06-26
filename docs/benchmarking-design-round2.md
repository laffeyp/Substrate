# Objective validation layer — design, round 2 (post-power-analysis)

*Status: architecture-band design, amending round 1. This round folds a Monte-Carlo power analysis of the paired-binary design and corrects three statistical points round 1 either got wrong or left open. Read [`benchmarking-design-round1.md`](benchmarking-design-round1.md) first; round 1 stands except where amended here. Working name "assay" still provisional.*

*Provenance: a Monte-Carlo power study (exact McNemar; Tango 1998 / Nam 1997 score-TOST rebuilt from scratch and validated to 1e-9; reproduced under adversarial re-derivation, including a brute-force feasibility check) plus a roadmap audit, 2026-06-26. Every number below is simulated, not asserted; the honesty caveat in §6 states the assumptions the numbers depend on. Amendments are traced in the table at the end.*

---

## 1. Why this round exists

Round 1 fixed the design's honesty posture (two Oracle classes, the three-state control-ran check, pre-registration, per-dimension compute, contamination dating). It left the statistics stated correctly in spirit but wrong in three specifics, and it carried a roadmap whose first step rested on a misconception. The first real run (a 6-problem bank, a powered weak-vs-strong difference, and a 4/6-vs-4/6 "match" the framework correctly refused to call equivalence) made the gap concrete enough to measure. This round measures it.

The headline: **the design is statistically honest, but the equivalence ambition is one-to-two orders of magnitude under-powered, and the obvious way to "fix" it (more trials) is counterproductive.** None of this dents round 1's architecture; it right-sizes the claims that architecture can carry.

## 2. The power reality (what a paired-binary bank can and cannot certify)

The comparison is paired across problems: a per-problem resolved/not bit per arm, collapsed across trials by pass^k (all k trials pass), compared by exact two-sided McNemar; equivalence by TOST against a pre-registered margin δ.

**A 10-problem bank cannot earn a powered equivalence claim at any defensible margin.** Simulated under truly-equal arms, TOST power at n=6 and n=10 is ~0 for δ = 0.10, 0.15, and 0.20. This is structural, not a tuning problem: a brute-force search over every outcome table shows that at n=10, equivalence within ±0.20 is **mechanically impossible** — no table passes — and the first margin a 10-problem bank can pass at all is 0.25, reachable only through the degenerate zero-discordant table. n=6 cannot pass at any margin up to 0.30.

The mechanism is a discordant-budget ceiling. Exact two-sided McNemar needs **≥6 same-direction discordant pairs** before its p can fall below 0.05 (2·0.5⁶ = 0.031). With ten problems the budget is exhausted before inference is possible. This is the same fact that made the framework refuse the 4/6-vs-4/6 call — correct behavior, not a defect. The only verdict n ≤ 10 can deliver is near-total dominance (the weak-vs-strong win was effectively a 6-0 sweep). It can never call a tie.

**Problems needed for ~80%-powered equivalence**, pre-registered margin δ:

| margin δ | problems (≈80% power) |
|---|---|
| ±0.20 | ~90 |
| ±0.15 | ~160 |
| ±0.10 | ~360 |

Required n scales as ≈ p_disc / δ²: halve the margin, roughly quadruple the bank. Detection (catching a real difference) is far cheaper than equivalence — a real, moderate gap powers up by roughly n≈100, a large gap by roughly n≈45 (these detection figures are directionally confirmed but not independently pinned; treat as approximate). Either way, ten problems is off by one-to-two orders of magnitude for an equivalence claim. **A defensible first equivalence-capable bank is ~90–160 problems at a pre-registered δ of 0.15–0.20.** Tighter margins get expensive fast.

## 3. Trials are the wrong knob for the comparison (amends round 1 §4.6)

Round 1 implied — and the build plan stated — that running more trials per cell would "narrow the CI for a real reason" and let the bank earn equivalence. This is backwards.

Growing trials k at fixed n narrows the cross-problem CI only through a **floor-effect artifact**: pass^k compounds failure across trials, so the collapsed marginal pass rate deflates toward all-fail (0.58 → 0.27 → 0.15 → 0.06 as k goes 1 → 3 → 5 → 9), and the estimand itself shrinks toward a degenerate zero. The CI looks tighter because it is collapsing onto "neither arm can solve anything k-in-a-row" — a hollow equivalence. The proof it is hollow: McNemar power at a *fixed real per-trial gap* does not improve with k; it flatlines and then degrades.

Only **adding problems** narrows the between-problem CI legitimately (SD = √(p_disc/n), confirmed to three decimals; power climbs steeply). Trials do reduce within-problem sampling variance, but second-order, and they cannot rescue n=10.

**Resolution.** pass^k stays as the registered *reliability* estimand, and k is chosen for that purpose. It is never a substitute for problem count. The equivalence/difference verdict scales with n, not k.

## 4. The statistics, corrected (amends round 1 §4.6)

**4.1 The bit-collapse does not inflate false positives — it is conservative.** Round 1 (and the round-1 review) worried that collapsing trials to an all-pass bit and feeding it to McNemar under-propagates trial variance and is anticonservative. Simulation refutes this for type-I: under truly-equal arms the false-positive rate is ~0.004 at n=10, far below nominal 0.05, because trial noise is exactly what generates the discordant pairs and exact McNemar conditions on them. The trial-variance-propagating alternative (a two-level cluster bootstrap) is the *less* safe choice at small n (type-I ~0.068, mild percentile-bootstrap anticonservatism). **Keep exact McNemar.** The real cost of the collapse is power loss and the floor effect (§3), not false positives. A consequence for the A/A calibration check: a healthy result is ~0 rejection, not ≤5%; a reading near or above 5% means something is broken — most likely a Wald approximation swapped in.

**4.2 The equivalence test must be a score/RMLE TOST, not "p>α" and not a Wald CI.** Two tempting tools are both wrong:

- *"McNemar p > α ⇒ equivalent"* is absence of evidence, not equivalence. Because exact McNemar is conservative, a non-significant result is nearly guaranteed at small n regardless of truth, so this rule would rubber-stamp "equivalent" on noise. (This is the error round 1's review already flagged; the simulation confirms its severity.)
- *Wald / asymptotic CI-inclusion TOST* is anticonservative for matched pairs (worst-case type-I ~0.20 at n=10, decaying with n) and, with zero discordant pairs, its CI collapses to a zero-width point at 0 and **falsely declares equivalence**.

Use **TOST on the matched-pairs proportion difference with a score / restricted-MLE interval (Tango 1998; equivalently Nam 1997)**, pre-registering δ. It is calibrated (type-I ≤ ~0.05 across n and nuisance), correctly refuses the degenerate small-n cases, and Tango proves McNemar is its δ=0 special case — so it is a clean superset of the current machinery and behaves well in exactly the all-pass ceiling case where naive intervals fail. For very small banks where even the score asymptotics are shaky, use the unconditional exact paired equivalence test (Hsueh, Liu & Chen 2001). Frame the whole thing in the TOST / equivalence-bounds idiom (Lakens 2017; Schuirmann 1987).

**4.3 Pre-state the minimum-detectable-effect from the bank size.** Round 1 said "state an MDE before running" without a method. The method: for the chosen test and n, the MDE follows from the discordant rate; report it (and the p_disc assumption it rests on) as part of pre-registration, so "no measured benefit" can be read as "no benefit larger than the MDE," not "no benefit."

## 5. The pass^k vs pass@k trap (new; the highest-risk hollow number)

pass^k (all k trials pass — a *reliability* estimand) gets **harder** with k. pass@k (at least one of k passes — a *coverage* estimand) gets **easier** with k. They move in opposite directions. The repeated-sampling gains in the literature (Brown 2024; Snell 2024) are pass@k coverage gains, and they convert to accuracy **only through a verifier** that selects the winning sample.

The hazard: a cheap arm made competitive by best-of-N selection silently (a) swaps the certified estimand from the registered pass^k reliability to pass@k coverage, and (b) needs a verifier — and if that verifier is the agent's **visible** tests rather than the **firewalled held-out** grader, apparent coverage inflates against the very tests the agent optimized. This is the single most likely route to an impressive-but-hollow result.

**Resolution.** The only legitimate selector is the held-out grader. pass^k reliability is the registered estimand; pass@k, if wanted, is a separately *named* secondary metric reported alongside, never instead. Any best-of-N selection is reported with the selector named (held-out-verifier coverage vs. a deployable realistic selector — they measure different things).

## 6. Matched compute is matched *currency*, not matched *parameter count* (amends the round-1 review's big-gap framing)

A draft of the roadmap critique held that comparing a large single-pass model against many small calls plus a selection structure is "no longer matched compute" and therefore a different question. That conflates matched parameter count with matched compute. **Compute can be matched in a common currency — tokens, FLOPs, or wall-clock — fixed a priori.** k forward passes of a model ~1/k the size is FLOP-comparable to one large pass, so a currency-matched comparison restores the exact "structure substitutes for raw capability at matched compute" claim. This is precisely Snell (2024)'s compute-optimal test-time-scaling result (a smaller model with test-time compute beating a 14×-larger one *is* a matched-compute finding). Capability/cost substitution is therefore a legitimate instance of the matched-compute claim, not a rival to it.

**Resolution.** The large-gap ("480B bar") comparison is in scope, on conditions: fix the matched currency up front (a token / FLOP / wall-clock budget, never parameter count); make the verifier and any selection explicit (§5); and relabel the claim as capability/cost substitution. Without those it becomes a different result wearing the structure claim's clothes.

*Honesty caveat (provenance).* The §2 numbers assume a collapsed marginal pass ~0.58 and a discordant rate p_disc ~0.40 at k=1, matched to the first run. Required-n rescales with p_disc (≈ p_disc/δ²); re-run the simulation with the observed discordant rate once a larger bank exists, and treat the table as a planning estimate, not a constant.

## 7. The integrity ratchet is phased (amends round 1 §4.2/4.3)

Applying full pre-registration to every number is purism to the point of uselessness; it would forbid the iteration a benchmark actually needs. Split the work:

- **Exploratory phase** — iterate freely (bank, prompts, k, arms), report descriptively, make **no** equivalence claims and **no** powered verdicts. Numbers here are for building the instrument, labeled as such.
- **Confirmatory run** — one run carries the full apparatus: a frozen pre-registration (§8 template), an a-priori margin, a powering statement, per-model post-cutoff contamination filtering, an append-only run registry, and the firewall audit. The verdict from this run is the only thing permitted to use the words "difference" or "equivalent."

As a confirmatory gate the ratchet is cheap and right; as a tax on exploration it is self-defeating.

## 8. Roadmap, corrected

1. **Freeze a pre-registration before any confirmatory arm runs** — the one-page template in [`benchmarking-preregistration-template.md`](benchmarking-preregistration-template.md). Falsifiable check: the committed pre-reg hash timestamps strictly before the first arm execution.
2. **Run the full local bank + trials as instrument calibration, not for equivalence.** Certify the firewall holds at scale; report per-arm pass^k reliability and an honest McNemar/TOST verdict. The goal is a verdict in *either* direction; "underpowered / inconclusive at n=10" counts as success. Do not run it expecting equivalence — §2 already gives that answer.
3. **Decide the local bank's job.** Either keep it small as a *calibration* instrument (report differences only), or invest in making it a *validated proxy* (show it correlates with the external set — see §9). A 90–160-problem bank at δ=0.15–0.20 is the floor for a local equivalence verdict.
4. **The large-gap comparison, run first among the ambitious steps** (it is a detection claim at a large gap — cheap to power), with the matched currency fixed, the verifier explicit, and the claim relabeled (§6). Falsifiable goal: "at matched [token/FLOP/wall-clock] budget, does the cheap stack land within δ of the large-model pass rate?" — not "the erosion is dramatic."
5. **SWE-bench-Live as the external-validity instrument** (Zhang et al. 2025), same pre-reg discipline, instances filtered to after *each model's* training cutoff (sharper than the benchmark's blanket "since 2024" floor — a 2025-cutoff model is contaminated by 2024 issues), accumulated across months until powered (~50 new instances/month is underpowered alone). A powered null here is a real, reportable outcome. This is the only step that certifies generalization.

## 9. External validity is a property of the sampling frame, not of authorship (amends the round-1 review)

"An author-created bank has no external validity at any n" is too strong. HumanEval, MBPP, and GSM8K are author-made yet treated as predictive, because their items were constructed to represent a defined distribution. A curated bank that is stratified against a pre-specified real population, or empirically shown to correlate with the external set, earns cautious generalization and works as a cheap leading indicator. The real disqualifier is *unvalidated convenience sampling of invented items* plus contamination — narrower than "author-created." So validating the local bank as a proxy for SWE-bench-Live is a legitimate path, not a dead end (§8 step 3).

## 10. Open decisions

1. **The local bank's job** — calibration instrument vs. validated proxy (§8 step 3). Decide before investing in bank growth.
2. **The pre-registered margin δ** — justify as the smallest pass-rate gap that would change a real decision; this sets the required n (§2).
3. **The matched currency for the large-gap comparison** — token, FLOP, or wall-clock budget (§6).
4. **Name** — still deferred to the vocabulary session.

---

## Changes from round 1

| Round 1 said | Round 2 amends |
|---|---|
| §4.6 "more trials narrows the CI" | §3: trials narrow the CI only via the pass^k floor effect; only problems give legitimate precision. |
| review worry: bit-collapse → McNemar is anticonservative | §4.1: simulation shows it is *conservative* (A/A type-I ~0.004 at n=10); keep exact McNemar; the cluster bootstrap is the less safe one. |
| §4.6 "paired McNemar / pass^k bootstrap CI; state MDE" | §4.2–4.3: equivalence must be a Tango/Nam score-TOST with pre-registered δ; never "p>α" or a Wald CI; MDE derived from n and p_disc. |
| (implicit) equivalence is reachable on a modest bank | §2: n≤10 cannot reach equivalence at any defensible margin; ~90–160 problems at δ=0.15–0.20. |
| review: the large-gap run is "a different question, not matched compute" | §6: matched *currency* (not parameter count) makes it a legitimate matched-compute claim (Snell 2024). |
| §4.2/4.3 pre-registration as a blanket discipline | §7: phased — exploratory (free, descriptive) vs. one confirmatory run (full apparatus). |
| review: author bank has no external validity | §9: external validity is about sampling frame + construct, not authorship; a validated proxy earns cautious generalization. |
| (new) | §5: the pass^k vs pass@k estimand swap + visible-test verifier trap — the highest-risk hollow number. |

## Revision log

- **round 2 — 2026-06-26.** Folded the Monte-Carlo power analysis: the n≤10 equivalence-impossibility result and required-n table (§2); trials-are-the-wrong-knob (§3); the corrected statistics — conservative bit-collapse, score-TOST over Wald/"p>α" (§4); the pass^k vs pass@k trap (§5); matched-currency clarification for the large-gap run (§6); the phased integrity ratchet (§7); the corrected roadmap (§8); and the external-validity-is-about-sampling-frame correction (§9).
- **round 1 — 2026-06-25.** Initial objective-validation design (see `benchmarking-design-round1.md`).
