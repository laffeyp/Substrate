# REVIEW round 2 — what round 1 missed (2026-08-12)

*Reviewer role, same session. New dated file per no-in-place-edits.*

*Round 1 lives at `docs/review/REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md`. The build side dispatched Sprints 165–176 against it in about two hours and marked 15/15 findings closed. This round is what round 1 missed by pitching every finding at a level a linter could reach.*

*Reads underneath this round: the full 856-line `PAPER-2026-08-12-swebench-failure-and-the-sdd-remedy.md`; the twelve sprint cards 165–176 and their close notes on `process/BLACKBOARD.md`; targeted greps for the retyped literals, publish-refusal wiring, dead-import survivals, and the runner's post-Sprint-169 exception surface.*

---

## The one sentence this review turns on

Closing fifteen findings in two hours did not move the arc; five of the fifteen closures are legible on paper and inert in the tree, and the pattern the arc keeps reproducing sits underneath every finding round 1 named.

---

## Meta-findings

### M1 — Round 1 was pitched at the level a linter reaches; the arc's actual problem sits one level deeper

Twelve sprints landed in about two hours. Every finding closed. The tree has moved; the arc has not. The rate-limit shim now releases its semaphore; the Architect ruled the shim is not the path Verified pass 1 fires against. The publish-refusal branch exists in `assay/report.py`; the runner does not call it (grep on `scripts/assay_swebench_confirmatory.py` for `graded_rate_floor` or `RunUnpublishable` returns zero). The heavy-topology DeprecationWarning is elevated to error in pytest; four scripts still import the heavy topology and run outside pytest (`solve_instance.py:28,100`, `flask_solve.py:115,137`, `docker_runner_smoke.py:10`, `regression_seam_smoke.py:22` — one more than Sprint 173's close note admits).

The pattern of the round-1 findings — "a raw string that should be an imported constant", "an `except BaseException` that should be `except Exception`", "an unnamed tuple that should be a Struct" — is the pattern a static tool would raise. It is a legitimate class of finding; it is not what a review is for. A review is for the things a static tool cannot see. Round 1 mostly named the things a smarter linter would.

The one round-1 finding that reached deeper (F1 on the rate-limit shim) got fixed and then over-ruled by the Architect's standing note during Sprint 170: the shim's fix stays as a correctness bug fix and does not unblock Verified. That leaves round 1's "two-move short list" at one move that produced no throughput and one move that fixed a bug.

Round 2's findings sit one level up. The list is shorter and each item takes longer than an afternoon to close.

### M2 — The paper is the finding

`docs/review/PAPER-2026-08-12-swebench-failure-and-the-sdd-remedy.md` (856 lines, dated 2026-08-12) is a positioning document, not an engineering audit. Three specific reasons.

**The title tells the reader what the paper is for.** "The SDD remedy" is what SDD-as-methodology needs to argue on behalf of itself. An engineering audit of one arc does not need to conclude "SDD is not optional for LLM-authored programs at this complexity" (§ 1). Correctness is the outcome the arc needs; SDD is one instrument that might produce it. Naming the instrument in the title reframes the audit as adoption argument. This is the market/adoption framing the standing memory forbids ("drop market/product framing — correctness is the point").

**§ 10 "What NOT to conclude" violates the standing prose rule.** No "What NOT to do" sections in vision docs — recast as positive scope statements. The section names five conclusions to avoid; two of them ("Do not blame the models"; "Do not blame the team") are advocating for a specific narrative about causation, not scoping the audit's claims.

**The natural-experiment argument (§§ 2, 7) does not control the variable it claims to isolate.** The paper says: eleven bundled topologies work, the twelfth does not, the independent variable is discipline. But the eleven working topologies have no equivalent claim to succeed at — a `code_review` walkthrough demo passing is not the same measure as SWE-bench Verified producing ≥30% resolve. The paper's own § 7 Counter 2 introduces `container_arm` as the same-boundary counter-experiment. `container_arm` produces `SelectedPatch` on wire-check; it does not have a published resolve rate. Cross-comparison of "clean wire-check" and "108/300 on Lite" and "walkthrough demo passes" is not a controlled experiment. The paper's own falsifier list at § 7 end ("if a project of comparable complexity ... shipped working code without SDD") sets a bar the field has never had a control group for.

**Two stale claims sit inside the paper.** § 3.1 says the dead-vocabulary gap "is still open"; `SuspectElements` was wired at Aug-8 fold (`localize_elements.py:142` emits it; `assemble.py:501-508` registers `element_localizer` with the schema). § 3.2 cites the runner's `BaseException` catch as evidence; Sprint 169 narrowed it a few hours earlier. Both were paper-truth before the paper landed; both were code-truth by the time it did.

**What to do with the paper.** Either retitle and rescope as a technical postmortem (drop § 1's methodology-scope claim, drop § 10, drop the "natural experiment" framing, keep §§ 3, 4, 5 as concrete divergence-record) — or leave it as an internal position paper and stop treating it as review authority. The paper appears in `docs/review/`; the roadmap v2 companion doc cites it as authority ("the paper diagnoses SDD adherence"). Position papers do not diagnose; they argue. Round 1 did not read the paper and flagged the title only; that was round 1's largest miss.

### M3 — F3's closure is a mirage; no runner path calls the branch

Round 1 F3 named the missing publish-refusal branch. Sprint 170 landed `RunUnpublishable`, `graded_rate_floor`, ten tests, ruff+mypy clean; the finding was marked BLOCKER-closed. Sprint 170's own close note says: "`scripts/assay_swebench_confirmatory.py` doesn't yet thread `pre.graded_rate_floor` into `build_report(..., graded_rate_floor=pre.graded_rate_floor)`; that's a three-line follow-on."

`grep -n "graded_rate_floor\|RunUnpublishable" scripts/assay_swebench_confirmatory.py` returns zero lines. The next Verified pass-1 attempt reports the headline with no threshold check. Any run at 82% throttle publishes as if it had graded to completion. The primitive is on the shelf; nothing pulls it down.

The three-line follow-on is not queued as a sprint on the tree. The finding-count reads 15/15 closed; the load-bearing path is 0/1 wired.

### M4 — The tier misread is the halt reason no sprint touched

The 2026-08-12 halt lists four reasons; reason (2) is: "I read Ollama Cloud's '3 concurrent models' (Pro) as '3 concurrent requests per model' and built the shim's per-model semaphore against that misread invariant. The actual documented cap is distinct-model count; per-request rate limits are not published and I never checked the 429 response body or headers to learn what was actually being denied."

Twelve sprints later, no sprint has hit the endpoint with a rising-N test, captured the 429 body, or read the response headers to learn what the provider actually rate-limits on. Sprint 174 added an observation-contract line naming a 20% sustained-denial threshold; the threshold is a guess against a limit that is still unknown. Sprint 168 released the semaphore during sleep; the semaphore is still sized against an invariant the provider does not enforce.

Every subsequent boundary defense will be sized against the same guess unless someone measures. The addendums-C-worthy discipline (`ADDENDUMS.md` C1-C9 — Audio Object's XCUITest / os.Logger / SignalScope work) generalizes to: **before authoring a shim against an external service, verify the service's actual behavior with a probe.** A thirty-line script that hits `/api/chat` at increasing concurrency, captures every response's `status_code` + `body` + `Retry-After`, and dumps a per-second denial-vs-attempted CSV would settle this in an afternoon. Nothing on the sprint queue is that.

### M5 — Twenty hours of restructuring; no behavioral run

The last live assay artifact is `process/assay_lite_n300_6arm_shim_2026-08-11/cells.cases.json`, mtime Aug 11 20:41. Nothing has run since. Between then and now the tree accumulated: one postmortem, one halt, two roadmap versions, one audit, one paper, twelve sprint cards, twenty modified files, one review from me (round 1), twelve sprint dispatches, and now this round-2 review. The verifiable-behavior surface has moved zero.

The kit's `be-your-own-skeptic — green is not proven` discipline is asymmetric here: it prevents claiming a run succeeded until behavior is verified; it does not prevent claiming a fix succeeded until behavior is verified. Sprint 168's `test_semaphore_released_during_retry_sleep_lets_peer_progress` proves the semaphore releases in a mock; it does not prove the fix survives 300 real Ollama calls at Pro. The smallest possible next behavioral run is a 3-instance smoke that fires the light topology against Ollama Cloud through the fixed shim and reads the resulting record for `RateLimitAttempted`/`Denied` counts. Twenty seconds of the shim's actual behavior against the real endpoint would tell us more than an afternoon of sprint dispatch has.

### M6 — The "external review" label inflates ceremony and hides the seam

The blackboard entries call round 1 "external review REVIEW-2026-08-12-swebench-arc-sdd-architecture-coding.md" and call the sprint chain "close every remaining external-review finding." The reviewer is me. This session opened as the reviewer per the top of `## Surfaced for review`. `AGENTS.md` § "Who you are" says: "You play three roles sequentially within one session: Architect-partner ... Supervisor ... Worker." One session, three roles. Labeling the reviewer role "external" imports a two-party audit framing that raises the perceived cost of each finding — and consequently raises the reflex to fold, close, and mark 15/15 rather than sit with the pattern round 1 named.

The kit's shape does not have "external reviews"; it has the reviewer hat, the observation contract, the Rubber Duck Pass. Findings from any of those go on the blackboard the same way. Renaming one of them "external" is where the "just close the finding count" reflex comes from. Same finding count, different framing, different treatment.

---

## Concrete findings round 1 should have caught but did not

Ranked by consequence.

### R1 — `container_arm` is the actual natural experiment, and it is under-instrumented

The paper's `container_arm` counter-argument depends on `container_arm` being clean under the same six boundaries as the failing solver. `container_arm` has been in the matrix since 2026-08-11 (commit `2f311d6`). No assay run against Verified has isolated its resolve rate. No sprint declares an observation contract for it beyond `assert producer_kinds == ["solve"]`. Under the "same-boundary counter-experiment" claim, `container_arm` should be the arm the next behavioral smoke fires and reads.

A five-instance dry run of `container_arm` on Lite, reading the record for `SelectedPatch` and firing `HarnessProducer` on each patch, would either confirm the counter-experiment (record is clean, arm works) or falsify the natural-experiment claim in the paper. The paper cites `container_arm` in three places without a resolve number. That is the load-bearing missing evidence.

### R2 — The equivalence-form comparator is not measured on this substrate

`docs/preregistrations/2026-08-swebench-lite.preg.json` (per the pre-reg file structure the code reads) pins Agentless + GPT-4o = 27.8% resolve on Lite as the comparator for the equivalence claim. Substrate does not run Agentless. The 27.8% is a number from a paper on a different codebase, a different harness pin, a different environment. The equivalence claim reads: substrate's ensemble resolve rate is within δ of a number produced elsewhere.

Two exposures:
- Any environmental shift between the Agentless paper's run and this substrate's run — SWE-bench harness version, Docker image tag drift, model-provider tier — is a confound the equivalence math cannot see.
- The whole equivalence-vs-superiority framing rests on comparing substrate to a specific published number. If the number moves (SWE-bench dataset revisions do move; harness version pins do move), the comparator moves and the equivalence claim moves with it.

Two options: run Agentless on this substrate, this harness pin, this environment, and pin THAT number as the comparator; or drop the specific-comparator claim and frame the arms as within-substrate comparisons only. The second is honest and smaller; the first is more work but produces a comparator that can be defended without a paper citation.

### R3 — "Grade becomes replayable at Level 1" (roadmap v2 § "Shape v2 lands") conflates the audit with the grade

Roadmap v2 at line 41-42 says the collapse to `LogProjectionOracle` moves the grade "replayable at Level 1 (record-derivable) rather than run-and-observe at Level 3(b)." What becomes record-derivable is the AUDIT of the grade — the recorded `GradeResult` event replays deterministically. The GRADE itself remains non-deterministic; pytest inside a Docker container is not a replayable function. Roadmap v2 markets the collapse as the substrate's payoff; the payoff as stated overclaims.

The honest framing: the recorded `GradeResult` event makes the grade auditable at Level 1 — you can `first_divergence` between two records and see they emitted different `GradeResult` events, which was already visible in the `resolved=false` vs `resolved=true` distinction in the report. What actually improves is that the reason for the divergence is inspectable via `explain_producer` walking back to the `HarnessProducer` events. That is a genuine improvement (post-hoc debugging surface) and is smaller than "the grade is now replayable."

Roadmap v2's § "Shape v2 lands" should distinguish the audit-replay claim (true, and payoff of the redesign) from the grade-replay claim (false, because pytest is stochastic).

### R4 — The 972 → 150 line runner claim is optimistic by roughly 2×

Roadmap v2 § S7 and the paper § 6 both cite the 972 → 150 shrinkage as the substrate payoff. An honest line count of the runner separates boundary except-branches from everything else. After Sprint 169 the runner has 2 `except` clauses (grep confirms). What remains: env parsing (~50 lines), `_build_arms_for_mode` (~140 lines), `_prep_one` + prep sweep (~90 lines), image pre-pull (~30 lines), `_write_cases_sidecar` (~30 lines), config fingerprint + preregistration wiring (~40 lines), the `cell` inner function (~90 lines even without the boundary handling), row writer + JSONL append + progress printout (~30 lines), the `_run` outer function + salvage path + batch-grade path (~80 lines). That sums to ~580 lines that are not boundary handling. Even after every boundary becomes a producer, these survive.

A more defensible target: 972 → ~350–400. The audit's "60% re-implements generic assay concerns" is closer to right. The paper and roadmap's 150 sounds sharper than it is; the sprint closing S7 will either meet an unrealistic target and land something too aggressive, or miss it and read as a scope failure. Set the target at 350–400 and both readings are honest.

### R5 — The trial structure in design v3 does not name the test it enables

Design v3 § "Pass 1 shape" says: "500 instances × 1 trial × 1 ensemble arm = 500 cells. Finding 14 collapses the earlier 500 × 3 × 1 = 1500. Three-trial McNemar on Pass 1 alone reads as belt-and-braces given Pass 2 runs the whole matrix with its own trial structure." The paragraph waves at McNemar and moves on. McNemar is a paired test; the pairing shape matters.

Two candidate pairings:
- **Instance-level pairing.** For each of 500 instances, ensemble arm vs baseline arm. McNemar over discordant pairs (b, c). This is the standard shape and matches the "delta between arms holding topology constant" claim.
- **Trial-level pairing.** For each (arm, instance) pair, trial-1 vs trial-2 vs trial-3. This is a variance decomposition (`pass^k` vs `pass@k`), not a between-arm test.

The pre-registration should name the exact statistic (McNemar's χ² with continuity correction, or an exact binomial test, or Wilson score interval on the discordant rate) and the exact pairing unit. The user's memory names "bit-collapse+McNemar is conservative not inflated; pass^k vs pass@k trap." Design v3 does not disambiguate. Roadmap v2 defers to S10's pre-reg update. The gap is not that a decision is missing; it is that the decision is deferred to the same shape of ad-hoc handling this arc is trying to move away from.

### R6 — Sprint 173's DeprecationWarning enforcement misses the four scripts that use it

Sprint 173 close note says three scripts still import the heavy topology (`solve_instance.py`, `flask_solve.py`, `assay_swebench_run.py`). Grep says four: `solve_instance.py`, `flask_solve.py`, `docker_runner_smoke.py`, `regression_seam_smoke.py`. `assay_swebench_run.py` does NOT import it (grep confirms). One mis-named script and one missed script. That is a small factual error in a close note that will be cited later as evidence the retirement is complete. The retirement is not complete; three scripts still emit the deprecated topology's kinds at runtime with no listener catching the warning.

Two moves in one commit: (a) migrate the four scripts to `swebench_repair_topology` (they built the heavy path for reproduction-based selection they no longer need under the design-v3 revert); (b) once migrated, un-comment the follow-on line in Sprint 173's close note.

### R7 — The Sprint 170 primitive lands without its consumer; that is a systemic pattern

Sprint 170 lands `RunUnpublishable`; the runner does not call it. Sprint 164 lands `Budget`; no producer declares one. Sprint 172 emits `UserWarning` when `budget=` is passed; nothing passes budget yet (Sprint 172's own tests pass budget explicitly, but production code paths do not).

Three sprints in a row lending "primitive on the shelf, consumer follows." Each closes clean because the primitive tests pass; each leaves the tree in a state where the primitive exists and does nothing. Under a rigorous dual-contract discipline, the primitive sprint's artifact contract should assert at least one live consumer. Right now the discipline permits "primitive lands; consumer follows in a separate sprint the next day." The pattern accumulates dead primitives.

Sprint 165 (roadmap v2 kernel enforcement, still unshipped) will make Sprint 164's `Budget` primitive load-bearing. Sprint N (unnamed) will make Sprint 170's `RunUnpublishable` load-bearing. Until then the tree has two shelf-primitives. Two is fine; three or four accumulates surface area that outlives its consumer's dispatch.

---

## Where round 1 was correct but for the wrong reason

Naming this to be fair.

**F1 (rate-limit shim slot-holding bug).** The finding was correct; the fix was correct. The "unblocks Verified pass 1" claim was wrong. The Architect's standing rule during Sprint 170 ("nothing gets shimmed") is the right posture — but round 1 did not anticipate that posture and framed the fix as unblocking. Sprint 168 is a bug fix, not a throughput win. Round 2 flags it as: the shim's semaphore is still sized against an unknown limit (M4).

**F5, F6, F8 (typed verdict at emit, Cap struct, WORKING_AGREEMENT axes).** These were reasonable pre-ratification tidies. The three sprints closed them mechanically. They will read as normal maintenance six months from now; that is what tidies do. The reason for flagging them at round 1 was correct; the surface impact was small. Round 1 could have folded all three into one meta-finding rather than dispatching them as three separate axes.

**F12 (roadmap v2 § S9 sustained-429 bound).** The finding was correct; the fix (Sprint 174) added a bound to the observation contract. The bound is a guess (see M4 — the tier's actual limit is unknown). The fix improves the paper record; it does not improve the actual defense until the limit is measured.

**F13 (CI guard preserves `_deprecated/`).** The finding was correct; Sprint 175 landed the guard. The guard prevents deletion; it does not prevent stagnation. Twenty uncommitted files across a day is a form of audit-trail rot that the deletion-guard does not catch. Round 2 names it under M5.

---

## What moves the arc

Ranked by expected effect on Verified pass 1's credibility.

1. **Measure the actual Ollama Cloud rate limit before authoring `RateLimitProducer`.** A thirty-line probe against the tier under test, capturing every 429's body + headers, per-second denial curve at rising concurrency. Ships as `scripts/probe_provider_rate_limit.py`; output pinned in `docs/preregistrations/` before roadmap v2 S5.2 dispatches. Closes M4.

2. **Run a 3-to-10 instance behavioral smoke against `swebench_repair_topology` + the fixed shim + the Ollama endpoint the run will actually use.** Read the resulting record for `RateLimitAttempted`/`Denied` counts. Verify Sprint 168 actually holds under load. Twenty seconds of real behavior beats a day of sprint dispatch. Closes M5.

3. **Wire `graded_rate_floor` into `assay_swebench_confirmatory.py` (three-line change) OR queue a sprint that does so.** Otherwise F3's closure is paper-only and the next Verified attempt publishes an unbounded headline. Closes M3.

4. **Give `container_arm` a real observation contract at N=5 and read the record.** Either the paper's natural-experiment claim confirms with evidence, or it falsifies. Right now the claim rests on `producer_kinds == ["solve"]` — a shape check, not a behavior check. Closes R1.

5. **Rewrite the paper as a technical postmortem or unlink it from `docs/review/`.** The current title ("the SDD remedy"), § 1's methodology-scope claim, § 10's "What NOT to conclude," and the natural-experiment framing all read as SDD-adoption advocacy rather than one arc's postmortem. Correctness is what the arc needs to earn; the paper's structure is what a methodology publication needs. Two different genres, two different documents. Closes M2.

6. **Pin the equivalence comparator to a substrate-produced number.** Run Agentless on this substrate, this harness pin, this environment. Whatever number comes out is the comparator; the equivalence math then has a defensible baseline. Alternative: drop the equivalence-vs-external framing and report substrate arms against each other only. Closes R2.

7. **Migrate the four scripts still importing the heavy topology.** Half an hour. Closes R6 for real.

8. **Add a dual-contract clause: "any sprint that lands a substrate primitive must land at least one live consumer or name the sprint that will."** Prevents R7's pattern from accumulating.

Items 1 and 2 are the ones I would run tomorrow. Item 3 is one commit. Item 4 fits between items 1 and 2. Items 5–8 are structural.

---

## Terminology audit

Round 1 said the prose was fine. Round 2 keeps that finding for the code and pushes back on the paper.

**"Remedy" is the wrong noun.** A remedy is what you offer to somebody who is sick. An engineering audit does not offer remedies; it names divergences and proposes changes. "The SDD divergences on this arc" or "Where SDD would have caught this earlier" reads as engineering; "the SDD remedy" reads as pharmaceutical. Small word; changes the register.

**"Natural experiment"** claims a controlled comparison. The paper's own § 2 admits the objection ("SWE-bench is uniquely hard") and dismisses it with `container_arm`; `container_arm` has no resolve number. That is not a controlled experiment; that is a same-shape observation with an uncontrolled variable. Either produce the missing data (R1 above) or drop the "natural experiment" language and call it "the sequence of failures on one arc."

**"Substrate application" vs "substrate topology" vs "substrate assay."** These terms slip across documents. Paper § 2 uses "application" for the twelve bundled topologies. WORKING_AGREEMENT uses "application" for the LLM-integration layer specifically. Roadmap v2 uses "assay" for the SWE-bench work. The three words are used for overlapping-but-not-identical scopes. Pick one word for one scope; the other two either become synonyms or get retired.

**"Boundary-as-producer"** is fine and consistent across docs. Keep.

**"Confirmatory"** is used correctly (pre-registered, publish-refusing branch, equivalence-form comparator). The word implies statistical rigor; the arc has to earn it. Right now the confirmatory framing is ahead of the statistical infrastructure (R2, R5). Either tighten the infra or soften the word.

---

## One-line summary

Round 1 was surface; the build side closed 15/15 in two hours without moving the arc, three of the closures are inert in the tree, the arc's actual problem is a mental model of "wrap the next external system in a Python class" that the paper reframes as SDD-adoption argument rather than confronts as a habit, and the next thing worth writing on this project is not another sprint card but a thirty-line probe of the actual Ollama Cloud rate limit followed by a five-instance smoke run against the fixed shim.

---

*Reviewer: Claude, this session, second round. Additive to `docs/review/` alongside the round-1 review, the paper, the audit, and roadmap v2. Findings for the build side to disposition. Nothing here to be closed by narrowing an except-clause.*
