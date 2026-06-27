"""The deterministic proximity test-picker (finding 17b / review #65). Pure checkout-vs-patch logic — the
observable is the chosen regression file set. Includes the real flask-4045 shape: the fix touches
src/flask/blueprints.py, so test_blueprints.py is change-related and must be EXCLUDED (stem match), while an
unrelated test like test_json.py stays IN the regression set."""

from substrate.topologies.swebench_solver.select_regression import (
    patch_touched_files,
    proximity_regression_files,
    related_test_files,
)

_FLASK_PATCH = """diff --git a/src/flask/blueprints.py b/src/flask/blueprints.py
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -1,3 +1,3 @@
-        if "." in name:
+        if "." in name and not allowed:
"""


def test_patch_touched_files_parses_headers() -> None:
    assert patch_touched_files(_FLASK_PATCH) == {"src/flask/blueprints.py"}


def test_touched_files_drops_dev_null_on_pure_add() -> None:
    add = "--- /dev/null\n+++ b/src/flask/new_mod.py\n@@ -0,0 +1 @@\n+x = 1\n"
    assert patch_touched_files(add) == {"src/flask/new_mod.py"}


def test_related_excludes_stem_match() -> None:
    # the test counterpart pairs by stem even though it lives in a separate tree (tests/ vs src/flask/).
    tests = ["tests/test_blueprints.py", "tests/test_json.py"]
    touched = {"src/flask/blueprints.py"}
    assert related_test_files(tests, touched) == {"tests/test_blueprints.py"}


def test_related_excludes_same_dir_and_direct_touch() -> None:
    tests = ["pkg/tests/test_a.py", "pkg/tests/test_b.py", "other/test_c.py"]
    # the patch edits one test in pkg/tests/ -> that test (direct) AND its dir-sibling are change-related.
    touched = {"pkg/tests/test_a.py"}
    assert related_test_files(tests, touched) == {"pkg/tests/test_a.py", "pkg/tests/test_b.py"}


def test_flask4045_regression_set_drops_blueprints_keeps_unrelated() -> None:
    test_files = ["tests/test_basic.py", "tests/test_blueprints.py", "tests/test_json.py"]
    touched = patch_touched_files(_FLASK_PATCH)  # {src/flask/blueprints.py}
    # exclude = the held-out test_patch files (firewall): flask-4045's test_patch edits test_basic.py +
    # test_blueprints.py, so they're excluded as held-out; test_blueprints would ALSO be dropped by stem.
    exclude = {"tests/test_basic.py", "tests/test_blueprints.py"}
    reg = proximity_regression_files(test_files, touched, exclude=exclude)
    assert reg == ["tests/test_json.py"]  # only the issue-unrelated, non-held-out test survives


def test_regression_set_is_sorted_and_deterministic() -> None:
    test_files = {"tests/test_z.py", "tests/test_a.py", "tests/test_m.py"}
    reg = proximity_regression_files(test_files, touched=set(), exclude=set())
    assert reg == ["tests/test_a.py", "tests/test_m.py", "tests/test_z.py"]
