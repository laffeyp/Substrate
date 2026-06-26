# Benchmarking pre-registration — template

*Status: a template. Copy it once per **confirmatory** run, fill every field, and commit it **before the first arm executes** (the commit hash + timestamp is the pre-registration). Exploratory runs do not need this and must not make powered or equivalence claims (see [`benchmarking-design-round2.md`](benchmarking-design-round2.md) §7). Filled instances live under `process/` or `runs/`, one per run; this file stays blank.*

*Voiding rule: once committed, every field below is frozen for this run. Changing any of them after an arm has executed does not edit this pre-registration — it opens a new, separately-reported run version. There is no in-place amendment of a frozen pre-reg.*

---

## 0. Identity
- Run id: `____`
- Date committed (UTC): `____`
- Pre-registration commit hash: `____`
- Assertion: this hash timestamps strictly **before** the first arm execution. ☐

## 1. Question
- One sentence: `____`
- Claim type (exactly one): ☐ difference  ☐ equivalence

## 2. Suite (frozen)
- Suite name / version: `____`
- Bank manifest hash (problem ids + held-out-test hashes, frozen): `____`
- Number of problems N: `____`

## 3. Adapter (frozen)
- Adapter identity / version: `____`
- Assertion: every arm — controls included — consumes the **identical** Adapter output per problem. ☐

## 4. Arms
- Control arm (exactly one, named): `____`
- Other arms + roles (full / ablation / baseline / placebo): `____`

## 5. Oracle
- Class: ☐ log-projection (replayable)  ☐ external-grader (run-and-observe, not replayable)
- Grader identity / version: `____`

## 6. Primary estimand (exactly one)
- `____`  (e.g. pass^k reliability)
- Trials per cell k: `____`   ·   k chosen for the reliability estimand, **not** as a substitute for problem count. ☐

## 7. Primary test
- Difference: exact two-sided McNemar, α = `____`.
- Equivalence: score / RMLE TOST on the matched-pairs difference (Tango 1998 / Nam 1997); for very small banks, the exact paired test (Hsueh/Liu/Chen 2001).
- Forbidden, by signature: ☐ "McNemar p>α ⇒ equivalent" (absence of evidence)  ☐ Wald CI-inclusion TOST (anticonservative; false-positive at zero discordant pairs).

## 8. Equivalence margin δ (equivalence claims only)
- δ = ± `____`
- Justification — the smallest pass-rate gap that would change a real decision: `____`

## 9. Power
- Assumed discordant rate p_disc: `____`  ·  assumed marginal pass: `____`
- MDE at this N (difference) / power at δ (equivalence): `____`
- Reference table (round 2 §2): equivalence ~80% power needs ~90 problems at δ=0.20, ~160 at 0.15, ~360 at 0.10; n≤10 cannot reach equivalence at any defensible margin.

## 10. Decision rule (published verbatim, before the run)
- Difference declared iff: `____`
- Equivalence declared iff the TOST passes against δ; otherwise the verdict is **"underpowered / inconclusive; difference CI = [..]"**. "p>α" never licenses "match."
- The published headline must be a **literal transcription** of the machine verdict string — never stronger.

## 11. Multiplicity
- Number of comparisons vs. control: `____`
- Correction across the arm matrix: ☐ Holm  ☐ Bonferroni  ☐ FDR (`____`)

## 12. Compute (per-dimension; no money)
- Reported axes, each on its own: quality, completion tokens, wall time, model calls. None fused; none a cost.
- Matched currency for any capability/cost-substitution arm (fixed a priori; never parameter count): ☐ tokens  ☐ FLOPs  ☐ wall-clock — value: `____`

## 13. Frozen run parameters
- Trials k: `____`  ·  seed-generation rule: `____`  ·  decoding params (temp / top-p / max tokens): `____`

## 14. Verifier / selection (if best-of-N is used)
- Selector = the **firewalled held-out grader** (the only legitimate selector). ☐
- pass@k, if reported, is a separately named **secondary** metric, never the primary. ☐

## 15. Contamination filter (external sets)
- Per-model training-cutoff dates: `____`
- Assertion: instances filtered to **after each model's** cutoff (not a blanket date floor). ☐

## 16. Firewall audit (CI gate)
- Held-out test files are absent from the agent sandbox. ☐
- No visible-test assertion duplicates a held-out one. ☐

## 17. Run registry
- Append-only registry location: `____`
- Assertion: every run with this config gets an immutable entry and is reported pass **or** fail; the denominator of runs is shown (no file-drawer). ☐

## 18. Secondary / exploratory metrics
- Labeled as such, carry no powered or equivalence claim: `____`
