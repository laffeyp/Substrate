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


class _FlakyRunner:
    """Raises on the first call (a real container failure: OOM/timeout), then behaves — proves one patch's
    runner failure becomes a RECORDED not-resolved, not a gather-wedge that emits zero results (review #62)."""

    def __init__(self) -> None:
        self.calls = 0

    def run(self, model_patch: str, test_command: str) -> tuple[int, str]:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("container OOM")
        return (0, "1 passed in 0.1s") if test_command == "REG" else (0, "Issue resolved")


async def test_runner_failure_does_not_wedge(tmp_path) -> None:  # type: ignore[no-untyped-def]
    base = _fixture_repo()
    topo = swebench_solver_topology(
        responders=[_SolverResponder() for _ in range(2)],
        base_checkout=base, issue="make f(x) return x + 1", repo_skeleton="m.py\nREADME.md",
        known_files={"m.py", "README.md"}, runner=_FlakyRunner(),
        regression_command="REG", reproduction_command="REPRO", n=2, max_rounds=1, watchdog_seconds=5.0,
    )
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))
    # always exactly N=2 TestResults (one a recorded runner-error), and a SelectedPatch still comes out.
    assert len([e for e in events if e["kind"] == "TestResults"]) == 2
    assert len([e for e in events if e["kind"] == "SelectedPatch"]) == 1


class _DyingDrafter:
    """Localizes fine, but the DRAFT model call dies — proves the drafter emits a failed Candidate so the
    round completes (-> Exhausted), never wedging the run on a dead coroutine (review #62)."""

    def respond(self, prompt: str) -> str:
        if "suspect file" in prompt:
            return "m.py\n"
        raise RuntimeError("model died")


async def test_drafter_model_error_does_not_wedge(tmp_path) -> None:  # type: ignore[no-untyped-def]
    base = _fixture_repo()
    topo = swebench_solver_topology(
        responders=[_DyingDrafter() for _ in range(2)],
        base_checkout=base, issue="make f(x) return x + 1", repo_skeleton="m.py\nREADME.md",
        known_files={"m.py", "README.md"}, runner=_StubRunner(),
        regression_command="REG", reproduction_command="REPRO", n=2, max_rounds=1, watchdog_seconds=5.0,
    )
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))
    # the failed drafts don't apply -> all fail -> Exhausted CLEANLY (not a watchdog wedge); no patch.
    assert any(e["kind"] == "Exhausted" for e in events)
    assert not any(e["kind"] == "SelectedPatch" for e in events)
