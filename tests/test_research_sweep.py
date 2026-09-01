# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Observation contract for research_sweep (sprint 139, application-parity W1.3).

CI: DeterministicResponders drive the map-reduce reproducibly, no network. Asserts the fan-out
(one reader per document), the fan-in (critic once all findings land), the reduce (synthesizer
once), read-only gather, and no lifecycle-kind collisions — on the application's own record.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.applications import gather, research_sweep_topology


def test_gather_is_readonly_and_bounded(tmp_path: Path) -> None:
    a = tmp_path / "a.md"
    a.write_text("alpha content")
    b = tmp_path / "b.md"
    b.write_text("beta content")
    docs = gather([a, b])
    assert docs == [("a.md", "alpha content"), ("b.md", "beta content")]
    # read-only: the files are untouched
    assert a.read_text() == "alpha content" and b.read_text() == "beta content"


def test_map_critique_reduce(tmp_path: Path) -> None:
    documents = [("a.md", "the sky is blue"), ("b.md", "grass is green"), ("c.md", "snow is white")]
    topo = research_sweep_topology(
        "what colors are mentioned?",
        documents,
        reader=DeterministicResponder(seed=0),
        critic=DeterministicResponder(seed=1),
        synthesizer=DeterministicResponder(seed=2),
    )
    result = asyncio.run(api.Runtime(tmp_path / "run").run(topo))
    events = list(api.read_record(tmp_path / "run"))
    kinds = [e["kind"] for e in events]

    assert result.status == "finalised"  # the runtime's own verdict
    assert kinds.count("ReadRequest") == 3  # one request per document
    assert kinds.count("Finding") == 3  # one reader ran per document (map)
    # each finding is over its own source — the readers mapped over DIFFERENT inputs
    sources = {e["payload"]["source"] for e in events if e["kind"] == "Finding"}
    assert sources == {"a.md", "b.md", "c.md"}
    assert kinds.count("Gaps") == 1  # the critic fired ONCE after all findings (fan-in)
    assert kinds.count("Synthesis") == 1  # the synthesizer fired ONCE (reduce)
    # order: all findings precede the gaps, which precede the synthesis
    assert kinds.index("Gaps") > max(i for i, k in enumerate(kinds) if k == "Finding")
    assert kinds.index("Synthesis") > kinds.index("Gaps")
    assert kinds[-1] == "substrate.RunFinalised"
    # F-18: every model call is metered onto the record (3 readers + 1 critic + 1 synthesizer = 5), so
    # the sweep is assayable — an assay reading this record sees the model work, not model_calls=0.
    assert kinds.count("ModelUsage") == 5
    # no invented lifecycle vocabulary — the app kinds are the four Structs + the shared ModelUsage
    known = {"ReadRequest", "Finding", "Gaps", "Synthesis", "ModelUsage"}
    assert not any(k not in known and not k.startswith("substrate.") for k in kinds)


class _FailingReader:
    """A reader that raises on every document — the failed/empty read a real model produces."""

    def respond(self, prompt: str) -> str:
        raise RuntimeError("model unreachable")


class _SpyResponder:
    """Records every prompt and returns a fixed reply — lets a test assert what the model actually SAW.
    DeterministicResponder hashes its prompt, so a content assertion on its OUTPUT is impossible; a spy on
    the INPUT is the direct check that the real input reached the model (review F-11)."""

    def __init__(self, reply: str = "noted") -> None:
        self.prompts: list[str] = []
        self._reply = reply

    def respond(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._reply


def test_the_question_and_the_document_reach_the_reader(tmp_path: Path) -> None:
    # F-11: no test proved real input reaches a model; the reviewer severed the reader input in 12 ways and
    # the suite stayed green. Assert the reader's prompt actually contains the question AND the document
    # content — blanking either (research_sweep.py:85/92) now turns this red.
    spy = _SpyResponder(reply="the sky is blue")
    topo = research_sweep_topology(
        "which colors are named?",
        [("sky.md", "the sky is azure today")],
        reader=spy,
        critic=DeterministicResponder(seed=1),
        synthesizer=DeterministicResponder(seed=2),
    )
    asyncio.run(api.Runtime(tmp_path / "run").run(topo))
    assert len(spy.prompts) == 1
    assert "which colors are named?" in spy.prompts[0]  # the QUESTION reached the reader
    assert "azure" in spy.prompts[0]  # the DOCUMENT CONTENT reached the reader


def test_the_synthesizer_receives_the_findings(tmp_path: Path) -> None:
    # F-13: presence of a Synthesis is not proof it was grounded. Assert the synthesizer's prompt carries
    # the readers' findings — feeding it zero findings (research_sweep.py:123) now turns this red.
    reader = _SpyResponder(reply="mentions the color crimson")
    synth = _SpyResponder(reply="crimson is named")
    topo = research_sweep_topology(
        "which colors?",
        [("a.md", "text a"), ("b.md", "text b")],
        reader=reader,
        critic=DeterministicResponder(seed=1),
        synthesizer=synth,
    )
    asyncio.run(api.Runtime(tmp_path / "run").run(topo))
    assert len(synth.prompts) == 1
    assert (
        "crimson" in synth.prompts[0]
    )  # the findings the readers produced reached the synthesizer


def test_an_empty_read_becomes_the_no_contribution_marker(tmp_path: Path) -> None:
    # F-13: sprint 140.1's card declared "an empty reply becomes (no contribution)"; no test covered it.
    topo = research_sweep_topology(
        "q",
        [("a.md", "content")],
        reader=_SpyResponder(reply="   "),  # a blank reply
        critic=DeterministicResponder(seed=1),
        synthesizer=DeterministicResponder(seed=2),
    )
    asyncio.run(api.Runtime(tmp_path / "run").run(topo))
    events = list(api.read_record(tmp_path / "run"))
    note = next(e["payload"]["note"] for e in events if e["kind"] == "Finding")
    assert note == "(no contribution)"  # the empty-reply fallback, not a bare ""


def test_gather_truncates_a_large_document_with_a_marker(tmp_path: Path) -> None:
    # F-14: the _MAX_DOC_CHARS truncation path was never exercised. A document over the cap must be cut
    # with a visible marker, never a silent mid-content drop.
    big = tmp_path / "big.md"
    big.write_text("x" * 20_000)
    (source, content) = gather([big])[0]
    assert len(content) < 20_000  # bounded
    assert "truncated" in content  # and the cut is announced, not silent


def test_gather_missing_path_raises_not_swallowed(tmp_path: Path) -> None:
    # F-14: gather's declared missing-path behaviour had no test.
    import pytest

    with pytest.raises(FileNotFoundError):
        gather([tmp_path / "does-not-exist.md"])


def test_empty_document_set_raises_not_silent_no_answer() -> None:
    # 2026-08-02 review (F-4 class): an empty corpus produced status=finalised with no Synthesis — the
    # fan-in never fires because no Finding is ever emitted. The library now refuses it at build time,
    # matching the CLI guard, rather than finalising with no answer.
    import pytest

    with pytest.raises(ValueError, match="empty"):
        research_sweep_topology(
            "q",
            [],
            reader=DeterministicResponder(seed=0),
            critic=DeterministicResponder(seed=1),
            synthesizer=DeterministicResponder(seed=2),
        )


def test_a_failed_reader_still_synthesizes_not_a_silent_no_answer(tmp_path: Path) -> None:
    # Regression (sprint 140.1): a reader yielding nothing must not stall the fan-in. Before the fix,
    # one dead reader left findings < n forever — no critic, no synthesis — yet the run finalised, so a
    # caller saw "finalised" and got no answer. Now every ReadRequest yields exactly one Finding (the
    # failure recorded as the note), the fan-in trips, and a synthesis is still produced.
    documents = [("a.md", "sky is blue"), ("b.md", "grass is green"), ("c.md", "snow is white")]
    topo = research_sweep_topology(
        "what colors?",
        documents,
        reader=_FailingReader(),  # every read fails
        critic=DeterministicResponder(seed=1),
        synthesizer=DeterministicResponder(seed=2),
    )
    result = asyncio.run(api.Runtime(tmp_path / "run").run(topo))
    events = list(api.read_record(tmp_path / "run"))
    kinds = [e["kind"] for e in events]

    assert result.status == "finalised"
    assert kinds.count("Finding") == 3  # one per request even though every read failed
    # the failure is recorded on the finding, not swallowed
    assert all("read failed" in e["payload"]["note"] for e in events if e["kind"] == "Finding")
    assert kinds.count("Synthesis") == 1  # the sweep still reaches an answer — no silent no-answer


def test_a_failed_critic_still_reaches_synthesis(tmp_path: Path) -> None:
    # F-4: the review found 140.1 hardened ONLY the reader; a critic that fails left Gaps unemitted, the
    # synthesize trigger never fired, and the run finalised with no Synthesis. Now a failed critic still
    # emits Gaps (a recorded failure), so the reduce fires and the sweep reaches an answer.
    documents = [("a.md", "sky is blue"), ("b.md", "grass is green")]
    topo = research_sweep_topology(
        "what colors?",
        documents,
        reader=DeterministicResponder(seed=0),
        critic=_FailingReader(),  # the critic model is down
        synthesizer=DeterministicResponder(seed=2),
    )
    result = asyncio.run(api.Runtime(tmp_path / "run").run(topo))
    events = list(api.read_record(tmp_path / "run"))
    kinds = [e["kind"] for e in events]
    assert result.status == "finalised"
    assert kinds.count("Gaps") == 1  # emitted despite the failure
    assert any("critic failed" in e["payload"]["note"] for e in events if e["kind"] == "Gaps")
    assert kinds.count("Synthesis") == 1  # the reduce still ran — no silent no-answer


def test_a_failed_synthesizer_still_finalises_with_a_marker(tmp_path: Path) -> None:
    # F-4 (reduce seam): a synthesizer that fails still emits Synthesis (a recorded failure), so the run
    # reaches its terminal with an honest marker rather than the silent-no-answer terminal.
    documents = [("a.md", "sky is blue"), ("b.md", "grass is green")]
    topo = research_sweep_topology(
        "what colors?",
        documents,
        reader=DeterministicResponder(seed=0),
        critic=DeterministicResponder(seed=1),
        synthesizer=_FailingReader(),  # the synthesizer model is down
    )
    result = asyncio.run(api.Runtime(tmp_path / "run").run(topo))
    events = list(api.read_record(tmp_path / "run"))
    kinds = [e["kind"] for e in events]
    assert result.status == "finalised"
    assert kinds.count("Synthesis") == 1
    assert any(
        "synthesis failed" in e["payload"]["text"] for e in events if e["kind"] == "Synthesis"
    )
