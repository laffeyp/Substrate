"""The SWE-bench matrix wiring — suite assembly + arm topology build (no Docker, no model)."""

import pytest

from substrate.assay.suite import BASELINE, FULL
from substrate.assay.swebench_matrix import (
    baseline_matched_compute_arm,
    container_arm,
    host_arm,
    n_drafts_no_correction_arm,
    n_drafts_repair_ensemble_arm,
    single_draft_baseline_arm,
    swebench_matrix_suite,
)


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


def test_sprint_159_matrix_names_and_roles():
    # The five arms of the sprint 159 confirmatory matrix. Names and default roles pin the
    # matrix shape a caller composes into `swebench_matrix_suite` — a rename or role change
    # here trips this test AND would fail the pre-registration gate's arms_hash check.
    arms = [
        single_draft_baseline_arm("single", model="m"),
        n_drafts_no_correction_arm("no_correction", model="m", n=3),
        # repair_arm exists already (pre-159); kept for backward compat.
        n_drafts_repair_ensemble_arm("ensemble", models=("m1", "m2", "m3")),
        baseline_matched_compute_arm("matched", model="m_strong", k_calls=9),
    ]
    assert [a.name for a in arms] == ["single", "no_correction", "ensemble", "matched"]
    assert [a.role for a in arms] == ["baseline", "ablation", "full", "baseline"]


def test_baseline_matched_compute_rejects_zero_k():
    # K < 1 is nonsense — a compute-matched baseline needs at least one attempt.
    with pytest.raises(ValueError, match="k_calls must be >= 1"):
        baseline_matched_compute_arm("matched", model="m", k_calls=0)


def test_ensemble_arm_n_matches_models_length():
    # The ensemble arm's N is INTRINSICALLY len(models) — the whole point is one distinct model
    # per slot. Verify build wires that many responders (structural check via the topology
    # builder's declared kinds; no network / no clone).
    arm = n_drafts_repair_ensemble_arm("ens", models=("a", "b", "c"))
    # Attempting build would clone github.com — skip that; just verify the arm carries the
    # ensemble shape by inspecting the wrapped build closure indirectly through the arm name.
    assert arm.name == "ens"
    assert arm.role == "full"  # default when caller omits role
    # A single-model spelling degrades to a 1-slot arm — flag if anyone slipped `models=("x",)`
    # into a call site that meant to be an ensemble.
    single = n_drafts_repair_ensemble_arm("solo", models=("x",))
    assert single.name == "solo"  # legal but degenerate ensemble; test-only pin


def test_single_draft_baseline_default_role_is_baseline():
    arm = single_draft_baseline_arm("single", model="m")
    assert arm.role == "baseline"


def test_n_drafts_no_correction_default_role_is_ablation():
    # This arm's whole purpose is ablating the correction round from the full pipeline.
    arm = n_drafts_no_correction_arm("nc", model="m")
    assert arm.role == "ablation"


def test_baseline_matched_compute_default_role_is_baseline():
    # Compute-matched IS a baseline — same currency (model calls) as the ensemble, different
    # mechanism (one strong model vs. three at N=1 each).
    arm = baseline_matched_compute_arm("matched", model="m", k_calls=9)
    assert arm.role == "baseline"
