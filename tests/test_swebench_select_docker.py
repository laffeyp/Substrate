"""Unit tests for the non-Docker parts of select_docker (the image name + the firewall-keeping regression
command). The real DockerTestRunner.run is verified by scripts/docker_runner_smoke.py against a live image."""

from substrate.topologies.swebench_solver.select_docker import build_regression_command, instance_image

# a stand-in for swebench's per-repo spec (the real one comes from MAP_REPO_VERSION_TO_SPECS, env-gated).
_FLASK_SPEC = {"install": "python -m pip install -e .", "test_cmd": "pytest -rA"}


def test_instance_image_name() -> None:
    assert instance_image("pallets__flask-4045") == "swebench/sweb.eval.x86_64.pallets_1776_flask-4045:latest"


def test_build_regression_command_reuses_repo_install_and_runner() -> None:
    cmd = build_regression_command(_FLASK_SPEC, ["tests/test_json.py"])
    # reuses the repo's OWN install + test runner (not a hand-rolled pytest), activates the testbed env,
    # and runs only the chosen file — never test_patch / PASS_TO_PASS.
    assert "conda activate testbed" in cmd
    assert "python -m pip install -e ." in cmd
    assert cmd.endswith("pytest -rA tests/test_json.py")


def test_build_regression_command_empty_when_no_files() -> None:
    # nothing left to run -> empty command (no vacuous all-pass)
    assert build_regression_command(_FLASK_SPEC, []) == ""
