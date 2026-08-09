"""Unit tests for the non-Docker parts of select_docker (the image name + the firewall-keeping regression
command). The real DockerTestRunner.run is verified by scripts/docker_runner_smoke.py against a live image."""

from substrate.topologies.swebench_solver.select_docker import (
    MODULE_LABEL_RUNNER,
    PATH_RUNNER,
    build_regression_command,
    cmd_takes_paths,
    instance_image,
    path_to_module_label,
    runner_flavor,
)

# a stand-in for swebench's per-repo spec (the real one comes from MAP_REPO_VERSION_TO_SPECS, env-gated).
_FLASK_SPEC = {"install": "python -m pip install -e .", "test_cmd": "pytest -rA"}


def test_instance_image_name() -> None:
    assert (
        instance_image("pallets__flask-4045")
        == "swebench/sweb.eval.x86_64.pallets_1776_flask-4045:latest"
    )


def test_build_regression_command_reuses_repo_install_and_runner() -> None:
    cmd = build_regression_command(_FLASK_SPEC, ["tests/test_json.py"])
    # reuses the repo's OWN install + test runner (not a hand-rolled pytest), activates the testbed env,
    # and runs only the chosen file — never test_patch / PASS_TO_PASS.
    assert "conda activate testbed" in cmd
    assert "python -m pip install -e ." in cmd
    # --continue-on-collection-errors so one stray uncollectable file can't abort the whole run (#152)
    assert "--continue-on-collection-errors" in cmd
    assert cmd.endswith("pytest -rA --continue-on-collection-errors tests/test_json.py")


def test_build_regression_command_empty_when_no_files() -> None:
    # nothing left to run -> empty command (no vacuous all-pass)
    assert build_regression_command(_FLASK_SPEC, []) == ""


def test_cmd_takes_paths() -> None:
    assert cmd_takes_paths("pytest -rA") is True
    assert cmd_takes_paths("python -m pytest") is True
    # django's module-label runner is NOT path-taking
    assert cmd_takes_paths("./tests/runtests.py --settings=test_sqlite") is False


def test_runner_flavor_detects_pytest_and_module_label():
    # F5 fix (review 2026-08-08): the classifier the dispatcher uses.
    assert runner_flavor("pytest -rA") == PATH_RUNNER
    assert runner_flavor("python -m pytest") == PATH_RUNNER
    assert runner_flavor("./tests/runtests.py --settings=test_sqlite") == MODULE_LABEL_RUNNER
    assert runner_flavor("python -m unittest") == MODULE_LABEL_RUNNER
    # Unknown falls back to PATH_RUNNER — the majority default; a real mismatch surfaces in the
    # run's stderr rather than as a silent exclusion.
    assert runner_flavor("some-custom-runner --flags") == PATH_RUNNER


def test_path_to_module_label_conversions():
    # F5 fix: file paths -> dotted module labels for django/unittest runners.
    assert path_to_module_label("myapp/tests/foo.py") == "myapp.tests.foo"
    assert path_to_module_label("tests/regressiontests/test_x.py") == "tests.regressiontests.test_x"
    # __init__.py collapses to the package label (not a spurious .__init__ suffix).
    assert path_to_module_label("myapp/tests/__init__.py") == "myapp.tests"
    # Non-Python paths pass through unchanged — the caller filters them out for module-label runners.
    assert path_to_module_label("setup.cfg") == "setup.cfg"


def test_build_regression_command_django_uses_module_labels_post_F5():
    # F5 fix (review 2026-08-08): pre-fix build_regression_command RAISED on the django/unittest
    # case, so every django instance crashed at case-preparation. Now it converts file paths to
    # dotted module labels and appends them positionally — the shape runtests.py accepts.
    django_spec = {
        "install": "python -m pip install -e .",
        "test_cmd": "./tests/runtests.py --settings=test_sqlite",
    }
    cmd = build_regression_command(django_spec, ["myapp/tests.py", "other/tests/foo.py"])
    assert "conda activate testbed" in cmd
    assert "python -m pip install -e ." in cmd
    assert "./tests/runtests.py --settings=test_sqlite" in cmd
    # module labels appended, not file paths. No --continue-on-collection-errors (that's a
    # pytest flag; runtests.py wouldn't know it).
    assert "myapp.tests" in cmd
    assert "other.tests.foo" in cmd
    assert "myapp/tests.py" not in cmd
    assert "--continue-on-collection-errors" not in cmd


def test_build_regression_command_module_label_drops_non_python_entries():
    # A non-Python entry in the regression list (a .cfg picked by the proximity heuristic) can't
    # be a module label — the module-label branch filters it out. If ALL entries are non-Python,
    # returns empty (no vacuous all-pass, same as no-files case).
    django_spec = {"install": "python -m pip install -e .", "test_cmd": "./tests/runtests.py"}
    cmd = build_regression_command(django_spec, ["myapp/tests.py", "setup.cfg"])
    assert "myapp.tests" in cmd
    assert "setup.cfg" not in cmd
    # All non-Python -> empty.
    assert build_regression_command(django_spec, ["setup.cfg", "conftest.ini"]) == ""


def test_cmd_takes_paths_legacy_alias():
    # Kept for the one existing caller — same dispatch as runner_flavor == PATH_RUNNER.
    assert cmd_takes_paths("pytest -rA") is True
    assert cmd_takes_paths("./tests/runtests.py") is False
