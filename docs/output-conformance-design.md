# Output-conformance probe — topology design (v1)

*Status: architecture-band design. No code yet. Author: reviewer, 2026-08-09. Target: a general Substrate topology that measures whether a prompt intervention moves output measurably closer to a specified target property, on a fixed case set, under matched compute, graded by a stack of mechanical checks + a family-disjoint judge + a human ratification sample. Read `docs/benchmarking-design-round1.md` and `docs/benchmarking-design-round2.md` first; the assay contract there is what this topology consumes.*

*Provenance: motivated by a live question — does a specific `UserPromptSubmit` hook actually produce prose in a target register — but the question generalises. The interesting object is the topology, not any one hook. The register case is the first worked instance (§8); the topology takes the target and the grader as parameters (§5, §6).*

---

## 1. Scope and shape

**Input.** A set of case prompts C. A set of prompt-intervention arms A (each a text that gets prepended to a prompt). A target-property specification T (mechanical checks + a judge prompt). A generator model M held constant across arms. A trial count k per (arm × case).

**Output.** For each (arm × case × trial), a `Response` on the record and a `ConformanceScore` per grader tier. A ranked `Report` over arms with paired confidence intervals, per the existing `assay/report.py` shape.

**The topology, in one line.** A grid of (arm × case × trial) responses, each graded on the same T by three tiers, aggregated by paired stats against a control arm. Every arm consumes the identical (case, target, grader) so the only variable between arms is the intervention.

**What it is not.** Not a general prompt-optimiser. It measures whether a specified intervention moves output toward a specified target; it does not search intervention space. Not a task-correctness benchmark. Correctness of the underlying answer is a separate axis and needs a different oracle.

## 2. The general question, precise

Given a fixed model M, a fixed case c, and a target property T, does prepending intervention a to the case's prompt produce a response whose conformance to T, graded by a stack that names its assumptions, is higher than the response produced under intervention a' (typically the no-intervention baseline)? Which arm wins under paired comparison at the pre-registered δ, and which mechanical properties of the output move in the direction T specifies?

This is a general form. Instances the topology handles without code change beyond a target definition:

- **Register conformance.** Target = a named prose register (White/Orwell plain, academic, corporate memo, marketing). Intervention = candidate `UserPromptSubmit` hook texts.
- **Format conformance.** Target = valid JSON against a schema. Intervention = system-prompt fragments that specify the schema differently (positive-only, negative-only, example-driven).
- **Brevity.** Target = a token-count ceiling. Intervention = brevity instructions phrased differently.
- **Vocabulary constraint.** Target = a domain wordlist (medical, legal, financial). Intervention = glossary prepends.
- **Tone.** Target = a mood/sentiment axis with a scored classifier. Intervention = tonal instructions.
- **Meta-narration removal.** Target = absence of "let me", "I'll", "certainly", "as an AI". Intervention = negative hooks.

The topology is one instrument. The register case is one instance.

## 3. Substrate mapping (the eight pieces)

- **Producers.** Per arm, one `intervened_generator(a)` that prepends a to the case prompt and calls M once, emitting `Response`. One `mechanical_grader(T)` that reads `Response` from the record and emits `MechanicalScore` events (deterministic, replayable). One `judge_pair(T, judge_M)` per unordered arm pair (a, a') that reads two responses, presents both to a judge model in a randomised order, emits `Preference`. One `verdict()` producer that aggregates per-arm scores and emits `ConformanceVerdict`.
- **Events.** `Response`, `MechanicalScore`, `Preference`, `ConformanceVerdict`, plus `ModelUsage` per model call. All frozen msgspec Structs. Schema locked before build.
- **Bus / record.** Every response, every mechanical number, every judge preference on the same record. `mechanical_grader` is `deterministic=True` (pure over its input record). `intervened_generator` and `judge_pair` are `deterministic=False` (model calls, replayable=False per response, captured once).
- **Views.** `responses` (KindBuffer of `Response`), `mechanical_scores` (KindBuffer of `MechanicalScore`), `preferences` (KindBuffer of `Preference`).
- **Predicates / Triggers.** "All (arm × case × trial) responses in → fire the mechanical grader per response." "All responses for a case in → fire the judge on every unordered arm pair." "All preferences in → fire the verdict."
- **Routes.** None required at v1. The verdict producer reads the views directly.
- **TerminationPolicy.** `threshold_count("ConformanceVerdict", 1)` OR `quiescence_with_watchdog`. Never hang.
- **Topology name.** `output_conformance`.

## 4. The Arm contract

An arm is `(name, role, intervention: str)`. The intervention is text prepended to the case prompt at generation time. The `build(case)` function returns a topology that, given a case's `prompt` and the arm's `intervention`, wires an `intervened_generator` that emits exactly one `Response` per trial. The arm never sees the target T or the grader — those live at the suite level and every arm consumes the identical (target, grader) pair.

The control arm is exactly one, named at suite construction. The pre-registration lists it (`benchmarking-preregistration-template.md` §4). The verdict's paired stats are always the-other-arm vs the control.

Ablation ergonomics. An arm can be constructed from a base intervention plus a modifier — the "author reference removed" ablation is the base minus one clause, not a separate arm authored in isolation. The suite builder factors this so an ensemble of six arms is one call over the four levers (author reference on/off, ban list on/off, example on/off, verbatim rules on/off).

## 5. The Target-property specification

A target T is a triple `(name, mechanical_checks, judge_prompt)`. Frozen at suite construction. All arms grade against the identical T.

- **`name`** — a string identifier. Appears in the report headline and the pre-registration. Example: `"register:white-orwell-plain"`.
- **`mechanical_checks`** — a list of `(check_name, callable, direction)` triples. Each callable takes a `Response` string and returns a float. Direction is `"higher-is-better"` or `"lower-is-better"`. The check set for the register case is enumerated in §8. Additional checks for other instances are enumerated at their target definition. Every check is pure and deterministic.
- **`judge_prompt`** — a string with two placeholders (`{response_a}`, `{response_b}`) that a judge model receives per pair. The judge returns exactly one of `A`, `B`, `TIE`. Prompt is committed to the record verbatim so a re-grade under a different judge is reproducible.

A target is a first-class artifact stored under `process/conformance-targets/<name>.py` (or `.json`). Its content-hash is part of the pre-registration; a target change bumps a run version. This is the direct analogue of the SWE-bench firewall spec — the target defines what "success" is, and it is frozen before arms run.

## 6. The grader stack

Three tiers. Each has its own failure mode, and the tiers cross-check each other. The pattern is Addendum A three-lens grading applied to prose instead of pixels.

**Tier 1 — Mechanical.** Deterministic checks per `mechanical_checks` in T. For each `Response`, emit one `MechanicalScore` event per check. Reads only the response text and the checkers; no model calls. Replayable (Level 2). Blind spot: mechanical checks measure surface properties. A response can pass every check and still miss T's spirit; a response can fail one check while carrying T's spirit better than a passing one.

**Tier 2 — Judge.** For each unordered arm pair per case per trial, a family-disjoint judge model receives the two responses in randomised order and returns `A`/`B`/`TIE`. Randomisation seed committed. Judge family MUST differ from the generator family (TECHNIQUES #42). Judge prompt frozen in T. Emitted as `Preference` events. Not replayable; captured once. Blind spot: judges have their own register bias and their own laziness pattern; a strong response written in a register the judge model was fine-tuned to prefer wins for the wrong reason. This is why tier 3 exists.

**Tier 3 — Human ratification.** A random 10% sample of judge decisions gets pulled to a `ratification.jsonl` file. The Architect (or a named human rater) rates each pair blind, matches the judge decision or not. Cohen's κ between judge and human is computed on the sample. If κ < 0.6, the judge signal is not trusted and the report headline drops to mechanical-only. This is the observation contract on the judge itself.

**Rule.** The mechanical tier is the primary evidence surface. The judge is a secondary aggregate that is trusted only when its κ against the human sample clears the floor. The human sample is the calibration of the judge, not the primary grade — it does not scale to 4 500 pairs, and it is not the estimand.

## 7. Statistical apparatus (reuse)

`assay/stats.py` already carries what this needs.

- **Per-arm score.** Mechanical: a vector of check means. Judge: Bradley-Terry rank across all pairwise comparisons involving this arm.
- **Paired test vs control.** Exact two-sided McNemar on the per-case "did arm beat control on the mechanical composite" bit. Paired bootstrap CI on the delta.
- **Equivalence.** Score-TOST (Tango 1998 / Nam 1997) per sprint 150. Pre-registered δ. INCONCLUSIVE when the delta CI crosses zero or n is below the power floor.
- **Multiplicity.** BH-FDR across the arm matrix. Pre-registered α.
- **Power reality.** Per `benchmarking-design-round2.md` §2: 90 problems at δ=0.20, 160 at δ=0.15, 360 at δ=0.10 for ~80%-powered equivalence. This topology inherits the reality. A five-arm register study on 20 prompts × 3 trials is 300 responses per arm and roughly 750 pairwise comparisons — enough for a δ ≈ 0.2 difference call, marginal for tighter, and never an equivalence call.

## 8. First worked instance — register conformance to White/Orwell

**Target definition.** `register:white-orwell-plain`, stored at `process/conformance-targets/register_white_orwell_plain.py`.

**Mechanical checks (each with direction).**

- `banned_token_rate` (lower better) — count per 1 000 words of a committed banned-token list. List frozen in the target file. Includes the register offenders named in the reviewer's memory and Orwell's specific bans.
- `passive_voice_rate` (lower better) — count of passive constructions per 100 sentences, via a `spaCy` dependency parse or a simple auxiliary-plus-past-participle regex.
- `adverb_rate` (lower better) — `-ly` adverb count per 100 words. Orwell rule two.
- `sentence_length_mean` (target ≈ 15, lower better above 25) — mean words per sentence.
- `sentence_length_variance` (higher better up to a floor) — variance across the response. Orwell/White vary length; LLM baseline is uniform.
- `latinate_root_fraction` (lower better) — words tagged as Latinate against an Anglo-Saxon wordlist. Orwell rule five.
- `preamble_marker` (binary; 0 better) — presence of `let me`, `I'll`, `certainly`, `great question`, `as an ai` in the first sentence.
- `trailing_summary_marker` (binary; 0 better) — does the last paragraph restate the body without adding a fact. Approximated by n-gram overlap between the last paragraph and the concatenated body above.

Eight checks. Each cheap and auditable. Every check is a pure function committed with the target.

**Judge prompt.** "Below are two prose responses to the same prompt. One reads more like the plain register of E. B. White and George Orwell — every sentence carries a fact, active voice, concrete nouns, short words, no filler, no preamble, no meta-narration. Which reads more like that register? Answer exactly one of A, B, TIE." Frozen verbatim in the target.

**Judge model.** A model from a different family than the generator. If the generator is Claude, the judge is a Llama or Qwen variant; if the generator is GPT, the judge is a Claude variant. Family disjoint per TECHNIQUES #42.

**Arms** (six).

- `A0_no_hook` — no intervention. The control.
- `A1_author_ref_full` — the current hook text ("Write like E. B. White and George Orwell. Plain register only. Every sentence carries a fact. Active voice, named subject, concrete noun. Short words over long. No preamble, no summary, no meta-narration. Do the work; do not hand small work to the user. This applies to all output, including internal reasoning.").
- `A2_ban_list_only` — a negative-only intervention listing forbidden tokens with no author reference and no positive rules.
- `A3_orwell_rules_only` — Orwell's six rules from "Politics and the English Language" verbatim, no author names.
- `A4_example_paragraph` — one paragraph of White prose prefixed with "Match this register."
- `A5_minimal` — "Plain register. Every sentence carries a fact." One clause.

Six arms lets the analysis separate the mechanism: is it the author invocation, the ban list, the positive rules, an example, or a short reminder that does the work.

**Cases** (twenty). Committed to `process/conformance-runs/register_2026-08/cases.json` before any arm runs. Five categories, four prompts each: (a) code review, (b) status update on a project, (c) explain a technical concept, (d) summarise a design document, (e) technical email response. Each prompt is a real work task the Architect could have received. Frozen; no additions or removals after run start.

**Trials.** k = 3 per (arm × case). 20 cases × 6 arms × 3 trials = 360 responses total.

**Compute budget.** Same generator model across every arm. Same decoding parameters (temp 0.7, top-p 0.95, max tokens 800). Only the prepended intervention differs.

**Pre-registration.** Fill `benchmarking-preregistration-template.md`. Fields specific to this run: claim type = difference; primary estimand = per-arm mechanical composite score (weighted mean of the eight normalised checks); primary test = paired McNemar on "arm beat control on the composite" bit per case; α = 0.05; BH-FDR across the five non-control arm comparisons. No equivalence claim — n=20 does not reach the power floor for equivalence at any defensible δ.

**Decision rule (verbatim).** "Arm X beats the control iff the paired-difference CI on the mechanical composite excludes zero at the BH-FDR-corrected α = 0.05, AND the judge Bradley-Terry rank places X above the control, AND κ between judge and human sample ≥ 0.6. Any of the three failing yields `INCONCLUSIVE`. `INCONCLUSIVE` is the verdict, not a licence to declare the closer number the winner."

## 9. Other instances the same topology handles

Named to show generality. Each is one target definition + one arm set + one case set. No topology change.

- **Format conformance.** Target = valid JSON against a JSON Schema Draft-07. Mechanical checks: parses (0/1), validates (0/1), extra keys count, missing required keys count. Judge: none needed (mechanical is complete). Arms: candidate system-prompt fragments (schema-inline, schema-linked, example-driven, rules-driven).
- **Brevity.** Target = response tokens ≤ 200. Mechanical checks: token count, information density (facts per 100 tokens, via a fact-extraction classifier). Judge: pairwise "which is more information-per-token." Arms: brevity instructions phrased four ways.
- **Domain vocabulary.** Target = medical terminology. Mechanical: term-frequency against a MeSH wordlist. Judge: pairwise "which reads more like a physician wrote it." Arms: glossary prepend variants.
- **Meta-narration removal.** Target = absence of LLM tells. Mechanical: count of "let me", "I'll", "certainly", etc. per response. Judge: pairwise "which reads more like a person wrote it." Arms: negative-only, positive-only, hybrid.
- **Tonal shift.** Target = a sentiment axis with a classifier scored -1 to +1. Mechanical: classifier score. Judge: pairwise on tone. Arms: tonal instruction variants.

The topology cost per instance is a target file (checks + judge prompt) and a case set. Everything else is the same runtime, the same graders, the same stats, the same report.

## 10. SDD adherence — pre-build obligations

Per `sdd-kit-2/AGENTS.md` hard rules and the discipline the swebench-solver design follows.

- **Vocabulary session (#1, #2, #6, #25) — obligation.** Lock the event schemas — `Response`, `MechanicalScore`, `Preference`, `ConformanceVerdict`, `Target` — with payload fields typed and reviewed. Register in `process/WORKING_AGREEMENT.md`. Run the dual-contract audit pairing every behavior tag with an observable: `Response` → the mechanical grader can compute at least one score; `MechanicalScore` → the check name is in T; `Preference` → the judge randomisation seed is on the record; `ConformanceVerdict` → the per-arm rank is deterministic given the recorded scores.
- **Observation contract asserts on the RECORD (#24).** The judge's replayability is `False` (a captured judgement, not a re-executable one); the mechanical grader's is `True`. The verdict is deterministic given the recorded scores. Every arm's response count per case per trial is asserted before the verdict fires. A missing response is a typed halt, not a hidden zero.
- **Canonical home (#22, #7).** The `Target` type owns its home at `topologies/output_conformance/target.py`. The check callables live under `topologies/output_conformance/checks/` one file per check family (register/, format/, brevity/, vocab/, tone/). No cross-target imports; a check reused across targets is imported by both target files from the checks module.
- **Chain-of-small-sprints (#12, #17).** Re-split the build as:
  1. Vocabulary session (plan-mode) — lock records + the `Target` shape + the pre-registration schema addition for `target_hash`.
  2. Topology skeleton — one producer per role, wiring, no real graders yet.
  3. The mechanical grader — the eight register checks as pure functions, unit-tested to gold cases.
  4. The judge producer — with a deterministic stand-in judge for CI.
  5. The verdict producer — pure over recorded scores.
  6. The register target — the first Target file, with its committed check list, judge prompt, and case set.
  7. The confirmatory run — pre-reg committed, arms executed, report generated.
- **Typed halts (#28).** A grader that cannot run on a response (parse failure, missing file) emits a typed halt event, not a silent 0. A judge that returns an unparseable answer is retried once with a stricter re-prompt then classified as a `Preference(result=UNPARSEABLE)`; unparseable rates are reported.
- **Diary (#34).** Open `process/KIT_DIARY.md` entries for the judge-vs-human κ number as the study runs — this is where the observation contract on the judge itself accumulates.

## 11. Sprint chain

Ordered. Each ≤ 2 files / one concept except sprint 3 (the check bundle) which explicitly declares its multi-file scope in the card and lists the eight files.

1. Vocabulary session — records + Target shape + pre-reg addition. Plan-mode.
2. Topology skeleton — `topologies/output_conformance/__init__.py`, `records.py`, empty `assemble.py`.
3. Mechanical checks — `topologies/output_conformance/checks/register.py` (eight functions + tests).
4. Judge producer — `topologies/output_conformance/judge.py` with a deterministic CI stand-in.
5. Verdict producer + assemble — `topologies/output_conformance/verdict.py` + wire `assemble.py`.
6. Register target — `process/conformance-targets/register_white_orwell_plain.py` with checks list + judge prompt + committed case set.
7. Suite + arm builder — `assay/conformance_suite.py` mirroring `assay/swebench_suite.py`; the arm ergonomics from §4.
8. Human ratification harness — `scripts/conformance_ratify.py` that pulls 10% of `Preference` events into `ratification.jsonl` and computes κ against the Architect's ratings.
9. Confirmatory run — pre-reg committed, matrix run through `run_arm_on_case`, report generated.
10. Writeup — `process/conformance-runs/register_2026-08/README.md` with the verdict verbatim from the machine, the per-arm ranks, mechanical profiles, and κ.

## 12. Non-goals

- **Not a prompt optimiser.** The topology grades a specified arm set. It does not search intervention space, does not learn an intervention, does not evolve prompts. Prompt search is a separate topology.
- **Not a task-correctness grader.** A response can be in the target register and be wrong about the underlying task. Correctness needs a task oracle; this topology does not have one.
- **Not a general LLM evaluation framework.** Inspect AI and lm-eval-harness measure model capability across a benchmark set. This measures whether an intervention on one model moves output toward one property. Different axis.
- **Not an alternative to SDD's Rubber Duck Pass.** The Rubber Duck Pass grades a sprint's signal trace against the vocabulary. This grades a response's text against a register. Both are external-check-surface graders; different check surfaces.

## 13. Open decisions

1. **Judge model choice.** The pre-registration must name the exact judge model. Family-disjoint from the generator is fixed; the specific model is Architect-decided. Fall-back plan if the primary judge is unavailable.
2. **The banned-token list for the register target.** Committed with the target file; whichever list ships at v1 is what the run grades against. The list should include every offender in the reviewer's memory file plus Orwell's specific bans; the exact final list is Architect-signed before commit.
3. **The Anglo-Saxon wordlist.** Public lists exist (Roget's, Bailey's) with different coverage. Pick one and commit its hash. A future ablation can swap and re-grade.
4. **The Architect's rating cadence for the ratification sample.** 36 pairs at 10% of 360 responses is manageable in one sitting; if the Architect defers, the judge signal is not trusted and the report ships mechanical-only.
5. **Where the topology lives in the bundled catalogue.** `topologies/output_conformance/` is the proposed home; a name change (`conformance_probe`, `register_ablation`, `intervention_effect`) is up for the vocabulary session.

## 14. Fold status

- Assay control plane (`benchmarking-design-round1.md`, `benchmarking-design-round2.md`) — CONSUMED. This topology is a plain Arm/Case/Suite instance graded through `run_arm_on_case`.
- Pre-registration template — CONSUMED (§8, `benchmarking-preregistration-template.md`).
- Statistics (`assay/stats.py`) — CONSUMED (§7). Score-TOST from sprint 150; paired McNemar; BH-FDR.
- Three-lens grading (Addendum A) — ADAPTED (§6, prose instead of pixels).
- Judge-family-disjoint discipline (TECHNIQUES #42) — CONSUMED (§6, §8).

Nothing new in the substrate primitives. Nothing new in the assay layer. One new topology + a target-file convention.

---

*Design authored 2026-08-09 after reading `swebench-solver-design.md`, `benchmarking-design-round1.md`, `benchmarking-design-round2.md`, `benchmarking-glossary.md`, `benchmarking-preregistration-template.md`, and `adding-a-topology.md` for register and structural convention. The register conformance instance is one worked target; the topology is the object.*
