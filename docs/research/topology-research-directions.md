# Topology research directions

*Status: research document. Future directions, not a build plan. Author: reviewer, 2026-08-09. Companion to `output-conformance-design.md`, which specs the first entry in the measurement-probe category. This document catalogues topologies worth building against substrate, ranked and specified enough for an Architect to pick the next one, but not detailed enough to be a sprint chain. Read `README.md`, `adding-a-topology.md`, `benchmarking-design-round1.md` and `-round2.md` first — the primitives and the assay contract are the vocabulary this document assumes.*

*The bundled catalogue as of 2026-08 covers about half of what substrate is architecturally capable of expressing. The gaps are named here.*

---

## 0. What counts as a topology worth cataloguing

Three criteria. All three must hold.

- **Solves a real LLM problem no single prompt or fine-tune can.** The value comes from the composition, the record, or the dynamic topology — not from prompting a smarter model. A topology that could be replaced by a longer prompt is not a topology worth building.
- **Generalises past one instance.** The topology takes parameters (target, arm set, case set, budget) so it produces value across many concrete studies. `output_conformance` is the pattern; each of the twelve categories below inherits it.
- **Fits substrate's primitives cleanly.** Producers with typed events, Views over the log, Triggers on predicates, a Termination policy. If a topology needs a mechanism substrate does not offer, that mechanism is a separate design question and the topology waits on it.

Anything that fails one of these is an application, a script, or a paper — not a topology.

## 1. What substrate already ships (baseline)

Named so the gaps below are legible. Grouped by category.

- **Measurement / graded competition.** `swebench_solver`. One benchmark, one solver. Application-shaped, not a general instrument.
- **Composition.** `debate`, `adversarial_pair`, `code_review`, `pair_coding`, `natural_conversation`, `natural_conversation_bare`.
- **Search / decomposition.** `recursive_decomposition`.
- **Discipline / correction.** `best_of_n`, `coding_flow`, `code_evolution`.
- **Simulation / multi-agent dynamics.** `prisoners_dilemma`, `intel_asymmetry`, `game_of_life`, `game_of_life_glider`.
- **Tool use.** `tool_loop`.

The measurement category is where substrate has one specific application (`swebench_solver`) and zero general instruments. Discipline has best-of-N and correction but no reasoning-discipline enforcers. Search has decomposition but no explored-and-pruned reasoning. Composition is well-covered. Simulation is well-covered.

## 2. Category A — Measurement probes

Every entry in this category takes a model M and a case set C, holds M constant, and measures a property OF the model that the model itself has no way to grade.

### A1. `sensitivity_probe`

Generate N paraphrases of each prompt via a paraphraser producer. Run each through M. Compute pairwise answer divergence per case; aggregate to a per-model brittleness score. Emit a per-case, per-paraphrase-pair `Divergence` event.

*What it measures.* Prompt brittleness — the degree to which a model's answer depends on surface form rather than semantic content.
*Why the topology.* The model that generated the answer is the wrong grader for whether the answer would change under phrasing shift; a second producer generates the perturbations, a third grades the divergence.
*Literature.* Sclar et al. 2023 ("Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design"). Zhu et al. 2023 ("PromptBench").
*Cost.* Light — one paraphraser + one divergence grader per pair.
*Priority.* High. Every LLM deployment inherits brittleness; almost nobody measures it.

### A2. `calibration_probe`

For each case in a set with known answers, force M to state a confidence (integer 0–100). Grade correctness. Fit a reliability diagram and an Expected Calibration Error (ECE). Emit per-case `Confidence`, `Outcome`, and a run-terminal `CalibrationCurve`.

*What it measures.* Whether the model's stated confidence tracks its correctness.
*Why the topology.* ECE is an aggregate across many (task, confidence, outcome) triples; the model cannot compute its own calibration from any single call.
*Literature.* Guo et al. 2017 (temperature scaling). Kadavath et al. 2022 ("Language Models (Mostly) Know What They Know"). Tian et al. 2023.
*Cost.* Light. The critical decision is the case set — must have unambiguous ground truth.
*Priority.* High. Production LLM apps route decisions off unreliable confidence estimates every day.

### A3. `position_bias_probe`

For a fixed task type (needle in a haystack, question over documents), sweep the needle position p across an N-token context. Emit `Recall(position=p)` events. Aggregate to a recall-by-position surface per document type.

*What it measures.* The lost-in-the-middle effect on this model, on these documents.
*Why the topology.* The surface is a two-dimensional aggregate (position × document class) that a single evaluation call does not produce.
*Literature.* Liu et al. 2024 ("Lost in the Middle"). Anthropic's needle-in-haystack tests.
*Cost.* Light-medium. Case-set construction is the work; the topology is a sweep.
*Priority.* Medium-high. Every RAG deployment inherits this and few teams measure it on their own corpus.

### A4. `context_saturation_probe`

Hold the task constant, hold the needle position constant, vary the total context length by padding with irrelevant material. Measure task accuracy as a function of total tokens.

*What it measures.* Degradation with total context size, isolated from position.
*Why the topology.* Same aggregate-over-a-sweep pattern as A3, orthogonal axis.
*Literature.* Same cluster as A3; specifically the "haystack size" experiments in the Anthropic tests.
*Cost.* Light.
*Priority.* Medium.

### A5. `format_stability_probe`

For a set of tasks requiring structured output (JSON against a schema, XML, tables), measure the parseable-fraction under M when the format spec is presented in different ways (inline, in a system prompt, by example). Emit per-case `FormatOutcome(parseable, validates, extra_keys, missing_keys)`.

*What it measures.* How reliable a given model is at producing valid structured output, and how much the framing of the spec matters.
*Why the topology.* Format-reliability is an aggregate across many cases; a single call cannot tell you the fraction.
*Literature.* Xia et al. 2024's ablations on prompt format in coding tasks. OpenAI's JSON mode behavior write-ups.
*Cost.* Light. Every check is a parser call.
*Priority.* Medium. Directly useful to anyone deploying structured-output pipelines.

### A6. `adversarial_robustness_probe`

A red-team producer generates adversarial versions of a task prompt (typos, prompt injections, misleading framings, jailbreak attempts). Measure answer stability and refusal-boundary shifts.

*What it measures.* How much a model's answer or safety behavior changes under adversarial input.
*Why the topology.* The red-team producer is a distinct piece; the answer-stability grader is a third piece.
*Literature.* Zou et al. 2023 ("Universal and Transferable Adversarial Attacks on Aligned Language Models"). Perez et al. 2022 ("Red Teaming Language Models").
*Cost.* Medium — the red-team producer needs a real attack corpus or a strong red-team model.
*Priority.* Medium. High if the deployment is exposed to untrusted input.

### A7. `training_cutoff_probe`

For a case set with known creation dates, measure model accuracy as a function of case date. Fit an empirical training-cutoff curve.

*What it measures.* The date beyond which the model's knowledge falls off. Distinct from the model's stated cutoff (often wrong).
*Why the topology.* The cutoff curve is an aggregate over many dated cases.
*Literature.* Karpukhin et al. 2020 on knowledge recency. Direct method used in SWE-bench-Live curation.
*Cost.* Light if the case set exists. The case set is the work.
*Priority.* Medium. Useful for any RAG or knowledge-graph deployment.

### A8. `judge_calibration_probe`

A meta-probe. For a judge model (typically used inside `output_conformance` or similar), calibrate the judge against a known-good rating set produced by humans. Emit judge-vs-human Cohen's κ and a per-preference miscalibration signal.

*What it measures.* Whether a judge model can be trusted as a grader.
*Why the topology.* Every judge-based topology depends on judge reliability; a probe that separates judge-error from arm-error is a prerequisite for any confirmatory run using a judge.
*Literature.* Zheng et al. 2023 ("Judging LLM-as-a-Judge"). Panickssery et al. 2024 on self-preference bias.
*Cost.* Medium — needs a human-rated calibration set.
*Priority.* High for any team relying on LLM judges in a benchmark.

## 3. Category B — Composition instruments

Multiple producers where the composition is the value, not any single producer's output.

### B1. `chain_of_verification`

Producer 1 answers the question. Producer 2 generates verification questions from the answer. Producer 3 answers each verification question independently, without the anchoring effect of the original answer. A checker producer flags contradictions.

*What it measures / does.* Reduces hallucination in the emitted answer by forcing independent verification of decomposed claims.
*Why the topology.* The independence of Producer 3 from Producer 1 is what makes the check honest; a single-producer self-check inherits the original's anchoring.
*Literature.* Dhuliawala et al. 2023 ("Chain-of-Verification Reduces Hallucination in Large Language Models").
*Cost.* Medium.
*Priority.* High. General anti-hallucination pattern with published effect size.

### B2. `committee_review`

N reviewer producers, each with a declared perspective (correctness, style, safety, cost, ambiguity, edge-case). Each emits a scored `Review`. An aggregator producer emits a final `Grade` with the per-perspective breakdown.

*What it does.* Generalises `code_review` beyond code. Any high-stakes output can use a per-perspective panel.
*Why the topology.* The perspectives are declared, the reviews are separable, the aggregation is auditable; a single reviewer-with-many-considerations blends the perspectives into one opaque grade.
*Literature.* Weng et al. 2023 (perspective-taking prompt ensembles). Ganguli et al. 2022 on Anthropic's red-team panels.
*Cost.* Medium.
*Priority.* Medium-high.

### B3. `disagreement_flag`

Run the same task on N models from N different families (Claude, GPT, Gemini, Llama, Qwen). A comparator producer scores answer divergence. Emit `Disagreement` events when divergence crosses a threshold.

*What it does.* Flags tasks where the models genuinely disagree — a task-difficulty signal stronger than any single model's expressed uncertainty.
*Why the topology.* Cross-family disagreement uses distinct training distributions; a single model's disagreement-with-itself is intra-family only.
*Literature.* Lin et al. 2023 on multi-model uncertainty. The self-consistency literature (Wang et al. 2022) inverted.
*Cost.* Medium — needs multi-model access.
*Priority.* High for triage of expensive downstream work.

### B4. `panel_of_judges`

A set of judges from different families rate the same outputs; measure inter-judge agreement per Cohen's κ; produce a consensus grade only when agreement clears a threshold; refuse to grade otherwise.

*What it does.* Extends the single-judge pattern in `output_conformance` §6 to a panel, so a judge with a systematic bias cannot swing the verdict alone.
*Why the topology.* Same reason committee_review is a topology — the panel's disagreement is the signal, not a nuisance.
*Literature.* Zheng et al. 2023.
*Cost.* Medium.
*Priority.* Medium. Necessary for high-stakes judge-based benchmarks.

### B5. `advocacy_debate`

Two producers each argue a fixed side of a proposition (assigned, not chosen). A judge decides. Distinct from `debate` which is symmetric; this pins each model to its assigned side.

*What it does.* Tests whether a model can generate strong arguments for positions it might not otherwise take. Useful for red-teaming, for structured pro/con analysis, for stress-testing decisions.
*Literature.* Irving et al. 2018 ("AI Safety via Debate"). Michael et al. 2023.
*Cost.* Light.
*Priority.* Medium. Research-interesting; specific applied use in decision review.

### B6. `dialectic_synthesis`

Thesis producer, antithesis producer, synthesis producer. The third reads the first two and produces a reconciliation. A grader scores synthesis quality against a rubric (integrates both, contradicts neither, adds a new frame).

*What it does.* Structured reconciliation of two views. Distinct from `debate` (which produces a winner); this produces a merged position.
*Literature.* Sparse; the pattern is philosophical rather than published.
*Cost.* Light.
*Priority.* Low-medium. Interesting but narrower applied value than B1–B4.

## 4. Category C — Search instruments

Dynamic topology used for actual state-space exploration. Substrate's Triggers spawn Producers as new states appear on the log; this is the category the log-first design was made for.

### C1. `tree_of_thought`

Branch on candidate reasoning steps. An evaluator producer scores each branch. A pruner keeps the top-k. Extends until a terminal condition (answer reached, depth budget, all branches pruned).

*What it does.* Structured search over reasoning steps rather than sampling reasoning traces.
*Why the topology.* State management for the tree is exactly what substrate's log-plus-triggers is for; nobody implements this cleanly on a checkpoint-based runtime.
*Literature.* Yao et al. 2023 ("Tree of Thoughts").
*Cost.* Medium.
*Priority.* High. Substrate's dynamic-topology primitive is uniquely suited; this is the topology that shows off what the runtime is for.

### C2. `monte_carlo_rollout`

For state-space problems (games, planning, simulation), N rollout producers simulate from the current state to a terminal. Outcomes aggregate back to inform the current decision.

*What it does.* MCTS-style planning driven by model rollouts.
*Why the topology.* The rollout independence and the aggregation are naturally topology-shaped.
*Literature.* MCTS in the AlphaGo lineage; recent work applying it to LLM planning (Feng et al. 2023, "AlphaZero-like Tree-Search for LLM").
*Cost.* Medium.
*Priority.* Medium. High for any planning or game application.

### C3. `beam_search_reasoner`

Top-k partial reasoning kept per step, pruned by a scorer, extended by an expander. Distinct from `tree_of_thought` (which branches freely) — this is disciplined width.

*What it does.* A predictable-cost search over reasoning space.
*Literature.* Xie et al. 2023 ("Self-Evaluation Guided Beam Search").
*Cost.* Medium.
*Priority.* Medium.

### C4. `iterative_deepening`

Try shallow reasoning first, deepen only where shallow was inconclusive. A confidence gate decides whether to spawn a deeper reasoner. Compute-adaptive.

*What it does.* Spends compute where it earns; a general pattern for cost-aware reasoning.
*Literature.* Cobbe et al. 2021 on verifier-guided search; classic AI iterative deepening.
*Cost.* Medium.
*Priority.* Medium.

### C5. `hypothesis_generate_and_test`

One producer generates candidate hypotheses. A tester producer evaluates each against evidence. Confirmed hypotheses feed into a synthesiser. Rejected ones seed a next-round generator.

*What it does.* Scientific-method-shaped reasoning as a topology.
*Literature.* Ellis et al. 2020 on program-synthesis-as-hypothesis-testing.
*Cost.* Medium.
*Priority.* Medium.

## 5. Category D — Discipline instruments

Topologies that impose a discipline the base model does not have. Every entry has the shape: a normal producer emits, an auxiliary producer enforces a constraint, the run halts or corrects on violation.

### D1. `assumption_extraction`

Before answering, force the model to enumerate the assumptions its answer would rest on. A second producer evaluates each assumption's validity against a source or a schema. The answer producer emits only after assumption verification.

*What it does.* Turns implicit reasoning into an auditable chain. Every "the model was confident and wrong" failure is an unstated assumption failure.
*Literature.* Zhou et al. 2023 ("Least-to-Most Prompting") adjacent. Explicit assumption-extraction as a discipline is less formalised.
*Cost.* Light.
*Priority.* High. Directly reduces overconfident-wrong failures.

### D2. `clarification_loop`

Before answering, an ambiguity-detector producer scores the prompt. Below threshold the model answers. Above threshold, a clarification producer emits a question through a human-in-the-loop gate. Resumes on user reply.

*What it does.* Pre-answer discipline for ambiguous prompts. Kills a class of "model answered the wrong question" failures for one round-trip cost.
*Literature.* Deng et al. 2023 on clarification-question generation.
*Cost.* Medium — needs a working human-in-the-loop pattern (see F1).
*Priority.* Medium-high.

### D3. `iterated_refinement`

Draft producer emits a candidate. Critic producer emits critiques against a spec. Reviser producer incorporates critiques. Loop until the critic passes or a diminishing-returns predicate holds.

*What it does.* Serial refinement with critic feedback. Distinct from best-of-N (independent samples).
*Literature.* Madaan et al. 2023 ("Self-Refine"). Chen et al. 2023 ("Teaching Large Language Models to Self-Debug").
*Cost.* Medium.
*Priority.* Medium.

### D4. `cite_before_claim`

The model must cite a source from a provided corpus before making a factual claim. A checker producer reads emitted claims and looks up citations. Uncited claims are rejected and re-drafted.

*What it does.* Enforces evidence-groundedness for factual output.
*Literature.* Menick et al. 2022 ("Teaching Language Models to Support Answers with Verified Quotes"). Gao et al. 2023 on citation quality.
*Cost.* Medium.
*Priority.* High for any RAG or knowledge-grounded application.

### D5. `check_your_work`

After answering, force the model to independently verify its answer using a different method (e.g. solve the math a second way, back-translate a translation, re-derive a proof). A comparator emits a disagreement flag.

*What it does.* Discipline against single-method reasoning failures.
*Literature.* Weng et al. 2022 on self-verification. Kadavath et al. 2022 adjacent.
*Cost.* Light.
*Priority.* Medium.

### D6. `counter_example_search`

For any general claim the model makes, spawn a producer that actively searches for counterexamples. If found, the claim is qualified or retracted.

*What it does.* Discipline against overclaiming.
*Literature.* Falsification-driven prompting is scattered; the disciplined-topology version is sparse.
*Cost.* Medium.
*Priority.* Low-medium. Interesting; narrow applied case.

### D7. `disclosure_gate`

For topics with known model limitations or biases (medical, legal, financial advice; recent events; identity attribution), force an explicit disclosure before answering. Rule-based enforcement in a gate producer that reads the prompt and either passes or injects the disclosure requirement.

*What it does.* Structural enforcement of appropriate-uncertainty markers.
*Literature.* Anthropic's own alignment writeups on model appropriate uncertainty.
*Cost.* Light.
*Priority.* Medium. Especially in regulated deployments.

## 6. Category E — Meta-topologies

Topologies about topologies. Every one takes another topology as input.

### E1. `topology_ablation`

Take a compound topology. Systematically remove one producer or one trigger at a time. Run the case set on each ablated version. Measure the outcome delta. Emit a per-piece contribution map.

*What it does.* Automates what Sprint 159 does by hand for SWE-bench arms.
*Why the topology.* Every future confirmatory run will need this analysis; hand-writing it per topology is the drift the meta-topology exists to prevent.
*Literature.* Ablation as a research method is universal; formalising it as a substrate topology is the specific contribution.
*Cost.* Medium. The mechanism is straightforward; the interface for "which pieces of an arbitrary topology are ablatable" is the design question.
*Priority.* High. Earns its keep the day the second substrate topology gets a confirmatory run.

### E2. `topology_composition_probe`

Measure whether composing topology A with topology B (via `embedded_substrate`) produces measurably better outcomes than either alone on a shared case set.

*What it does.* Empirically grounds the composition claim substrate's `embedded_substrate` primitive makes.
*Literature.* None; the composition primitive is substrate-specific.
*Cost.* Medium.
*Priority.* Medium.

### E3. `arm_diversity_probe`

For an ablation matrix, measure whether the arms actually produce different output distributions or whether they collapse to the same behaviour despite structural difference. Kills the "ablation ran, everything scored the same, we assumed the differences didn't matter" failure mode where the arms were degenerate rather than genuinely equivalent.

*What it does.* Detects degenerate ablations.
*Literature.* Kapoor & Narayanan 2024 raise the ambient version; the specific probe is not formalised.
*Cost.* Light.
*Priority.* Medium. Useful as a pre-flight check on any confirmatory run.

## 7. Category F — Interaction topologies

Human in the loop, multi-turn structure, resource-bounded operation.

### F1. `human_in_the_loop_recovery`

General pattern: a topology halts at typed boundaries (`awaiting_human_decision`), writes an entry to a queue, waits for the user's reply, resumes with the reply as input. The reply itself is an event on the record.

*What it does.* Makes human-in-the-loop a first-class topology primitive instead of an ad-hoc pattern per application.
*Literature.* Anthropic's Human-in-the-Loop guidance. LangGraph's interrupt pattern (checkpoint-based, weaker than what substrate can offer).
*Cost.* Medium.
*Priority.* High. Prerequisite for D2, C-series and several applied topologies.

### F2. `progressive_disclosure`

Answer at increasing detail as the user requests more. Level-1 producer emits a short answer, level-2 emits a fuller one on request, level-3 emits the full derivation. The user's request-for-more is an event.

*What it does.* Structures conversational depth as a topology instead of hoping the model reads user cues correctly.
*Literature.* Sparse.
*Cost.* Light.
*Priority.* Low-medium.

### F3. `resource_bounded_reasoner`

The topology respects a budget (time, tokens, calls) and adapts reasoning depth to what fits. Distinct from iterative deepening (which deepens on inconclusiveness); this deepens on available budget.

*What it does.* Makes cost-aware reasoning a topology primitive.
*Literature.* Ren et al. 2023 on budget-aware LLM inference.
*Cost.* Medium.
*Priority.* Medium.

## 8. Category G — Multi-agent research topologies

Substrate already has `prisoners_dilemma`, `intel_asymmetry`, `game_of_life`, `game_of_life_glider`. These are the same class. What follows adds axes the existing four do not cover.

### G1. `emergent_language`

Put N models in a communication game with a shared goal but no shared vocabulary. Measure whether they develop a stable protocol.

*What it does.* Probes whether LLMs can bootstrap shared meaning under task pressure. Related to substrate's memory-vs-vocabulary discipline.
*Literature.* Lazaridou et al. 2017 on emergent communication in RL agents; recent LLM adaptations (Chen et al. 2024 on emergent conventions).
*Cost.* Medium.
*Priority.* Medium. Research-facing.

### G2. `theory_of_mind`

One model reasons about another model's beliefs given a shared conversation history. A grader checks the belief attribution against the second model's actual next output.

*What it does.* Measures model-of-model accuracy — a specific cognitive capability.
*Literature.* Kosinski 2023 (contested), Ullman 2023 (rebuttal), Sap et al. 2022.
*Cost.* Medium.
*Priority.* Medium. Research-facing; useful for multi-agent debugging.

### G3. `deception_detection`

One model instructed to be truthful, one instructed to be deceptive. A third judges which is which. Measures whether deception is detectable by other models under this setup.

*What it does.* Probes a specific safety-relevant capability.
*Literature.* Pacchiardi et al. 2023, Scheurer et al. 2023.
*Cost.* Medium.
*Priority.* Medium. Safety-adjacent research.

### G4. `norm_convergence`

Repeated multi-agent game with a shared payoff structure. Measure whether models converge on stable equilibria and how fast.

*What it does.* Studies whether LLMs behave as rational strategic agents under repeated play.
*Literature.* Fontana et al. 2024 on LLM game-theoretic behavior.
*Cost.* Medium.
*Priority.* Low-medium. Research.

### G5. `self_modeling`

Model asked to predict its own future outputs on tasks; measure prediction accuracy.

*What it does.* Measures self-knowledge in a specific sense. Adjacent to calibration but with the model as its own subject.
*Literature.* Betley et al. 2024 on introspection.
*Cost.* Light.
*Priority.* Low-medium.

## 9. Category H — Applied topologies

Real-world task shapes, general enough to be topologies rather than one-off scripts.

### H1. `typed_information_extraction`

Schema-driven extraction of structured data from unstructured text. Producer 1 extracts candidate fields. Producer 2 validates against schema. Producer 3 resolves ambiguities. Emits `Extraction(field, value, source_span, confidence)` per field.

*What it does.* The whole LLM-as-parser class of tasks as a general topology.
*Literature.* Xu et al. 2023 on schema-driven extraction with LLMs.
*Cost.* Medium.
*Priority.* High. Directly applied; wide use.

### H2. `multi_document_synthesis`

N documents in, one synthesis with citations out. Per-document extractor producers emit facts. An aggregator produces a synthesis draft. A verifier checks every citation against source. Uncited or misattributed claims trigger revision.

*What it does.* Enterprise-shaped RAG done with the discipline substrate can enforce.
*Literature.* Gao et al. 2023 on citation-grounded synthesis.
*Cost.* Medium-heavy.
*Priority.* High.

### H3. `long_horizon_planning`

Decompose a high-level goal into subgoals. Spawn sub-topologies per subgoal (via `embedded_substrate`). Aggregate results. Handle inter-subgoal dependencies via routes on the shared log.

*What it does.* The multi-step-plan-and-execute pattern as a real topology, not a demo.
*Literature.* Wang et al. 2023 ("Voyager"), Yao et al. 2022 ("ReAct") for the base pattern.
*Cost.* Heavy.
*Priority.* Medium-high.

### H4. `curriculum_synthesis`

From a task specification, the model generates a curriculum of examples that would help solve it. A trainer producer uses the curriculum; a grader measures whether the curriculum actually improved solutions.

*What it does.* Tests whether models can generate their own useful training material.
*Literature.* Wang et al. 2024 on self-generated curricula.
*Cost.* Medium.
*Priority.* Low-medium. Research.

## 10. Cross-cutting themes

Patterns that appear in more than one category and would benefit from a shared substrate primitive.

- **Multi-model access as first-class.** A5, B3, B4, G1–G5 all require calling different model families on the same task. `adapters/ensemble.py` (sprint 157) is the seed; a first-class multi-model dispatcher would unblock the whole cluster.
- **Case-set curation is the work.** A2, A6, A7, C-series, D-series — the topology is often light and the case set is the load-bearing artifact. A `case_bank` type with typed cases, ground-truth fields, and contamination-date metadata would serve every category. A shared library of curated case banks would compound value across studies.
- **Human-in-the-loop as a primitive.** D2, F1, F2 all need a working pattern for typed halts + resume-on-reply. F1's design is a prerequisite for the others.
- **Judge reliability as a prerequisite.** A8 gates B4 and any judge-based composition. Building A8 first raises the trust ceiling on every downstream judged topology.
- **Record as replay is the differentiator.** C1–C4 (search) and E1 (ablation) exploit substrate's log-first design in ways checkpoint-based runtimes cannot; these are the topologies where the runtime's architectural bet pays.

## 11. What to build next — selection

Not a plan. Ordering criteria the Architect can apply.

- **Highest general leverage per unit build cost.** A1 (`sensitivity_probe`), A2 (`calibration_probe`), D1 (`assumption_extraction`), D4 (`cite_before_claim`), E1 (`topology_ablation`), H1 (`typed_information_extraction`).
- **Highest research payoff (unpublished-effect risk).** B1 (`chain_of_verification`) has known effect; the substrate-native version would be measured cleanly. G3, G4 open genuinely novel questions but with correspondingly higher uncertainty.
- **Highest architectural fit.** C1 (`tree_of_thought`), E1 (`topology_ablation`). These are the topologies where substrate's log-first, dynamic-trigger design is uniquely suited; building them showcases what the runtime is for.
- **Prerequisite chains.** F1 unblocks D2, F2. A8 unblocks confident use of judges in any composition. Multi-model dispatcher unblocks A5, B3, B4, G-series.

A defensible first slate of five, chosen against these criteria: A1 + A2 (measurement probes that every LLM deployment needs), B1 (published-effect anti-hallucination), E1 (meta-tool that pays back every future ablation), C1 (the topology that shows off the runtime). Five topologies, all in categories the bundled catalogue does not yet cover, each of which either measures something no single call can or exploits substrate's dynamic topology in a way checkpoint-based runtimes cannot express.

## 12. What is missing from this catalogue

Named so the gaps in this document are legible.

- **RL-adjacent topologies.** Reward modelling, preference elicitation, iterative-fine-tuning-driving-topologies are absent. Substrate has no first-class training seam; adding these requires a design conversation.
- **Multi-modal topologies.** Every entry above is text-in, text-out. Vision, audio, video producers exist in principle; no bundled topology exercises them.
- **Real-time / streaming-graded topologies.** Everything above is batch. A topology graded on streaming behaviour (latency, first-token time, streaming coherence) would need a different oracle class.
- **Adversarial-safety topologies.** A6 is the seed; a full family (jailbreak-resistance, prompt-injection-defence, output-filtering) deserves its own catalogue.
- **Long-running / persistent-state topologies.** Everything above is per-run. Topologies that maintain state across many runs — knowledge accumulation, model-of-user learning — need substrate's cross-record composition, which is post-1.0.

Each of the five is a research direction of its own. This document catalogues topologies buildable against the substrate primitives that ship today; extensions to the primitives themselves are separate design work.

---

*Research directions authored 2026-08-09 after `output-conformance-design.md`. Twelve categories, forty-plus topologies named. The bundled catalogue as of 2026-08 covers about half of what substrate is architecturally capable of expressing; the other half is here. Additions welcome; nothing here is a build commitment. When a topology moves to build, it gets its own design doc in the style of `output-conformance-design.md` or `swebench-solver-design.md`.*
