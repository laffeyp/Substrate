# Sprint 066 — every docstring §-reference resolves in the current spec corpus or leaves the code

```yaml
---
id: 066
status: closed
phase: 8
pass_kind: correctness
closed_at: 2026-09-01
closed_by: substrate main HEAD after this card
scope_note: script-driven sweep across substrate/src and substrate-ui .py files; ~42 fabricated citations removed or generalised across 15+ files. Four .toml application manifest comments retain their §7.3 / §7.6 citations — low visibility, deferred to a follow-up. §14, §20, §22 references verified against draft5.md and kept. Every kernel-spec F-* ID kept verbatim.
---
```

## Product-spec conformance

**Fulfills:** SDD hard rule that a code artifact citing a spec section is making a claim about the spec's contract. The 2026-09-01 audit surfaced fabricated citations: `bundles.py:5` cites `TECH-SPEC §9`, `bundles.py:9` and `roles.py:3` cite `TECH-SPEC §1.6.5`, `roles.py:12` cites `§7b`, `transcript.py:10` cites `TECH-SPEC-2026-08-25-round6 §3a`, `server.py:1133` cites `TECH-SPEC §1.6.5`, `server.py:1145` cites `TECH-SPEC §7 line 674`. None of these sections exist in the current corpus (`docs/specs/technical_spec/draft5.md` + `draft5_amendment_A1.md`; `docs/specs/product_spec/draft7.md` + amendments A1/A2/A3; `docs/specs/kernel_spec/v15.md`). Every citation is a claim that fails to verify.

This sprint audits every docstring §-reference in the substrate + substrate-ui code and applies one of three outcomes per hit.

## Motivation

A false spec citation is worse than no citation. A reader trusts the citation and treats the referenced section as authoritative; when it does not exist, the reader's trust in the whole cross-reference graph drops. SDD depends on the citation graph being real.

The audit already surfaced the shape at the prompt-composition boundary. The scan generalizes: bundles, roles, transcript, per_turn, session-registry, delegate all carry spec citations that need verification.

## Scope

Grep, categorize, apply.

**Grep.** `grep -rn "TECH-SPEC\|tech-spec\|product-spec\|kernel-spec\|§[0-9]" src/ substrate-ui/*.py` (excluding tests). Every hit gets classified.

**Three outcomes per hit:**

1. **Verified — leave.** The cited section exists in the current corpus at the cited number, and the claim the docstring makes is what the section actually says. Leave the citation. Add a `# spec-audit: 2026-09-XX verified` comment on the same line so a future audit skips it cheaply.

2. **Concept exists, citation stale — repair.** The cited concept is real and shipped, but the section number is wrong (spec has been re-numbered, or the concept moved to an amendment). Update the citation to the current section number in the current spec draft. Add a `# spec-audit: 2026-09-XX repaired from <old-ref>` comment naming the drift.

3. **Fabricated — remove.** The cited section does not exist and never did in any draft in `docs/specs/*/history/` either. The concept the citation dresses up is a topology-layer concept the code shipped without spec authority. Remove the citation entirely. If the concept genuinely belongs in the spec corpus (per Architect judgment), open a companion spec-amendment card; do not carry a false citation while the amendment is pending.

**Known hits from the 2026-09-01 audit (starter list):**

| File | Line | Current citation | Verify |
|---|---|---|---|
| `src/substrate/bundles.py` | 5 | TECH-SPEC §9 | drafts have §9 as SIDECAR, not bundles. Fabricated. |
| `src/substrate/bundles.py` | 9 | §1.6.5 | Not in any draft. Fabricated. |
| `src/substrate/topologies/session/roles.py` | 3 | TECH-SPEC §1.6.5 | Fabricated. |
| `src/substrate/topologies/session/roles.py` | 12 | §7b | Not in draft5.md. Fabricated. |
| `src/substrate/topologies/session/transcript.py` | 10 | TECH-SPEC-2026-08-25-round6 §3a | Not a spec version in `docs/specs/`. Fabricated. |
| `src/substrate/topologies/session/transcript.py` | 14 | Product-spec §4a | Not in draft7.md. Fabricated. |
| `substrate-ui/server.py` | 1133 | TECH-SPEC §1.6.5 | Fabricated. |
| `substrate-ui/server.py` | 1145 | TECH-SPEC §7 line 674 | Verify — §7 exists in draft5.md; check for line 674 content match. |
| `substrate-ui/server.py` | 1356 | spec §7b | Fabricated per roles.py:12 read. |

**Not a wholesale ban on §-references.** Kernel-spec `v15.md` uses `F-*` requirement IDs (F-LIFE-2, F-TERM-1, F-OBS-1, etc.); those are real. Every hit against those stays.

## Prerequisites

- No open sprint modifying the spec corpus (`docs/specs/*`).
- The 2026-09-01 audit's starter list from above.

## Context files

- `docs/specs/technical_spec/draft5.md` + `draft5_amendment_A1.md` + `history/draft1.md`-`draft4.md`.
- `docs/specs/product_spec/draft7.md` + amendments A1/A2/A3 + `history/`.
- `docs/specs/kernel_spec/v15.md` + `substrate_v14_kernel.py` + `v16_reconciliation_note.md`.
- `docs/specs/design_spec/draft1.md`.
- `src/` and `substrate-ui/*.py` — the grep targets.

## Artifact contract → Files modified

- Every source file whose §-reference sits in one of the three outcomes gets edited per that outcome. Comment format:
  - Verified: `# spec-audit: 2026-09-XX verified` on the same line or immediately below.
  - Repaired: `# spec-audit: 2026-09-XX repaired from <old-ref>` naming the drift.
  - Removed: no residual comment; the citation is gone.
- `substrate/process/spec-audit-2026-09.md` (new) — a table of every hit, its outcome, and (for repaired/removed) the reasoning. Serves as the record of the sweep so a future contributor can trace why a citation is or is not present.

## Signal contract → Emits

None. Prose correctness sprint, no runtime behavior change.

## Observation contract

- Grep after the sweep: `grep -rn "TECH-SPEC\|§[0-9]" src/ substrate-ui/*.py | grep -v "spec-audit"` returns the set of un-audited hits. That set should be empty (or contain only kernel `F-*` IDs which are their own contract).
- `substrate/process/spec-audit-2026-09.md` exists and lists every hit's outcome.
- Full substrate + substrate-ui test suites still green — no runtime change, only comment and docstring edits.
- No production code file loses semantic content from citation removal (grep the diff for behavior changes; every diff hunk should be a docstring or comment edit).

## Halt conditions

- `spec_ambiguity` if a citation refers to a section that partially matches (concept overlap but not verbatim). Halt and record in the audit table; the Architect decides whether it counts as verified, repaired, or removed.
- `bridge_mapping_required` if the audit surfaces a concept that clearly belongs in the spec corpus but was shipped topology-side without an amendment (bundles, per_turn, role composition). Open a companion sprint card proposing a Product-spec Amendment A4 (or Technical-spec Amendment A2) that lifts the composition primitives into the spec; do not silently repair a citation to a section that would need writing.

## Definition of done

Every docstring in `src/` and `substrate-ui/*.py` that cites a spec section either points at a section that exists (verified or repaired) or does not carry the citation. The audit table under `process/spec-audit-2026-09.md` records every hit's outcome. Zero fabricated citations in the tree.
