# Substrate spec corpus

Four documents form the connected corpus for the Substrate project.
Read in order if new; cross-reference freely.

| File | What it is | Current draft |
|---|---|---|
| `horizon_substrate.md` | Kernel semantics (the abstract substrate, eight primitives, append cycle) | v15 |
| `product_spec.md` | The product that ships the kernel (requirements, conformance gate, reference topologies) | DRAFT 7 |
| `technical_spec.md` | The implementation contract (byte layout, writer cycle, public API) | DRAFT 5 |
| `design_spec.md` | The felt experience (API ergonomics, CLI UX, error UX, future UI sketches) | DRAFT 1 |

## Reading order for someone new

1. **`horizon_substrate.md`** — what the substrate is conceptually.
2. **`product_spec.md` Part I (§0)** — concrete worked example, eight primitives in plain language, what the bus is on disk.
3. **`product_spec.md` Part II** — formal requirements, conformance suite, reference topologies.
4. **`technical_spec.md`** — what gets built, byte-level.
5. **`design_spec.md`** — what it feels like to use.

## Cross-references

Each spec carries:
- A status header with the draft number and what changed.
- "Builds on" links to the other specs it depends on.
- A "Document history" section at the bottom recording the changes per draft.
- (Where applicable) "Flows back into" notes naming what the next revision of the upstream spec should incorporate.

## Archive

`archive/` holds prior drafts and ancillary review documents. When a new draft of any spec is cut, the previous draft should be moved into `archive/` named `<spec>_DRAFT<N>.md` (or `<spec>_v<N>.md` for the kernel spec, which uses `v` rather than `DRAFT`).

Currently in `archive/`:
- `product_spec_DRAFT1_critique.md` — critique notes written against product spec DRAFT 1, which were incorporated into DRAFT 2 and survive in the current DRAFT 7. Kept for reference.

## What this corpus does NOT contain

- Prior draft files of the four specs themselves. Each spec has only ever existed as the single file at the top of this folder; revisions were made in place (the Document History section records what changed each draft). Future revisions should preserve the prior draft to `archive/` before being overwritten.
- The pre-substrate notes (`horizon_multi_agent.md`, `horizon_compositional_grammar.md`, `shared_log_design.md`, etc.) which live one directory up in `notes/`. Those belong to the original recursive-strategy-refinement project, not the Substrate corpus.
