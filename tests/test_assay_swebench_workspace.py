"""The SWE-bench workspace diff seam: turn a changed checkout into a model_patch, dropping test-file edits
(which collide with the held-out test_patch and cause false not-resolves). git is real; no Docker."""

import subprocess
from pathlib import Path

from substrate.assay.swebench_workspace import filter_diff, is_test_file, workspace_diff


def test_is_test_file():
    assert is_test_file("tests/test_basic.py")
    assert is_test_file("pkg/foo_test.py")
    assert is_test_file("conftest.py") and is_test_file("tests/conftest.py")
    assert not is_test_file("src/flask/blueprints.py")
    assert not is_test_file("setup.py")  # config is KEPT — a real fix may touch it


_DIFF = """diff --git a/src/app.py b/src/app.py
index 111..222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1 +1 @@
-x = 1
+x = 2
diff --git a/tests/test_app.py b/tests/test_app.py
index 333..444 100644
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -1 +1 @@
-assert x == 1
+assert x == 2
"""


def test_filter_diff_drops_test_sections_keeps_source():
    out = filter_diff(_DIFF)
    assert "a/src/app.py" in out and "+x = 2" in out  # source kept
    assert "tests/test_app.py" not in out and "assert x == 2" not in out  # test section dropped


def _git_repo(tmp_path) -> Path:
    d = tmp_path / "repo"
    d.mkdir()
    (d / "app.py").write_text("def f():\n    return 1\n")
    (d / "tests").mkdir()
    (d / "tests" / "test_app.py").write_text("assert f() == 1\n")
    for args in (
        ["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"],
        ["add", "-A"], ["commit", "-qm", "base"],
    ):
        subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True)
    return d


def test_workspace_diff_on_a_real_repo_drops_test_edits(tmp_path):
    repo = _git_repo(tmp_path)
    # a topology edits BOTH a source file and a test file in the checkout.
    (repo / "app.py").write_text("def f():\n    return 2\n")
    (repo / "tests" / "test_app.py").write_text("assert f() == 2\n")
    patch = workspace_diff(str(repo))
    assert "app.py" in patch and "+    return 2" in patch  # the real fix is in the patch
    assert "test_app.py" not in patch  # the test edit is dropped (would collide with the held-out tests)


def test_workspace_diff_empty_when_nothing_changed(tmp_path):
    repo = _git_repo(tmp_path)
    assert workspace_diff(str(repo)) == ""  # no changes -> empty patch (graded not-resolved, no crash)


def test_workspace_diff_captures_a_new_file(tmp_path):
    repo = _git_repo(tmp_path)
    (repo / "newmod.py").write_text("y = 9\n")  # git add -A must surface new files
    patch = workspace_diff(str(repo))
    assert "newmod.py" in patch and "+y = 9" in patch
