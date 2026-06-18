# Substrate Product Spec — Critique Notes

**Status:** Notes against `substrate_product_spec.md` DRAFT 1
(itself building on `horizon_substrate.md` DRAFT v14). Captures the
issues worth carrying into DRAFT 2 of the product spec, into the
technical spec, and back into v14 where the kernel might need
revision. Not folded into the product spec itself — these are notes,
not pending edits.

Two issues could change the shape of the product. The rest is
tightening.

## 1. F-PRED-1 (Predicate budget enforcement) — shape-changing

Single most consequential underspecified clause. The kernel
semantics (v14) and a third of the conformance suite (checks 5, 8)
depend on the runtime being able to:

1. Measure each Predicate's per-call cost.
2. Quarantine violators reliably.
3. Not corrupt the writer's state when it does.
4. Not silently miss a violation that would have changed the
   outcome.

CPython gives two viable mechanisms and both are unpleasant.
Wall-time measurement around the call is the obvious one, but
`time.perf_counter()` granularity around 100µs is fine on Linux and
macOS, and the call overhead of the timer itself becomes a
non-trivial fraction of the budget. Worse: wall-time can't *abort*
a runaway Predicate — by the time you've measured "this Predicate
took 5ms," it has already taken 5ms. R-RISK-3 acknowledges this with
"wall-time measurement with hysteresis (quarantine after k
consecutive violations)" — which prevents repeated stalls but does
nothing about the first stall. If the first stall is in an
`input_builder`, you've held up the writer arbitrarily.

The alternative is `sys.settrace`/`sys.setprofile` to interrupt at
instruction granularity, but the overhead of running with a tracer
enabled is roughly 10×. That breaks N-PERF-1 by itself.

The deeper issue: "Predicates are host-language callables" (Decision
#5 in v14) is load-bearing for substrate expressiveness, but it's
exactly the wrong choice for reliable budget enforcement. A
composable predicate algebra over a fixed set of operators would let
the runtime statically bound cost. The current product spec
inherits the v14 stance and waves at the implementation —
"technical spec decides." It doesn't acknowledge that "technical
spec decides" might force a revision of v14 Decision #5.

**Action:** elevate F-PRED-1 from a functional requirement to an
open design question in DRAFT 2. Sketch the candidate mechanisms in
§11. Don't commit to the predicate-as-arbitrary-callable shape until
prototyping enforcement on real Predicates at N-PERF-1 throughput.

## 2. "No thin-slice MVP" commitment is unargued — risk-changing

§2 asserts strongly: "There is no thin-slice MVP that ships half a
substrate — half a substrate orchestrates nothing." That's a stance,
not an argument. The implicit reasoning is that the value emerges
from kernel semantics + replay + composition + persistence all
working together — true — but the spec doesn't say so, and it
doesn't bound the cost.

If v1.0 takes six months, fine. If it takes 18 months without any
external validation along the way, that's a real risk to the
project. Open-source momentum dies in long gaps between release and
validation. The Factory v0 document built validation into its plan
by having existing projects (Trading System, Audio Object,
Katybird, MMT1) adopt the libraries as they shipped. The product
spec has no equivalent: the reference topologies are CI acceptance
tests, not external validators.

**Action:** either argue the all-at-once commitment concretely
(estimate v1.0 timeline; name what breaks if you slice; show the
smallest slice that orchestrates *something*) or define one or two
milestones short of v1.0 where the kernel is usable enough that
someone outside the substrate team can build a real topology
against it.

## 3. §3 has no spec maintainer / spec owner role

Three-document set plus conformance suite plus codebase. Who
decides when v14 becomes v15? Who arbitrates when the conformance
suite and the spec disagree (which §4 principle #1 says is a
release blocker)? Who has authority to add a v14 decision after
release without it being a backward-incompatible kernel change?

The omission matters because §4 principle #1 ("the spec is the
contract") puts weight on the spec staying authoritative. Without
an explicit maintainer role, every decision involves consensus
among everyone who's read the docs, and that consensus is slow and
lossy. Topology authors will reason from the spec; if the spec has
a question and no decider, they'll diverge.

**Action:** add a fourth user persona — "the spec maintainer" —
who owns the v14, product, and technical docs as a connected
corpus, and is the authority of last resort when code and spec
disagree. They can be the same person as the topology author /
operator, but the role needs to exist.

## 4. N-PERF-1 is suspicious

5,000 cycles/sec with 50 Predicates and 10 Views. Arithmetic:
validation (msgspec at ~1µs/event) + 10 View updates (~0.5µs each
conservative) + 50 Predicate evaluations + Route evaluation: at
200µs/cycle (the budget for 5,000 cycles/sec), you have 5µs for
validation + Views + Routes, and 195µs spread across 50 Predicates
= 3.9µs/Predicate. That's plausible if most Predicates short-circuit
on a subscription filter (event-kind mismatch returns False
instantly) and only a few actually evaluate.

But the spec doesn't say so. The number assumes subscription
filtering is doing most of the work, while the F-PRED-1 budget of
100µs/call describes the worst case. If you read N-PERF-1 naively
— "50 Predicates each evaluating substantively against the budget"
— you need 200µs × 50 = 10ms/cycle = 100 cycles/sec, two orders of
magnitude off the stated target.

The throughput claim is fine if the assumptions behind it are
stated. "Cycles/sec" without saying what fraction of Predicates
actually run is a load-bearing omission.

**Action:** restate N-PERF-1 with explicit assumptions about
subscription filtering. Or replace cycles/sec with a more meaningful
metric: events per second under a stated topology shape.

## 5. Input immutability (F-PROD-3) is not actually enforceable in Python

"deep-frozen or copied" — neither works for arbitrary Python objects.
You can freeze tuples and frozensets, you can wrap dicts in
`MappingProxyType` (which is a *view*, not a freeze — the
underlying dict can still mutate), you can rebind `__setattr__` on
user classes at runtime (fragile, breaks descriptors), or you can
deep-copy at instantiation (paying the copy cost forever).

R-RISK-2 admits this: "inputs are msgspec/Pydantic models by
convention; technical spec defines the sealing mechanism and its
documented limits." But F-PROD-3 reads as a MUST contract: "Input
immutability MUST be enforced." If enforcement is "by convention,"
the MUST is a fiction. Either:

(a) Tighten the contract: "inputs MUST be `msgspec.Struct(frozen=True)`
or `pydantic.BaseModel(frozen=True)`; the runtime rejects other
input types at instantiation." Then F-PROD-3 is real.

(b) Be honest: "the runtime makes a best-effort defensive copy at
instantiation; nested mutable state remains the topology author's
responsibility." Then F-PROD-3 is a SHOULD with caveats.

The third option — pretending you can deep-freeze arbitrary Python
— is worse than either.

**Action:** pick (a) and document it as a constraint on Producer
kind authorship, or pick (b) and rewrite F-PROD-3.

## 6. Schema evolution / upgrade story is missing

Persistent buses (F-PERS-2) outlive runs. Vocabulary evolves. A
persistent bus written against schema v1 of a Producer kind needs to
be readable when the codebase moves to schema v2 — at minimum for
replay; ideally for cross-run pattern work.

The product spec doesn't address:

- How does a topology declare `schema_version` on a Producer kind?
- What's the migration story when an old persistent bus is loaded by
  new code?
- Does Level 1 replay work across versions? Level 2?
- Can a single run mix Producer kinds at different schema versions
  (e.g., during a migration)?

The Factory v0 doc handled this with explicit "vocabulary version"
semantics and seven typed proposal types for evolution. The
substrate spec inherits the problem without naming it.

**Action:** add an explicit schema-versioning section. Even if the
answer is "schemas are fixed for a run; persistent buses pin the
schema version they were written against and you migrate
explicitly," it needs to be stated.

## 7. O-1 is a near-term blocker disguised as a deferred decision

§4 principle #7 says "open source from day one." N-OSS-1 says "Repo
public from first release." Both require a license to be chosen
*before any commit ships in a public repo*. O-1 ("MIT vs Apache-2.0")
is filed as an open question. But it's not actually deferrable — it
has to be resolved before the first git push, not before v1.0.

The spec presents it as on the same timeline as O-3 (schema library)
and O-5 (TriggerFired payload handling), which are genuinely v1.0
decisions. O-1 needs to be hoisted to a pre-everything blocker.

**Action:** resolve O-1 in DRAFT 2 (the patent grant argument for
Apache-2.0 is strong for a substrate that other people may build
derivative implementations of) or label it as a
"must-resolve-before-first-public-commit" blocker.

## 8. Conformance check 6 ("Replay round-trip") needs tighter language

"Level 3(b) substitution re-executes to an equivalent log." What's
"equivalent"? Sequence-by-sequence byte-identical? Outcome-identical
(same `RunFinalised`)? Causally-identical (same Triggers fired in
the same order)?

If concurrent Producers' admission order is recorded as scheduling
nondeterminism in the original run, and Level 3(b) replays that
order via substitution, the resulting log should be byte-identical
event-by-event (which matches N-DET-1). If "equivalent" allows
reordering, then N-DET-1 and check 6 are saying different things,
and that's confusing.

**Action:** state byte-identical and align with N-DET-1.

## 9. R-3 has two modes and the spec should say so

"A writer Producer streams code" — with deterministic stand-ins this
works in CI. With a real LLM this is the actually-interesting case.
The value of R-3 is demonstrating real LLM-streaming-overlap with
tree-sitter, not deterministic stand-ins streaming. The CI run
sanitizes away the thing that makes R-3 worth shipping.

That's fine *if* the spec says so. Right now §8 reads as though R-3
is a single test that works in CI. In practice it's two tests: a CI
version with deterministic stand-ins (proves wiring) and a
walkthrough version with real LLMs (proves the claim about overlap).
Both should exist.

**Action:** §8 should explicitly note dual-mode testing for R-3
(and probably R-1 also, since "N seeded Producers (deterministic
stand-ins in CI; local LLMs in the walkthrough)" already hints at it
but doesn't make it a requirement).

## 10. Performance regression gate is missing from §7

§7 lists ten conformance checks as release gates. N-PERF-1 is
verified in CI per §12 but it's not in the conformance suite. That
means: a code change that passes functional conformance but degrades
throughput 5× silently ships. The "verified in CI" gate is binary
(does CI pass at all) and CI passes if N-PERF-1 is met *at all*, not
if it's met *as well as the previous release*.

For a substrate where performance is load-bearing on the predicate
budget enforcement, performance regression detection has to be a
release gate, not a CI smoke test.

**Action:** add a perf gate to the conformance suite that checks
N-PERF-1 *relative to the previous release tag*, not just
absolutely.

## Smaller issues

- **F-CLI-5 (`substrate tail`) is too minimal.** Operators will need
  filtering by event kind, by Producer, and at minimum a
  `--since <seq>` flag. The spec says the UI is out of scope, but a
  useful tail needs the basic flags. Either extend F-CLI-5 or be
  explicit that operators are expected to pipe through jq/grep
  externally.

- **F-COMP-3 ("Nesting depth is unbounded") doesn't acknowledge RAM
  cost.** Each embedded substrate is a full kernel instance with its
  own writer, admission queue, hot tail, and Views. 10 levels deep
  is 10× the per-runtime overhead. For self-modifying or
  meta-orchestration patterns this may matter. Not a blocker, but
  worth a note.

- **N-PORT-1 ("Windows best-effort") plus F-PERS-2 (persistent bus
  with flock) is a correctness risk.** If two runtimes race against
  a Windows persistent bus and the PID-file fallback has a TOCTOU
  window, the bus corrupts. "Best-effort" is too soft for a
  correctness primitive. Either state that persistent buses aren't
  supported on Windows in v1.0, or commit to the locking working
  there.

- **F-API-3 (no model SDK in core) needs a sibling clause for
  examples.** Where do the LLM Producer adapters for the walkthroughs
  live? In an extras package? In a separate `substrate-examples`
  repo? The spec is silent.

- **§4 principle 7 ("Open source from day one") doesn't argue the
  rationale.** Factory v0 had a clear theory of moat (libraries
  open, accumulated work proprietary). What's substrate's theory?
  Defensibility comes from the spec being canonical and the
  conformance suite being authoritative? Community-building? Hiring
  signal? Without a stated rationale, the OSS commitment is just a
  vibe.

## Net take

The spec is unusually clear and well-structured for a DRAFT 1. The
requirement IDs are stable, the conformance gate is a real gate, the
reference topologies cover the kernel meaningfully. The work is
good.

The two issues that could change the shape of the product are (1)
F-PRED-1 budget enforcement — which might force a revision of the
predicate-as-arbitrary-callable decision in v14 — and (2) the no-MVP
commitment, which loads a lot of risk onto one release. Everything
else is tightening.

If the technical spec resolves F-PRED-1 cleanly (probably by
tightening what counts as a valid Predicate, plus aggressive
subscription filtering, plus hysteresis-based quarantine) and the
project has a credible path to first external validation before
full v1.0 (probably by shipping `substrate-kernel` as a separable
package that real topology authors can build against while the CLI
and replay layers are still in flux), the rest of the issues are
normal spec-tightening, not architectural.

## Issues by destination

For DRAFT 2 of the product spec:
- §1 F-PRED-1 elevated to open question
- §2 no-MVP argument or milestone definition
- §3 spec maintainer persona
- §4 N-PERF-1 assumptions stated
- §5 F-PROD-3 tightened or honestly weakened
- §6 schema-versioning section added
- §7 O-1 resolved or hoisted
- §8 conformance check 6 language tightened
- §9 R-3 dual-mode testing made explicit
- §10 perf regression added to conformance gate
- Smaller fixes listed above

For the technical spec:
- F-PRED-1 mechanism (with the v14-revision possibility on the
  table)
- F-PROD-3 sealing mechanism
- F-PERS-2 Windows locking
- TriggerFired payload handling (O-5)
- Schema version migration mechanics

Back into v14:
- Decision #5 (Predicate language) may need revision if F-PRED-1
  enforcement forces a constraint.
- A note on schema versioning in the persistent-bus opt-in
  (Decision #4).
