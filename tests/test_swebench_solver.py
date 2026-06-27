"""End-to-end observation contract for the full swebench_solver topology (sprint 141): LOCALIZE -> REPAIR
-> SELECT on a FIXTURE repo with deterministic responders + a stand-in runner. The record is the
observable — a SelectedPatch with the resolving diff comes out the far end of the whole pipeline."""

import subprocess
import tempfile
from pathlib import Path

from substrate.api import Runtime, read_record
from substrate.topologies.swebench_solver.assemble import swebench_solver_topology

_FIX = "# path: m.py\n<<<<<<< SEARCH\n    return x\n=======\n    return x + 1\n>>>>>>> REPLACE\n"


def _fixture_repo() -> str:
    d = tempfile.mkdtemp()
    (Path(d) / "m.py").write_text("def f(x):\n    return x\n")
    (Path(d) / "README.md").write_text("a fixture\n")
    for args in (
        ["git", "-C", d, "init", "-q"],
        ["git", "-C", d, "config", "user.email", "t@t"],
        ["git", "-C", d, "config", "user.name", "t"],
        ["git", "-C", d, "add", "-A"],
        ["git", "-C", d, "commit", "-qm", "base"],
    ):
        subprocess.run(args, capture_output=True, check=True)
    return d


class _SolverResponder:
    """One stand-in for both phases: returns the suspect file on a LOCALIZE prompt, the SEARCH/REPLACE fix
    on a REPAIR prompt (keyed on a distinctive localize phrase)."""

    def respond(self, prompt: str) -> str:
        return "m.py\n" if "suspect file" in prompt else _FIX


class _StubRunner:
    """Regression passes; the reproduction test reports the issue resolved."""

    def run(self, model_patch: str, test_command: str) -> tuple[int, str]:
        return (0, "1 passed in 0.1s") if test_command == "REG" else (0, "Issue resolved")


async def test_swebench_solver_end_to_end_on_a_fixture(tmp_path) -> None:  # type: ignore[no-untyped-def]
    base = _fixture_repo()
    topo = swebench_solver_topology(
        responders=[_SolverResponder() for _ in range(2)],
        base_checkout=base,
        issue="make f(x) return x + 1",
        repo_skeleton="m.py\nREADME.md",
        known_files={"m.py", "README.md"},
        runner=_StubRunner(),
        regression_command="REG",
        reproduction_command="REPRO",
        n=2,
        max_rounds=1,
        watchdog_seconds=20.0,
    )
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))

    # the pipeline ran every phase: localization, N applied patches, test results, a selection.
    assert [e["payload"]["files"] for e in events if e["kind"] == "SuspectFiles"] == [["m.py"]]
    applied = [e["payload"] for e in events if e["kind"] == "AppliedPatch"]
    assert len(applied) == 2 and all("+    return x + 1" in a["model_patch"] for a in applied)
    assert len([e for e in events if e["kind"] == "TestResults"]) == 2
    selected = [e["payload"] for e in events if e["kind"] == "SelectedPatch"]
    assert len(selected) == 1 and "+    return x + 1" in selected[0]["model_patch"]
