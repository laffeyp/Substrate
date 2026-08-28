# Sprint 232b — five remaining Mad Lib templates + fragments

```yaml
---
id: 232b
status: pending
phase: daily-driver-piece-H
pass_kind: docs
---
```

## split rationale

Sprint 232 (parent) shipped the mechanism: interpolator (~180 lines),
one representative template (`default.tmpl.md`), and the `--wizard`
CLI flag on `bundle create`. The five other templates (`code_review`,
`pair_coding`, `best_of_n_verified`, `research_sweep`, `writing`) are
pure data files, each one 30-60 lines of prose. Deferred to this
follow-up so 232 stays ≤2 code files + 1 template + tests (SDD rule 6).

## scope

- `substrate/src/substrate/templates/bundles/code_review.tmpl.md`
- `substrate/src/substrate/templates/bundles/pair_coding.tmpl.md`
- `substrate/src/substrate/templates/bundles/best_of_n_verified.tmpl.md`
- `substrate/src/substrate/templates/bundles/research_sweep.tmpl.md`
- `substrate/src/substrate/templates/bundles/writing.tmpl.md`
- `substrate/src/substrate/templates/bundles/fragments/*.md` — reusable
  fragments the wizard can splice into a template's slot answers
  (methodology-tdd.md, personality-blunt.md, personality-gentle.md,
  per-turn-security-flag.md, etc.).

Each template mirrors `default.tmpl.md`'s shape (YAML `slots:` header
followed by `== bundle.toml ==` / `== methodology.md ==` /
`== personality.md ==` / `== per-turn.md ==` sections). Slot design
per app:

- code_review: rubric, blunt-vs-gentle, per-turn security-flag.
- pair_coding: pair-style choice, delegate-frequency line.
- best_of_n_verified: verifier-strictness choice, retry-budget hint.
- research_sweep: reader-depth choice, synthesis-length line.
- writing: voice choice, tone choice, style-fragment picker.

## artifact contract

Five template files + N fragment files. No code changes.

### Tests

- `test_all_wizard_templates_parse.py` — every template's header
  parses; every template's body renders with a zero-filled values
  dict (proves the templates never reference a slot not in their
  header).

## halt conditions

- `vocabulary_change_required` if a template needs a slot kind beyond
  `text_line`, `text_paragraph`, `bool`, `pick`.
