"""The deterministic proximity test-picker (finding 17b / review #65). Pure checkout-vs-patch logic — the
observable is the chosen regression file set. Includes the real flask-4045 shape: the fix touches
src/flask/blueprints.py, so test_blueprints.py is change-related and must be EXCLUDED (stem match), while an
unrelated test like test_json.py stays IN the regression set."""

from substrate.topologies.swebench_solver.select_exec import resolve_regression
from substrate.topologies.swebench_solver.select_regression import (
    canonical_test_modules,
    discover_test_modules,
    exclude_delta,
    is_test_module,
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


def test_discover_test_modules_drops_fixture_and_support_files() -> None:
    # the exact shape the real-runner smoke surfaced (#69 NET #2): only true test modules survive; the
    # fixture app that raises ImportError on collection, package __init__, and a plain module are dropped.
    repo_files = [
        "tests/test_basic.py",
        "tests/test_apps/__init__.py",
        "tests/test_apps/cliapp/importerrorapp.py",  # raises ImportError ON PURPOSE -> not a test module
        "src/flask/blueprints.py",
        "tests/helpers.py",
        "tests/conftest.py",  # support, not a test module
    ]
    assert discover_test_modules(repo_files) == ["tests/test_basic.py"]
    assert is_test_module("tests/test_apps/cliapp/importerrorapp.py") is False
    assert is_test_module("pkg/foo_test.py") is True


def test_canonical_test_modules_drops_example_test_trees() -> None:
    # the exact shape the real solve #152 surfaced: flask's examples/*/tests have a conftest that imports an
    # uninstalled example package -> fatal rc-4 conftest error. The dominant `tests/` group is kept; the
    # scattered `examples/` test trees are dropped.
    mods = [
        "tests/test_basic.py",
        "tests/test_json.py",
        "tests/test_blueprints.py",
        "examples/javascript/tests/test_js_example.py",
        "examples/tutorial/tests/test_auth.py",
    ]
    assert canonical_test_modules(mods) == [
        "tests/test_basic.py",
        "tests/test_blueprints.py",
        "tests/test_json.py",
    ]


def test_planner_builds_per_candidate_firewall_clean_command() -> None:
    repo_tests = ["tests/test_basic.py", "tests/test_blueprints.py", "tests/test_json.py"]
    exclude = {"tests/test_basic.py", "tests/test_blueprints.py"}  # held-out test_patch files
    plan = make_regression_planner(_SPEC, repo_tests, exclude=exclude)
    run = plan(_FLASK_PATCH)  # the patch touches src/flask/blueprints.py
    # only the issue-unrelated, non-held-out test runs, under the repo's own install + runner.
    assert run.command.endswith("pytest -rA --continue-on-collection-errors tests/test_json.py")
    assert "python -m pip install -e ." in run.command
    assert run.files == frozenset(
        {"tests/test_json.py"}
    )  # the scope, for the vanished-test check (#70)


def test_planner_empty_command_when_everything_excluded() -> None:
    plan = make_regression_planner(_SPEC, ["tests/test_basic.py"], exclude={"tests/test_basic.py"})
    run = plan(_FLASK_PATCH)
    assert (
        run.command == "" and run.files == frozenset()
    )  # nothing left -> empty (no vacuous all-pass)


def test_exclude_delta_zero_when_proximity_already_catches() -> None:
    # the issue test is co-located (stem match) -> proximity already drops it -> exclude adds nothing.
    test_files = ["tests/test_blueprints.py", "tests/test_json.py"]
    touched = {"src/flask/blueprints.py"}
    assert exclude_delta(test_files, touched, exclude={"tests/test_blueprints.py"}) == []


def test_exclude_delta_names_the_harness_assist() -> None:
    # the issue test is NOT co-located (other dir, no stem match) -> proximity keeps it -> exclude is what
    # drops it: that drop is the harness assist, and exclude_delta names it.
    test_files = ["other/test_weird.py", "tests/test_json.py"]
    touched = {"src/flask/blueprints.py"}
    assert exclude_delta(test_files, touched, exclude={"other/test_weird.py"}) == [
        "other/test_weird.py"
    ]


def test_resolve_regression_static_vs_planner() -> None:
    # a static string is the same for every patch with no scope; a planner tailors command + scope per patch.
    static = resolve_regression("REG", "any patch")
    assert static.command == "REG" and static.files is None
    plan = make_regression_planner(_SPEC, ["tests/test_json.py"], exclude=set())
    run = resolve_regression(plan, _FLASK_PATCH)
    assert run.command.endswith("pytest -rA --continue-on-collection-errors tests/test_json.py")
    assert run.files == frozenset({"tests/test_json.py"})
