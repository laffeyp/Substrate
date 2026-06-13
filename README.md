# Substrate

A concurrent streaming dataflow runtime: an importable Python 3.12+ library plus
a CLI. You bring computations — LLMs, ML models, deterministic transforms,
subprocesses, simulators, parsers, sensors — as **Producers** that take typed
input and emit a stream of typed **Events**; the runtime runs them concurrently,
coordinates them through a single totally-ordered append-only **Bus**, and
creates new Producers dynamically when **Predicates** over **Views** of the log
are satisfied (**Triggers**). **Routes** carry data into future instantiations;
a **TerminationPolicy** decides when the run ends. The load-bearing commitment:
*all state lives on the log, and nothing consequential is silent* — the persisted
**run record** is the canonical account of what happened.

Working name "substrate" (official package name deferred — B-Q-1). Apache-2.0.

## Spec corpus

This package implements a four-document spec corpus (in this repo):

- `kernel_spec/v15.md` — the eight primitives, the append cycle, replay (+ `v16_reconciliation_note.md`).
- `product_spec/draft7.md` — requirements, the 17 conformance checks, reference topologies.
- `technical_spec/draft5.md` — byte layout, writer cycle, public API.
- `design_spec/draft1.md` — API ergonomics, CLI UX, error UX.

Built under Signal-Driven Development (`../sdd-kit-2/`); the locked signal
vocabulary is `signals/0.2.json` (additive successor to `signals/0.1.json`, which
is retained as the v0.1 audit trail — see `signals/0.2-rationale.md`). Spec
amendments: `product_spec/draft7_amendment_A1_replay_3b.md` (replay 3b deferral +
D-8 exclusion set), `product_spec/draft7_amendment_A2_nperf1.md` (N-PERF-1 floor).
Implementation roadmap: `sprints/PHASE1_PLAN.md`.

## What "replay" means (read this before relying on it)

The product surface is the **run record** — a framed, CRC-protected, RFC 8785
(JCS) canonically-encoded JSONL log. Replay reconstructs from it at four honesty
tiers (`substrate replay <record> --level <1|2|3a|3b>`):

- **Level 1 — state reconstruction.** Re-derive any View's state at any sequence.
- **Level 2 — decision reconstruction.** Every runtime decision and resolved
  input is recorded; Level 2 reads and re-verifies them (input hashes recomputed).
- **Level 3(a) — native re-execution.** Re-run the topology with real Producers;
  precondition-checked (all kinds author-deterministic + replay ceiling `3a`) and
  refuses rather than diverging.
- **Level 3(b) — byte-identical substitution re-execution.** *Deferred to
  post-1.0* (product amendment A1.1): it needs a replay-mode writer that replays
  recorded wall-clock `t` values, not yet built.

**What ships in v1.0:** Levels 1, 2, and 3(a), plus the **D-8 log-equivalence**
relation (`first_divergence` / record diffing — two records are equivalent modulo
supplementary metadata like `t`, run ids, and per-run instance ids). **The
flagship "byte-identical replay" (Level 3(b)) is post-1.0** — do not rely on
byte-for-byte re-execution in v1.0; rely on Levels 1/2/3a + D-8 equivalence, which
are sufficient for state/decision reconstruction, provenance, and divergence
localization. (`substrate replay --level 3b` surfaces the deferral explicitly;
it never silently fakes success.)

## Docs

- **First topology** — a zero-to-working two-Producer topology: `docs/tutorial.md`.
- **Reference topologies (R-1/R-2/R-3)** — CI + real-LLM walkthroughs, with actual
  recorded runs: `docs/walkthroughs/README.md`.
- **API reference** — the public surface (`substrate.api`): `docs/api.md`.
- **Conformance** — `uv run substrate conformance` runs the 17-check release gate.

## Develop

```
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run pytest
```
