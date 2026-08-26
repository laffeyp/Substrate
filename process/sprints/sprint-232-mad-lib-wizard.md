# Sprint 232 — Mad Lib wizard + six templates

```yaml
---
id: 232
status: pending
phase: daily-driver-piece-H
pass_kind: architecture
---
```

## scope

Author `substrate/src/substrate/templates/interpolate.py` — ~40-line home-rolled interpolator that substitutes `{{slot_name}}` and evaluates `{% if slot_name %}...{% endif %}` in a template string. No jinja dependency. Ship six templates under `substrate/src/substrate/templates/bundles/`: `default.tmpl.md`, `code_review.tmpl.md`, `pair_coding.tmpl.md`, `best_of_n_verified.tmpl.md`, `research_sweep.tmpl.md`, `writing.tmpl.md`. Each template starts with a YAML-fenced `slots:` block declaring pick / bool / text_line / text_paragraph slots. Ship fragments under `substrate/src/substrate/templates/bundles/fragments/` (methodology-tdd.md, personality-blunt.md, personality-gentle.md, per-turn-security-flag.md, etc.).

CLI: `substrate bundle create <name> --wizard` walks the chosen template's slots (`click.prompt` for each), interpolates the answers into the template, writes `~/.substrate/bundles/<name>/{methodology.md, personality.md, per-turn.md, bundle.toml}` from the rendered output.

## prerequisites

- Sprint 231 closed.
- Sprint 222 closed (CLI `bundle create` verb exists).

## context_files

- Sprint 229 output: `bundles.py`.
- Sprint 222 output: `bundle create` verb.
- `current-design-direction/TECH-SPEC-2026-08-25-round6.md` §9 Mad Lib wizard section.

## artifact contract

### Files

- `substrate/src/substrate/templates/interpolate.py` — new (~40 lines).
- `substrate/src/substrate/templates/bundles/*.tmpl.md` — six new templates.
- `substrate/src/substrate/templates/bundles/fragments/*.md` — fragments.
- `substrate/src/substrate/cli.py` — grow `bundle create` with `--wizard` flag.

### Assertions

- `interpolate.py` handles `{{slot}}` substitution + `{% if slot %}...{% endif %}` conditionals. Nested `{% if %}` not supported (documented).
- Every shipped template parses; its `slots:` block declares only the four kinds.
- `substrate bundle create test --wizard` (piped answers) produces a bundle whose assembled seed matches a committed expected.txt.

### Tests

- `test_interpolator_substitutes_slots.py`
- `test_interpolator_if_conditionals.py`
- `test_wizard_walks_template.py`
- `test_wizard_writes_valid_bundle.py`

## observation contract

Manual: `substrate bundle create team-review --wizard` walks the code_review template; answer 5-7 prompts; open the created bundle dir; verify methodology.md, personality.md, per-turn.md are populated with real prose from the chosen fragments; `bundles.load_bundle("team-review")` reads it back without error.

## halt conditions

- `bridge_mapping_required` if the interpolator grows beyond `{{slot}}` + `{% if %}` and needs jinja.

## definition of done

Interpolator + six templates + wizard verb work. Piece H closes. Daily driver v1's substrate side is complete. Piece G (substrate-ui two-view) is the fast-follow in `substrate-ui/sprints/` starting at 033.
