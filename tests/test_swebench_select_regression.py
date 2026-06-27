"""The deterministic proximity test-picker (finding 17b / review #65). Pure checkout-vs-patch logic — the
observable is the chosen regression file set. Includes the real flask-4045 shape: the fix touches
src/flask/blueprints.py, so test_blueprints.py is change-related and must be EXCLUDED (stem match), while an
unrelated test like test_json.py stays IN the regression set."""

from substrate.topologies.swebench_solver.select_exec import resolve_regression
from substrate.topologies.swebench_solver.select_regression import (
    make_regression_planner,
    patch_touched_files,
    proximity_regression_files,
    related_test_files,
)

_SPEC = {"install": "python -m pip install -e .", "test_cmd": "pytest -rA"}

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


def test_planner_builds_per_candidate_firewall_clean_command() -> None:
    repo_tests = ["tests/test_basic.py", "tests/test_blueprints.py", "tests/test_json.py"]
    exclude = {"tests/test_basic.py", "tests/test_blueprints.py"}  # held-out test_patch files
    plan = make_regression_planner(_SPEC, repo_tests, exclude=exclude)
    cmd = plan(_FLASK_PATCH)  # the patch touches src/flask/blueprints.py
    # only the issue-unrelated, non-held-out test runs, under the repo's own install + runner.
    assert cmd.endswith("pytest -rA tests/test_json.py")
    assert "python -m pip install -e ." in cmd


def test_planner_empty_command_when_everything_excluded() -> None:
    plan = make_regression_planner(_SPEC, ["tests/test_basic.py"], exclude={"tests/test_basic.py"})
    assert plan(_FLASK_PATCH) == ""  # nothing left -> empty (no vacuous all-pass)


def test_resolve_regression_static_vs_planner() -> None:
    # a static string is the same for every patch; a planner tailors per patch.
    assert resolve_regression("REG", "any patch") == "REG"
    plan = make_regression_planner(_SPEC, ["tests/test_json.py"], exclude=set())
    assert resolve_regression(plan, _FLASK_PATCH).endswith("pytest -rA tests/test_json.py")
