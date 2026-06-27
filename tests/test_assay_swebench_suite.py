"""SWE-bench Adapter/Suite wiring — the non-Docker parts. `prepare_swebench_case` (git + Docker) is
env-gated and exercised live; here we prove an Arm builds a topology from a prepared payload and the Suite
assembles + validates, with no I/O."""

from substrate.assay.suite import BASELINE, FULL, Case
from substrate.assay.swebench_suite import (
    safe_case_id,
    solver_topology_from_payload,
    swebench_solver_arm,
    swebench_suite,
)


def test_safe_case_id_strips_the_double_underscore():
    # SWE-bench ids carry '__'; the harness forbids it in a case_id (run-root separator).
    assert safe_case_id("pallets__flask-4045") == "pallets_1776_flask-4045"
    assert "__" not in safe_case_id("django__django-12345")

_PAYLOAD = {
    "base_checkout": "/tmp/does-not-need-to-exist",
    "repo_skeleton": "src/flask/blueprints.py\ntests/test_json.py",
    "known_files": ["src/flask/blueprints.py", "tests/test_json.py"],
    "regression_files": ["tests/test_json.py"],
    "exclude": ["tests/test_blueprints.py"],
    "spec": {"install": "python -m pip install -e .", "test_cmd": "pytest -rA"},
    "passed_at_base": ["tests/test_json.py::test_dump"],
    "image": "swebench/sweb.eval.x86_64.pallets_1776_flask-4045:latest",
    "issue": "Blueprint names with dots should raise",
}


def _case():
    # case_id is the path-safe label (no '__'); the REAL instance_id rides in ground_truth for grading.
    return Case(
        case_id="pallets_1776_flask-4045",
        payload=dict(_PAYLOAD),
        ground_truth={"instance_id": "pallets__flask-4045"},
    )


def test_solver_topology_from_payload_returns_a_topology():
    from substrate.reference._models import DeterministicResponder

    topo = solver_topology_from_payload(
        _PAYLOAD, [DeterministicResponder(), DeterministicResponder()], n=2, max_rounds=1
    )
    assert callable(topo)  # building the topology does no I/O; the runner runs only at run time


def test_solver_arm_build_returns_a_topology_from_a_case():
    arm = swebench_solver_arm("full", FULL, models=["qwen2.5-coder:7b"], n=2)
    assert arm.role == FULL
    assert callable(arm.build(_case()))  # one model cycled across 2 slots; no connection at build


def test_swebench_suite_assembles_and_validates(tmp_path):
    arms = [
        swebench_solver_arm("strong_ref", BASELINE, models=["strong"], n=1),
        swebench_solver_arm("full", FULL, models=["a", "b"]),
    ]
    suite = swebench_suite(
        [_case()], arms, report_root=tmp_path, dataset_name="princeton-nlp/SWE-bench_Lite",
        control_arm="strong_ref",
    )
    assert suite.control_arm == "strong_ref"
    assert [a.name for a in suite.arms] == ["strong_ref", "full"]
    assert suite.primary_metric == "resolved" and suite.oracle is not None
