"""Observation contract for research_sweep (sprint 139, workflow-parity W1.3).

CI: DeterministicResponders drive the map-reduce reproducibly, no network. Asserts the fan-out
(one reader per document), the fan-in (critic once all findings land), the reduce (synthesizer
once), read-only gather, and no lifecycle-kind collisions — on the workflow's own record.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.workflows import gather, research_sweep_topology


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
    # no invented lifecycle vocabulary — the app kinds are the four topology-local Structs only
    known = {"ReadRequest", "Finding", "Gaps", "Synthesis"}
    assert not any(k not in known and not k.startswith("substrate.") for k in kinds)


class _FailingReader:
    """A reader that raises on every document — the failed/empty read a real model produces."""

    def respond(self, prompt: str) -> str:
        raise RuntimeError("model unreachable")


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
