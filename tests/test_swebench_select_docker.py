"""Unit tests for the non-Docker parts of select_docker (the image name + the firewall-keeping regression
command). The real DockerTestRunner.run is verified by scripts/docker_runner_smoke.py against a live image."""

from substrate.topologies.swebench_solver.select_docker import derive_regression_command, instance_image


def test_instance_image_name() -> None:
    assert instance_image("pallets__flask-4045") == "swebench/sweb.eval.x86_64.pallets_1776_flask-4045:latest"


def test_derive_regression_command_drops_held_out_test_files() -> None:
    cmd = derive_regression_command(["tests/test_a.py", "tests/test_b.py"], exclude={"tests/test_b.py"})
    assert "tests/test_a.py" in cmd and "tests/test_b.py" not in cmd  # the held-out file is dropped
    assert cmd.startswith("python -m pytest")
    # nothing left to run after excluding -> empty command (no vacuous all-pass)
    assert derive_regression_command(["tests/test_x.py"], exclude={"tests/test_x.py"}) == ""
