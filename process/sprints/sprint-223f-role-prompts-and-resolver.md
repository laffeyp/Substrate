# Sprint 223f — role-prompt files + four-layer resolver (piece A dependency)

```yaml
---
id: 223f
status: closed
phase: piece-B-gap-fill
pass_kind: functional
---
```

## scope

TECH-SPEC §1.6.5 (line 144) assigns role-prompt files to piece A:
`substrate/src/substrate/topologies/session/prompts/<role>.md`. Piece B's
`role` field on POST /api/session (sprint 223a) depends on being able to
resolve a role name to a prompt string. This card ships the piece-A
minimum piece B needs: one `default.md` prompt file + the four-layer
resolver at `substrate/src/substrate/topologies/session/roles.py`.

The four layers, in resolution order (spec lines 171-176):

1. `<repo>/.substrate/prompts/<role>.md` (or `<role>/*.md` folder shape)
2. `~/.substrate/prompts/<role>.md` (or folder shape)
3. `substrate/src/substrate/topologies/session/prompts/<role>.md`
4. Not found → `RegistrationError("no role prompt found for --role <name>")`

Folder shape (§7b): if `<role>/` is a directory, concatenate its `*.md`
files in lexical order. Both a bare `.md` and a folder at the same layer
is an error (ambiguous).

## prerequisites

None. Piece A predates piece B in the arc; this card lands the piece-A
slice piece B cannot proceed without.

## artifact contract

### Files

- `substrate/src/substrate/topologies/session/prompts/default.md` — the
  `default` role prompt. One-line minimum: "You are a general-purpose
  agent." Substrate ships nothing more opinionated for `default`.
- `substrate/src/substrate/topologies/session/roles.py` — one function
  `resolve_role_prompt(role: str, *, repo_root: Path | None = None) -> str`.

### Assertions

- `resolve_role_prompt("default")` returns the shipped `default.md` text.
- Layer 1 (repo) wins over layer 2 (user home) wins over layer 3 (shipped).
- Folder shape: three files `a.md`, `b.md`, `c.md` in `<role>/` concatenate
  in that order, one blank line between.
- Both `<role>.md` and `<role>/` at the same layer → `RegistrationError`.
- Missing at all four → `RegistrationError` naming the role.

### Tests

- `substrate/tests/test_role_prompt_resolver.py` — six cases: default
  shipped, layer precedence (three), folder-shape concatenation, ambiguous
  same-layer, not-found.

## observation contract

`uv run python -c "from substrate.topologies.session.roles import
resolve_role_prompt; print(resolve_role_prompt('default'))"` prints the
shipped default prompt.

## halt conditions

- `dual_contract_fail` if resolver returns bytes not present on disk.
- `vocabulary_change_required` if folder-shape needs a manifest.
