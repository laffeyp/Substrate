"""Host-backend coding step — the non-network parts (file pick parsing). The clone+grade integration is
env-gated and run live."""

from substrate.assay.swebench_host import _pick_file


class _Stub:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def respond(self, prompt: str) -> str:
        return self._reply


def test_pick_file_keeps_only_a_real_repo_path():
    known = ["src/flask/blueprints.py", "src/flask/app.py"]
    assert _pick_file(_Stub("src/flask/blueprints.py"), "issue", known) == "src/flask/blueprints.py"
    # a path the model invents (not in the repo) is rejected -> None, never a fabricated edit target.
    assert _pick_file(_Stub("src/flask/made_up.py"), "issue", known) is None
    # tolerate backticks / extra lines; take the first line.
    assert _pick_file(_Stub("`src/flask/app.py`\nbecause..."), "issue", known) == "src/flask/app.py"
