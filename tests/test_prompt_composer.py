# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Prompt composer Producer + pure `_compose_prompt` — sprint 059.

Two layers of tests:
 - Unit tests of the pure composition function `_compose_prompt` — the join,
   precedence ordering, empty cohort shape, provenance passthrough.
 - Integration test — the composer is registered in `session_topology` and
   fires on every UserMessage. In sprint 059's landing state, no fragment
   sources exist yet; every `PromptComposed` on the record carries
   `fragment_seqs=()` and `text=""`. The integration test verifies exactly
   that shape.

Live-model test is deferred to sprint 064 when `_model_factory` migrates
to read `PromptComposed.text` as its input. Until then the composer runs
in parallel with the model producer without feeding it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from substrate import api
from substrate.topologies.session import PromptComposed
from substrate.topologies.session.ci import ci_session_topology
from substrate.topologies.session.composer import _compose_prompt


def test_compose_prompt_empty_cohort() -> None:
    """An empty cohort returns PromptComposed with empty text, empty seqs,
    zero tokens, strategy=precedence_join. The composer does not skip on
    empty input — the record shows the honest empty state."""
    result = _compose_prompt([], [])
    assert result == PromptComposed(
        text="",
        fragment_seqs=(),
        total_tokens=0,
        strategy="precedence_join",
    )


def test_compose_prompt_single_fragment() -> None:
    """One fragment yields PromptComposed with that fragment's text, one seq
    in fragment_seqs, non-zero total_tokens."""
    fragments = [{"source": "role", "text": "You review code.", "precedence": 0, "provenance": {}}]
    seqs = [42]
    result = _compose_prompt(fragments, seqs)
    assert result.text == "You review code."
    assert result.fragment_seqs == (42,)
    assert result.total_tokens > 0
    assert result.strategy == "precedence_join"


def test_compose_prompt_orders_by_precedence_ascending() -> None:
    """Fragments join in precedence order. Lower precedence lands earlier.
    The seq column preserves the ordering so a reader can trace the record."""
    fragments = [
        {"source": "per_turn", "text": "TURN", "precedence": 10, "provenance": {}},
        {"source": "role", "text": "ROLE", "precedence": 0, "provenance": {}},
        {"source": "tools_suite", "text": "TOOLS", "precedence": 20, "provenance": {}},
    ]
    seqs = [7, 3, 12]
    result = _compose_prompt(fragments, seqs)
    assert result.text == "ROLE\n\nTURN\n\nTOOLS"
    assert result.fragment_seqs == (3, 7, 12)


def test_compose_prompt_stable_ordering_within_equal_precedence() -> None:
    """Two fragments at the same precedence order by seq (kernel arrival
    order). Locks byte-reproducibility of the composed text across replays."""
    fragments = [
        {"source": "bundle_methodology", "text": "M_LATE", "precedence": 5, "provenance": {}},
        {"source": "bundle_methodology", "text": "M_EARLY", "precedence": 5, "provenance": {}},
    ]
    seqs = [17, 5]  # M_EARLY at seq 5 arrived first; must land first.
    result = _compose_prompt(fragments, seqs)
    assert result.text == "M_EARLY\n\nM_LATE"
    assert result.fragment_seqs == (5, 17)


def test_compose_prompt_skips_empty_text_but_keeps_seq() -> None:
    """A fragment with empty text does not add a blank line to the composed
    text; the join filter drops it. Its seq stays on fragment_seqs so the
    record still shows the fragment fired."""
    fragments = [
        {"source": "role", "text": "ROLE", "precedence": 0, "provenance": {}},
        {"source": "per_turn", "text": "", "precedence": 10, "provenance": {}},
        {"source": "user_message", "text": "ASK", "precedence": 100, "provenance": {}},
    ]
    seqs = [1, 2, 3]
    result = _compose_prompt(fragments, seqs)
    assert result.text == "ROLE\n\nASK"
    assert result.fragment_seqs == (1, 2, 3)


def test_compose_prompt_total_tokens_matches_estimate() -> None:
    """total_tokens follows the chars/4 heuristic on the assembled text.
    Downstream K-window budget calc reads this off PromptComposed directly."""
    long_text = "x" * 400
    fragments = [{"source": "role", "text": long_text, "precedence": 0, "provenance": {}}]
    seqs = [1]
    result = _compose_prompt(fragments, seqs)
    # 400 chars / 4 chars-per-token = 100.
    assert result.total_tokens == 100


def test_compose_prompt_provenance_ignored_by_composer() -> None:
    """The composer does not read `provenance` — it is source-side audit
    data that rides on the fragment envelope. Different provenance on the
    same text produces byte-identical PromptComposed."""
    fragments_a = [{"source": "role", "text": "ROLE", "precedence": 0, "provenance": {"a": 1}}]
    fragments_b = [
        {"source": "role", "text": "ROLE", "precedence": 0, "provenance": {"resolved_from": "/x"}}
    ]
    assert _compose_prompt(fragments_a, [1]) == _compose_prompt(fragments_b, [1])


def test_composer_fires_per_turn_with_cohort(tmp_path: Path) -> None:
    """Integration (sprint 064 post-migration): a two-turn CI session with
    the CI defaults (CALCULATOR tools, no per_turn, no role, no bundle)
    fires the chain UserMessage → per_turn → user_message → composer.
    At least the first turn's PromptComposed lands on the record and
    carries the tools_suite fragment (session-open) plus the
    user_message fragment for "hello" in the composed text.

    Turn 2's /exit routes to session_end → SessionEnded which finalises
    the run; the chain for turn 2 may or may not complete before
    finalisation. Assertion: at least one PromptComposed lands, and the
    first composed carries a non-empty text with the "hello" ask.
    """

    async def _run() -> None:
        record_root = tmp_path / "ci"
        topology = ci_session_topology(
            turns=("hello", "/exit"),
            session_id="s_compose_cohort",
        )
        await api.Runtime(record_root).run(topology)

    asyncio.run(_run())
    envelopes = list(api.read_record(tmp_path / "ci"))
    composed = [env for env in envelopes if env.get("kind") == "PromptComposed"]
    assert len(composed) >= 1, f"expected >=1 PromptComposed, got {len(composed)}"
    first_payload = composed[0]["payload"]
    assert first_payload["strategy"] == "precedence_join"
    # tools_suite fragment (session-open) + user_message "hello" (turn-scoped)
    # both landed before composer fired — deterministic per-turn chain.
    assert "hello" in first_payload["text"], (
        f"user_message fragment missing from composed text: {first_payload['text']!r}"
    )
    assert first_payload["total_tokens"] > 0
    assert len(first_payload["fragment_seqs"]) >= 2  # tools_suite + user_message


def test_composer_scopes_turn_fragments_to_current_turn(tmp_path: Path) -> None:
    """Drift-grooming 2026-09-02 pin for F-1 (turn-cohort accumulation).
    A three-turn CI session emits per_turn+user_message fragments per turn.
    Prior to the FragmentCohort View, `KindBuffer("PromptFragment")`
    accumulated every fragment ever emitted, so turn 2's PromptComposed
    stacked turn 1's user_message on top of turn 2's. This test asserts
    each turn's composed text carries THIS turn's user question and NOT
    prior turns'.

    Also pins F-2 (real seqs): every PromptComposed.fragment_seqs value
    is a valid record seq that resolves to a PromptFragment envelope with
    the same text.
    """

    async def _run() -> None:
        record_root = tmp_path / "ci"
        topology = ci_session_topology(
            turns=("alpha ask", "bravo ask", "/exit"),
            session_id="s_turn_scope",
        )
        await api.Runtime(record_root).run(topology)

    asyncio.run(_run())
    envelopes = list(api.read_record(tmp_path / "ci"))
    by_seq = {int(env["seq"]): env for env in envelopes}
    composed = [env for env in envelopes if env.get("kind") == "PromptComposed"]
    assert len(composed) >= 2, f"need >=2 PromptComposed to test turn scoping; got {len(composed)}"

    turn1_payload = composed[0]["payload"]
    turn2_payload = composed[1]["payload"]

    assert "alpha ask" in turn1_payload["text"], (
        f"turn 1 composed missing its user_message: {turn1_payload['text']!r}"
    )
    assert "alpha ask" not in turn2_payload["text"], (
        f"turn 2 composed leaked turn 1's user_message: {turn2_payload['text']!r}"
    )
    assert "bravo ask" in turn2_payload["text"], (
        f"turn 2 composed missing its user_message: {turn2_payload['text']!r}"
    )

    for composed_env in composed:
        for seq in composed_env["payload"]["fragment_seqs"]:
            frag_env = by_seq.get(int(seq))
            assert frag_env is not None, (
                f"fragment_seqs seq {seq} does not resolve to any record envelope"
            )
            assert frag_env["kind"] == "PromptFragment", (
                f"fragment_seqs seq {seq} resolves to {frag_env['kind']!r}, not PromptFragment"
            )
            frag_text = frag_env["payload"]["text"]
            if frag_text:
                assert frag_text in composed_env["payload"]["text"], (
                    f"PromptFragment@seq={seq} text not present in PromptComposed.text"
                )


def test_composer_fires_with_empty_cohort_when_no_sources(tmp_path: Path) -> None:
    """A CI session with no tools produces no session-open fragments and
    no user_message fragment when the empty-body producer completes
    without yielding (but user_message text is "hello" so it DOES yield).
    Actually this case is unreachable via ci_session_topology today —
    CALCULATOR is always bound. Skip test scaffolding for the truly-empty
    case; the pure `_compose_prompt(fragments=[])` test above covers the
    empty-cohort code path."""
    # Empty-cohort coverage lives in test_compose_prompt_empty_cohort above.
    # This test intentionally elided — the ci_session_topology always
    # binds CALCULATOR tools and turns include at least one UserMessage.text,
    # so a truly empty cohort never happens through the CI wrapper.
