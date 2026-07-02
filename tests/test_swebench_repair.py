"""Observation contract for the REPAIR phase (sprint 137).

Runs the shared best-of-N + correction loop with the swebench drafter (deterministic stand-in responders)
+ the applier-as-validator (real git clones of a fixture repo). The record is the observable (#24): a
candidate's SEARCH/REPLACE edit is applied to a pristine clone and an AppliedPatch with the git-diff lands.
"""

import subprocess
import tempfile
from pathlib import Path

from substrate.api import Runtime, read_record
from substrate.reference._models import DeterministicResponder
from substrate.topologies.best_of_n import best_of_n_correction
from substrate.topologies.coding_flow import Verdict
from substrate.topologies.swebench_solver.records import AppliedPatch
from substrate.topologies.swebench_solver.repair import (
    repair_drafter_factory,
    repair_validate_factory,
)

_FIX = "# path: m.py\n<<<<<<< SEARCH\n    return x\n=======\n    return x + 1\n>>>>>>> REPLACE\n"
_BAD = "# path: m.py\n<<<<<<< SEARCH\n    return NOPE\n=======\n    return x + 1\n>>>>>>> REPLACE\n"


def _fixture_repo() -> str:
    d = tempfile.mkdtemp()
    (Path(d) / "m.py").write_text("def f(x):\n    return x\n")
    for args in (
        ["git", "-C", d, "init", "-q"],
        ["git", "-C", d, "config", "user.email", "t@t"],
        ["git", "-C", d, "config", "user.name", "t"],
        ["git", "-C", d, "add", "-A"],
        ["git", "-C", d, "commit", "-qm", "base"],
    ):
        subprocess.run(args, capture_output=True, check=True)
    return d


def _applied(events: list[dict]) -> list[dict]:
    return [e["payload"] for e in events if e["kind"] == "AppliedPatch"]


def _outcome(events: list[dict]) -> dict | None:
    return next((e for e in events if e["kind"] in ("Solved", "Exhausted")), None)


async def test_repair_applies_and_emits_applied_patch(tmp_path) -> None:  # type: ignore[no-untyped-def]
    base = _fixture_repo()
    responders = [DeterministicResponder(seed=0, menu=[_FIX])]
    topo = lambda b: best_of_n_correction(  # noqa: E731
        b,
        n=1,
        max_rounds=1,
        draft_factory=repair_drafter_factory(
            responders, spec="make f add 1", edit_context="m.py: def f"
        ),
        validate_factory=repair_validate_factory(base),
        validator_schemas=[Verdict, AppliedPatch],
    )
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))

    applied = _applied(events)
    assert len(applied) == 1
    assert "+    return x + 1" in applied[0]["model_patch"] and applied[0]["creates_file"] is False
    out = _outcome(events)
    assert out is not None and out["kind"] == "Solved"


class _CorrectingResponder:
    """Emits a non-applying edit on the seed round; the correct one once it sees the apply failure fed
    back — drives the correction loop through REPAIR."""

    def respond(self, prompt: str) -> str:
        return _FIX if "PRIOR attempt failed" in prompt else _BAD


async def test_repair_correction_loop_fixes_a_non_applying_edit(tmp_path) -> None:  # type: ignore[no-untyped-def]
    base = _fixture_repo()
    responders = [_CorrectingResponder()]
    topo = lambda b: best_of_n_correction(  # noqa: E731
        b,
        n=1,
        max_rounds=2,
        draft_factory=repair_drafter_factory(
            responders, spec="make f add 1", edit_context="m.py: def f"
        ),
        validate_factory=repair_validate_factory(base),
        validator_schemas=[Verdict, AppliedPatch],
    )
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))

    verdicts = [e["payload"] for e in events if e["kind"] == "Verdict"]
    assert [v["passed"] for v in verdicts] == [
        False,
        True,
    ]  # round 1 failed to apply, round 2 applied
    applied = _applied(events)
    assert len(applied) == 1 and applied[0]["round"] == 2
    out = _outcome(events)
    assert out is not None and out["kind"] == "Solved" and out["payload"]["round"] == 2
