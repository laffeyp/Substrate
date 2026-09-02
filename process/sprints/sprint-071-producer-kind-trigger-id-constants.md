# Sprint 071 — producer-kind + trigger-id `Final[str]` constants + frozenset mirrors

```yaml
---
id: 071
status: open
phase: 9
pass_kind: string-discipline
---
```

## Product-spec conformance

**Fulfills:** string-literal discipline drift classes 2 (producer-kind names, ~60 sites) and 3 (trigger IDs, ~30 sites). Not `StrEnum` candidates — a downstream topology can extend the set (a future application could add its own producer kinds). Idiom: module-level `Final[str]` constants + `frozenset` mirror, matching `topologies/session/vocabulary.py`'s existing `SESSION_STARTED = "SessionStarted"` + `SESSION_KINDS` pattern.

**Consumes:** `docs/design/string-literal-discipline.md` § "Correct Python usages" #3. Sprint 070's StrEnum landings for the closed-set values.

## Motivation

Session-topology producer kinds and trigger IDs are stable identifiers with a well-known set at each level (kernel primitives + session topology + tool_loop topology + any application). Every `b.producer_kind("model", ...)` registration and every `_producer_kind_from_ref(ctx) == "model"` predicate today spells the string raw. Rename a producer kind: fifteen sites to edit; one miss and a predicate silently never fires.

Sprint 068 already showed the shape works — `FRAGMENT_SOURCE_KINDS: frozenset[str]` covers the seven fragment-source producer kinds; the `warn-on-fragment-error` trigger reads the frozenset. Sprint 071 generalises: every producer_kind name and every trigger_id gets a `Final[str]` constant + a domain-scoped frozenset.

## Scope

Two new blocks in `topologies/session/vocabulary.py` (or a sibling `identifiers.py` if the vocabulary module bloats). One sweep across every `b.producer_kind(...)` and `b.trigger(...)` call in `session_topology` + `ci_session_topology`. One sweep across every `_producer_kind_from_ref(ctx) == "..."` predicate.

### Session-topology producer kinds

```python
# vocabulary.py — additions
from typing import Final

# Session-topology producer kinds (session/__init__.py::session_topology).
PRODUCER_KIND_SESSION_STARTED: Final[str] = "session_started"
PRODUCER_KIND_MODEL: Final[str] = "model"
PRODUCER_KIND_TOOL: Final[str] = "tool"
PRODUCER_KIND_PARK: Final[str] = "park"
PRODUCER_KIND_SESSION_END: Final[str] = "session_end"
PRODUCER_KIND_SESSION_WARNING: Final[str] = "session_warning"
PRODUCER_KIND_FRAGMENT_ERROR_WARNING: Final[str] = "fragment_error_warning"
PRODUCER_KIND_SESSION_OPEN: Final[str] = "session_open"
PRODUCER_KIND_PROMPT_COMPOSER: Final[str] = "prompt_composer"
PRODUCER_KIND_PER_TURN_FRAGMENT: Final[str] = "per_turn_fragment"
PRODUCER_KIND_ROLE_FRAGMENT: Final[str] = "role_fragment"
PRODUCER_KIND_BUNDLE_METHODOLOGY_FRAGMENT: Final[str] = "bundle_methodology_fragment"
PRODUCER_KIND_BUNDLE_PERSONALITY_FRAGMENT: Final[str] = "bundle_personality_fragment"
PRODUCER_KIND_PARENT_CONTEXT_FRAGMENT: Final[str] = "parent_context_fragment"
PRODUCER_KIND_TOOLS_SUITE_FRAGMENT: Final[str] = "tools_suite_fragment"
PRODUCER_KIND_USER_MESSAGE_FRAGMENT: Final[str] = "user_message_fragment"

SESSION_PRODUCER_KINDS: Final[frozenset[str]] = frozenset({
    PRODUCER_KIND_SESSION_STARTED, PRODUCER_KIND_MODEL, PRODUCER_KIND_TOOL,
    PRODUCER_KIND_PARK, PRODUCER_KIND_SESSION_END, PRODUCER_KIND_SESSION_WARNING,
    PRODUCER_KIND_FRAGMENT_ERROR_WARNING, PRODUCER_KIND_SESSION_OPEN,
    PRODUCER_KIND_PROMPT_COMPOSER, PRODUCER_KIND_PER_TURN_FRAGMENT,
    PRODUCER_KIND_ROLE_FRAGMENT, PRODUCER_KIND_BUNDLE_METHODOLOGY_FRAGMENT,
    PRODUCER_KIND_BUNDLE_PERSONALITY_FRAGMENT, PRODUCER_KIND_PARENT_CONTEXT_FRAGMENT,
    PRODUCER_KIND_TOOLS_SUITE_FRAGMENT, PRODUCER_KIND_USER_MESSAGE_FRAGMENT,
})
```

Sprint 068's existing `FRAGMENT_SOURCE_KINDS` frozenset becomes a subset built from the named constants: `frozenset({PRODUCER_KIND_PER_TURN_FRAGMENT, PRODUCER_KIND_ROLE_FRAGMENT, ...})`.

### Session-topology trigger IDs

```python
# vocabulary.py — additions
TRIGGER_ID_RUN_TOOL: Final[str] = "run-tool"
TRIGGER_ID_CONTINUE: Final[str] = "continue"
TRIGGER_ID_WRAP_UP: Final[str] = "wrap-up"
TRIGGER_ID_PARK_ON_FINAL: Final[str] = "park-on-final"
TRIGGER_ID_PARK_ON_MODEL_ERROR: Final[str] = "park-on-model-error"
TRIGGER_ID_PARK_ON_INTERRUPT: Final[str] = "park-on-interrupt"
TRIGGER_ID_RESUME_ON_COMPOSED: Final[str] = "resume-on-composed"
TRIGGER_ID_END_ON_EXIT: Final[str] = "end-on-exit"
TRIGGER_ID_END_ON_CAP: Final[str] = "end-on-cap"
TRIGGER_ID_END_ON_USER_END: Final[str] = "end-on-user-end"
TRIGGER_ID_EMIT_PER_TURN_FRAGMENT: Final[str] = "emit-per-turn-fragment"
TRIGGER_ID_EMIT_USER_MESSAGE_FRAGMENT: Final[str] = "emit-user-message-fragment"
TRIGGER_ID_COMPOSE_ON_COHORT_COMPLETE: Final[str] = "compose-on-cohort-complete"
TRIGGER_ID_WARN_ON_FRAGMENT_ERROR: Final[str] = "warn-on-fragment-error"

# CI-wrapper trigger (session/ci.py)
TRIGGER_ID_ADVANCE_ON_PARK: Final[str] = "advance-on-park"

SESSION_TRIGGER_IDS: Final[frozenset[str]] = frozenset({...all of the above...})
```

### Sweeps

- `b.producer_kind("model", ...)` → `b.producer_kind(PRODUCER_KIND_MODEL, ...)`. Same for every producer registration.
- `b.trigger("resume-on-composed", ...)` → `b.trigger(TRIGGER_ID_RESUME_ON_COMPOSED, ...)`. Same for every trigger registration.
- `_producer_kind_from_ref(ctx) == "model"` → `_producer_kind_from_ref(ctx) == PRODUCER_KIND_MODEL`. Same for every predicate.
- `producer.kind in FRAGMENT_SOURCE_KINDS` — already correct; the constant now composes from named symbols.
- `tests/test_session_topology_e2e.py:207` — `{"resume-on-composed", ...} <= trigger_ids` → `{TRIGGER_ID_RESUME_ON_COMPOSED, ...} <= trigger_ids`.

## Prerequisites

- Sprint 070 closed (StrEnum idiom + msgspec verification landed).
- No open work modifying `topologies/session/vocabulary.py` or `session_topology`'s trigger set.

## Context files

- `docs/design/string-literal-discipline.md` § "Correct Python usages" #3 + patterns A and F.
- `src/substrate/topologies/session/vocabulary.py` — existing home for kind constants; two new blocks land here.
- `src/substrate/topologies/session/__init__.py` — every producer_kind + trigger registration.
- `src/substrate/topologies/session/ci.py` — CI-wrapper trigger `advance-on-park`.
- `tests/test_session_topology_e2e.py:207` and any other test asserting on trigger_id / producer_kind literals.

## Artifact contract → Files modified

- `src/substrate/topologies/session/vocabulary.py` — two new blocks (PRODUCER_KIND_* and TRIGGER_ID_*) + two frozenset mirrors; existing `FRAGMENT_SOURCE_KINDS` rebuilt from the new constants.
- `src/substrate/topologies/session/__init__.py` — every literal producer_kind / trigger_id in `b.producer_kind(...)`, `b.trigger(...)`, and every predicate that compares against them.
- `src/substrate/topologies/session/ci.py` — advance-on-park trigger + any other CI-wrapper additions.
- Tests updated to import + reference named constants.

## Signal contract → Emits

None. The wire strings unchanged. Only Python-surface identifiers gain names.

## Observation contract

- Full suite green.
- Grep verification: `grep -rn '"model"\|"tool"\|"park"\|"session_end"\|"session_warning"\|"per_turn_fragment"\|"role_fragment"\|"bundle_methodology_fragment"\|...' src/substrate/topologies/session/ | grep -v "vocabulary\.py\|test_\|# "` returns zero producer_kind literals outside vocabulary.py's declaration.
- Same grep for trigger IDs returns zero.
- `SESSION_PRODUCER_KINDS` and `SESSION_TRIGGER_IDS` sets each contain the correct count (17 + 15 respectively).

## Halt conditions

- `bridge_mapping_required` if a producer_kind or trigger_id is used in a way that requires the literal (e.g., interpolated into an error message). Case-by-case: an error message can reference the constant via f-string; no code-path change.
- `spec_ambiguity` if sprint 068's `FRAGMENT_SOURCE_KINDS` predicate depends on a specific hash-order over the seven kinds. Read the predicate; frozenset membership is order-independent.

## Definition of done

Every producer_kind name and every trigger_id in the session topology is a `Final[str]` constant in `vocabulary.py`, imported at the call site. `SESSION_PRODUCER_KINDS` and `SESSION_TRIGGER_IDS` frozenset mirrors exist. Grep finds zero literal producer_kind or trigger_id strings in code outside `vocabulary.py`.
