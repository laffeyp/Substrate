# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The SWE-bench matrix wiring — suite assembly + arm topology build (no Docker, no model)."""

import pytest

from substrate.assay.suite import BASELINE, FULL
from substrate.assay.swebench_matrix import (
    container_arm,
    host_arm,
    swebench_matrix_suite,
    swebench_repair_arm,
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
    # The five arms of the Sprint 160 confirmatory matrix, expressed as rows against the
    # parametric factory `swebench_repair_arm`. Rename or role change trips this test AND
    # would fail the pre-registration gate's arms_hash check.
    arms = [
        swebench_repair_arm("single", models=["m"], n=1, max_rounds=1, role="baseline"),
        swebench_repair_arm("no_correction", models=["m"], n=3, max_rounds=1, role="ablation"),
        swebench_repair_arm("ensemble", models=["m1", "m2", "m3"], n=3, max_rounds=2, role="full"),
        swebench_repair_arm("matched", models=["m_strong"], n=9, max_rounds=1, role="baseline"),
    ]
    assert [a.name for a in arms] == ["single", "no_correction", "ensemble", "matched"]
    assert [a.role for a in arms] == ["baseline", "ablation", "full", "baseline"]


def test_swebench_repair_arm_rejects_zero_n():
    # n < 1 is nonsense — an arm needs at least one drafter slot. The check lives on the
    # parametric factory; every caller inherits it.
    with pytest.raises(ValueError, match="n must be >= 1"):
        swebench_repair_arm("bad", models=["m"], n=0, max_rounds=1)


def test_swebench_repair_arm_default_role_is_full():
    arm = swebench_repair_arm("x", models=["m"], n=1, max_rounds=1)
    assert arm.role == "full"


class _RecordingBuilder:
    """A stub TopologyBuilder that records every producer_kind name registered against it.
    Used to inspect what a topology declares without wiring the real substrate runtime."""

    def __init__(self):
        self.producer_kinds: list[str] = []

    def producer_kind(self, name, **_kw):
        self.producer_kinds.append(name)

    def initial(self, *_a, **_kw):
        pass

    def view(self, *_a, **_kw):
        pass

    def trigger(self, *_a, **_kw):
        pass

    def termination(self, *_a, **_kw):
        pass


def _payload_for_test():
    # Minimal PreparedPayload the light topology needs. `base_checkout` and `repo_skeleton`
    # can be strings the topology never dereferences at build time (only at run time).
    return {
        "base_checkout": "/tmp/does-not-exist",
        "issue": "test issue",
        "repo_skeleton": "",
        "known_files": set(),
        "image": "img",
        "spec": None,
        "regression_files": (),
        "passed_at_base": (),
        "exclude": (),
        "skip_base_pytest": True,
    }


def _case_for_test():
    from substrate.assay.suite import Case

    inst = _inst()
    return Case(
        case_id="pallets_1776_flask-4045",
        payload=_payload_for_test(),
        ground_truth=inst,
    )


def test_matrix_arms_dispatch_light_topology_producer_kinds_omit_select_exec():
    # Design v3 §"The five-arm matrix" (ratified 2026-08-10): every arm builds the LIGHT
    # `swebench_repair_topology`; the heavy `select_exec` test-execution SELECT apparatus
    # is out. This test builds every arm factory's topology and asserts producer_kinds
    # never include `select_exec`. A regression here fails BEFORE the confirmatory fires.
    case = _case_for_test()
    arms = [
        swebench_repair_arm("single", models=["m"], n=1, max_rounds=1, role="baseline"),
        swebench_repair_arm("no_correction", models=["m"], n=3, max_rounds=1, role="ablation"),
        swebench_repair_arm("ensemble", models=["m1", "m2", "m3"], n=3, max_rounds=2, role="full"),
        swebench_repair_arm("matched", models=["m_strong"], n=9, max_rounds=1, role="baseline"),
    ]
    for arm in arms:
        topo = arm.build(case)
        b = _RecordingBuilder()
        topo(b)
        assert "select_exec" not in b.producer_kinds, (
            f"arm {arm.name!r} declared a select_exec producer — the heavy topology leaked "
            "back into the matrix. Design v3 §'The five-arm matrix' forbids this at the gate."
        )


def test_container_arm_dispatches_distinct_topology_shape():
    # F8 (holistic review 2026-08-10): the matrix needs a structurally distinct topology
    # arm, not another parameterization of swebench_repair_topology. `container_arm` wraps
    # `solve_in_container` (a read/edit/bash agent loop) as a one-producer topology whose
    # only producer kind is "solve" — no `localizer`, no `drafter`, no `select_exec`, none
    # of the repair topology's producers. This test pins that shape so a well-meaning
    # refactor cannot silently re-route container_arm through the repair machinery.
    arm = container_arm("tool_loop_container", role="ablation", model="m", max_steps=8)
    case = _case_for_test()
    topo = arm.build(case)  # build is pure — Docker fires only when the topology RUNS
    b = _RecordingBuilder()
    topo(b)
    assert b.producer_kinds == ["solve"], (
        f"container_arm should declare exactly the 'solve' producer; got {b.producer_kinds}. "
        "A leak of repair topology producers here means the matrix's structurally distinct arm "
        "silently became another parameterized wrapper — F8 regressed."
    )


def test_include_test_selection_parameter_retired():
    """Sprint 199b (roadmap v2 S7b): the `include_test_selection` opt-in that routed to
    the heavy `swebench_solver_topology_with_test_selection` was retired. The parameter
    no longer appears on `_build_solver_arm_from_payload` OR `swebench_repair_arm`.
    Regression: adding it back would let the heavy path re-enter matrix-arm code paths."""
    import inspect

    from substrate.assay.swebench_matrix import (
        _build_solver_arm_from_payload,
        swebench_repair_arm,
    )

    sig_build = inspect.signature(_build_solver_arm_from_payload)
    sig_arm = inspect.signature(swebench_repair_arm)
    assert "include_test_selection" not in sig_build.parameters, (
        "_build_solver_arm_from_payload must not carry the retired include_test_selection "
        "parameter. See Sprint 199b (S7b) and _deprecated/README.md."
    )
    assert "include_test_selection" not in sig_arm.parameters, (
        "swebench_repair_arm must not carry the retired include_test_selection parameter."
    )
