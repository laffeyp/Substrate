# Substrate as a tool: Producers that author and run topologies

The tool-using loop (`docs/tool-loop/tool-loop-futures.md`) treats a tool as a leaf — a function the model
calls. This document is about the advanced case: a tool whose execution **is another substrate
run**, and beyond that, a Producer that **authors a new topology** at runtime and runs it. The
substrate stops being only the thing that runs agents and becomes a thing agents *use*.

This is a research document. It separates what ships today, what is one composition away, and what
is a genuine open design question — and it marks each, because the interesting claims here are the
ones that are *not* yet true.

---

## Three meanings of "create topologies at runtime"

The phrase hides three different asks, with three different answers:

1. **Dynamic shape** — a run whose set of *running Producers* grows as it unfolds. **Ships.** This
   is the kernel's recursive-Trigger property: `recursive_decomposition` spawns solvers spawning
   solvers at any depth from one Trigger and a budget. The *structure* (kinds, triggers) is fixed;
   the *instances* are unbounded and data-dependent.

2. **Substrate as a tool** — a Producer whose work is running a whole *inner* topology. **Ships:**
   `embedded_substrate`. Below.

3. **Authoring a new topology from data** — a Producer that emits a topology *spec* and has it
   built and run. **The pieces ship; the composition is the move.** `build_from_spec` +
   `embedded_substrate`. Below.

4. **Modifying a live topology** — adding a kind/trigger/route to a *running* run. **Does not
   ship, by design.** The graph is frozen at `build()`. This is the open research direction, and
   the substrate's own philosophy says how it would have to work if it were built. Below.

---

## What ships: `embedded_substrate` (kernel/composition.py)

An embedded substrate is a Producer whose factory constructs an **inner `Runtime`** at its own
root and runs a complete inner topology, exporting only the inner kinds it maps onto the outer
bus. The inner run has its own record, complete and independent at its own root; a provenance link
ties it to the outer call; backpressure is handled at the export point (outer congestion slows the
embedded Producer's yields, never the inner run).

R-3 (`reference/r3_codesynth.py`) is the worked example: a writer→checker→typecheck pipeline runs
as an embedded substrate that exports only `ArtifactReady` onto a two-stage outer run — no inner
`CodeChunk`/`Declaration`/`substrate.*` kind leaks across the boundary. Read
`docs/walkthroughs/records/r3` (outer) and `r3-inner` (inner) to see two linked, independent
records from one composed run.

**The pattern, applied to the tool-loop.** Make a `tool` Producer's execution an
`embedded_substrate`. Now a "tool" is a whole topology:

```python
# a tool whose result is the verdict of running an ENSEMBLE on the model's sub-question
b.producer_kind(
    "ensemble_tool",
    schemas=[ToolResult],
    factory=lambda: embedded_substrate(
        ensemble_topology(question=...),          # an inner topology, chosen per call
        default_export=ToolResult,                # inner RunFinalised -> outer ToolResult
    ),
    deterministic=False,                          # an inner real-model run is not byte-reproducible
)
```

The meta-agent that falls out: a top-level `tool_loop` whose tools are `run_ensemble`,
`run_debate`, `run_pipeline` — each a shipped topology, each executed as an inner substrate, each
returning its verdict as the `ToolResult` the outer model reads. The model orchestrates *runs*,
not just functions. **Status: every piece ships; the meta-agent topology that wires them is a
sketch.**

---

## What ships, underused: topology from data (`build_from_spec`)

`embedded_substrate` runs an inner topology you wrote in code. The stronger move is letting the
*spec* be data — so a Producer (or a model) can emit a topology and have it run.

The Studio already does exactly this. `substrate-ui/builder.py`'s `build_from_spec(spec)` takes a
dict describing the topology and returns "the actual function the runtime runs — no faking": it
mints a frozen msgspec Struct per authored event kind, a Producer per kind, and wires the views,
triggers, routes, and termination from the spec. The spec is plain data:

```json
{
  "producers":   [{"kind": "reviewer", "emits": ["Critique"], "initial": true}],
  "views":       [{"name": "crits", "kind": "KindCount", "of": "Critique"}],
  "triggers":    [{"id": "adj", "on": "Critique",
                   "predicate": {"view": "crits", "op": ">=", "n": 2}, "starts": "judge"}],
  "termination": {"kind": "any_of",
                  "members": [{"kind": "all_completed"},
                              {"kind": "quiescence_with_watchdog", "seconds": 1}]}
}
```

`build_from_spec` is built only on the public `substrate.api` surface, so it is portable: a core
Producer can call the same translator. Compose it with `embedded_substrate` and you have a
**self-authoring run**:

```
model Producer  --emits-->  TopologySpec (a typed event, the design)
        |
   build Trigger fires a builder Producer
        |
   builder Producer:  topo = build_from_spec(spec);  embedded_substrate(topo)  --runs it-->
        |
   exports the inner verdict back as the model's next observation
```

The model writes the next topology; the runtime builds and runs it; the result comes back on the
log. **Status: `build_from_spec` and `embedded_substrate` ship; emitting a spec as a typed event
and threading it through a builder Producer is the unbuilt composition.** Honest limits today: the
Studio's `build_from_spec` mints *stub* or single-`Responder` Producers from a constrained spec
shape (no `PerKey`, deterministic stubs emit each kind once); a production version needs a richer
spec vocabulary and real model-backed Producers. The constraint is also the safety story — see
below.

---

## The boundary: a live topology is frozen (kernel/topology.py)

You cannot add a kind, trigger, or route to a *running* run. `TopologyBuilder.build()` "freezes and
statically validates" — every trigger's `starts` must name a known Producer kind, every `initial`
must be a known kind — and registration is frozen when the run starts. This is deliberate, and it
buys three things the substrate's value rests on:

- **Static validity.** A run cannot reference a kind that does not exist; the graph is checked
  whole, before a single event.
- **Determinism.** The append-cycle (View update → Route → Predicate → Trigger) evaluates against a
  fixed set of triggers and views; a structure that changed mid-cycle would make "what fired and
  why" ambiguous.
- **Replay.** Level-2 replay verifies every recorded decision by hash against the topology. A
  self-rewriting graph has no fixed topology to verify against.

So in today's substrate, "modify a topology" means **author an amended topology and run it** (a new
run, or an inner run via the two sections above) — not mutate the live one. For most uses that is
the right answer: each run stays statically valid and replayable, and the amendment is just the next
run with a different spec.

---

## The open research direction: event-sourced topology amendment

If live structural change is genuinely wanted — a run that adds a trigger to itself while running —
the substrate's own first principle dictates the only honest way to build it: **make the amendment a
logged decision.** Everything else in the substrate that changes the run is an event on the bus
(a Producer starting, a condition firing, a run ending). A structural change must be too.

The shape:

- A kernel decision event — `substrate.TopologyAmended` — carrying the added kind / trigger / route
  (as the same spec data `build_from_spec` consumes), appended on the bus like any decision.
- The append-cycle reads the *current* topology, which is now the base registration plus every
  `TopologyAmended` applied in seq order. Registration stops being "frozen at build" and becomes
  "append-only, like everything else."
- Replay reconstructs the topology incrementally: re-apply each `TopologyAmended` at its seq, and
  the graph at seq N is deterministic from the log. Determinism and replay are **preserved**,
  because the structural change is itself on the record being replayed.
- Static validation moves from once-at-build to incremental-at-append: an amendment is validated
  against the graph as it stands when the amendment lands (the added trigger's `starts` must name a
  kind known *by then*).

This is consonant with the substrate, not a bolt-on: the topology becomes event-sourced like the
rest of the run. The costs are real and worth stating: incremental validation is more subtle than a
single build-time pass; the kernel's "registration frozen" invariant — currently a strong
simplifier — relaxes; and a topology that amends itself into amending itself needs a budget the same
way recursive spawning does (next section). Whether the capability earns that complexity is the open
question. The point of this section is that **if** it is built, the design is forced: amendment as a
logged, replayable decision, or not at all.

---

## Cross-cutting concerns

**Termination and halting.** A Producer that authors-and-runs topologies, or amends its own, can
fail to terminate. The existing answer generalizes: `recursive_decomposition` bounds unbounded
spawning with a depth-budget Trigger that puts the bound *on the log* (`DepthBudgetExceeded`). A
meta-topology needs the same — a spawn/amendment budget, emitted as a typed event at the boundary,
so the bound is auditable, not silent.

**Safety.** A Producer that runs arbitrary topologies is close to arbitrary code execution. The
mitigation is already in the design: `build_from_spec` consumes a *constrained spec*, not Python —
it can only express the declared primitive shapes (kinds, views, triggers, routes, termination), not
run a shell. That is a capability boundary: the model authors *structure*, and the only code that
runs is the typed Producers the runtime mints. Real side-effecting Producers inside an authored run
still pass the bus-boundary validation (strict validator-extras) and should be sandboxed and
capability-scoped per inner run. Authoring structure is safer than `eval`-ing actions precisely
because the runtime, not the model, owns execution.

**Provenance.** Nested and authored runs compose under `trace_ancestry`: the spec-emitting event is
the parent of the run it produced, the inner run's root links back to the outer call, and
`first_divergence` still diffs any two records. A three-level meta-agent (outer loop → authored
inner run → its own sub-tools) is a tree of linked records, each independently replayable.

**Determinism tiers.** An inner run over real models is `deterministic=False` (like `coding_flow`);
it still produces a complete replayable record at its own root, just not byte-identical
re-execution. The *outer* orchestration — which spec was emitted, which builder fired, which inner
verdict returned — stays on the outer log and is replayable regardless of the inner's tier.

---

## Prior art, and what is different here

The agent field has a name for letting a model's action space be code: **code-as-action** (CodeAct
and kin), where the agent writes Python and an interpreter runs it. It is capable and dangerous —
arbitrary execution, no replay, no typed boundary. Actor systems (Erlang's `spawn`) give dynamic
process creation; self-modifying programs and reflection give live mutation; dynamic dataflow
frameworks give runtime graph construction.

The substrate's version differs on the axes that matter for an agent you have to *trust and debug*:
the action is a **typed topology spec, not arbitrary code**; execution is owned by the **runtime,
not the model**; every authored run, every spawn, and (under the research direction) every amendment
is a **logged, replayable decision**. You get the expressive power of an agent that builds its own
machinery, with a record that tells you exactly what it built and what that machinery then did. That
combination — runtime authorship that is still replayable and auditable — is the thing worth
building toward.

---

## Status summary

| Capability | Mechanism | Status |
|---|---|---|
| Dynamic, data-dependent spawning | recursive Trigger + budget | ships (`recursive_decomposition`) |
| Substrate as a tool (inner run) | `embedded_substrate` | ships (R-3) |
| Topology authored from data | `build_from_spec` (Studio) | ships in substrate-ui; portable (api-only) |
| Self-authoring run (emit spec → build → run) | spec event + builder Producer + `embedded_substrate` | composition unbuilt |
| Meta-agent (tool_loop whose tools are runs) | tool-loop + `embedded_substrate` | sketch |
| Live structural self-modification | `substrate.TopologyAmended` as a logged decision | open research |
