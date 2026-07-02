"""The SWE-bench matrix wiring — suite assembly + arm topology build (no Docker, no model)."""

from substrate.assay.suite import BASELINE, FULL
from substrate.assay.swebench_matrix import container_arm, host_arm, swebench_matrix_suite


def _inst():
    return {
        "instance_id": "pallets__flask-4045",
        "repo": "pallets/flask",
        "base_commit": "abc",
        "problem_statement": "fix the bug",
        "test_patch": "",
        "patch": "",
        "FAIL_TO_PASS": "[]",
    }


def test_matrix_suite_assembles_with_both_arms(tmp_path):
    arms = [host_arm("host", BASELINE, model="m"), container_arm("container", FULL, model="m")]
    suite = swebench_matrix_suite(
        [_inst()], arms, report_root=str(tmp_path), dataset_name="d", control_arm="host"
    )
    assert [a.name for a in suite.arms] == ["host", "container"]
    assert suite.control_arm == "host" and suite.equivalence_margin == 0.2
    assert suite.cases[0].case_id == "pallets_1776_flask-4045"  # path-safe label
    assert (
        suite.cases[0].ground_truth["instance_id"] == "pallets__flask-4045"
    )  # real id for grading


def test_arm_build_returns_a_topology_without_io(tmp_path):
    suite = swebench_matrix_suite(
        [_inst()],
        [host_arm("host", BASELINE, model="m")],
        report_root=str(tmp_path),
        dataset_name="d",
        control_arm="host",
    )
    topo = suite.arms[0].build(
        suite.cases[0]
    )  # constructs the responder + topology; no clone/model call
    assert callable(topo)
