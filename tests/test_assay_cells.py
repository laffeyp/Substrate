"""Cells-file reconstruction — sprint 152 `assay_kind` dispatch.

Pins the two branches of `suite_from_meta`: the pre-152 `"coding"` shape reads exactly as it did
(so any pre-152 cells file — none carried `assay_kind` — still reads coding-style), and the new
`"swebench"` shape reconstructs a Suite from the `.cases.json` sidecar that
`scripts/assay_swebench_confirmatory.py` writes (sprint 144a gap #7). An unknown `assay_kind` raises
rather than silently coding-parsing SWE-bench data — the signal-not-guess posture the vocab-as-
contract discipline requires.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from substrate.assay.cells import (
    CODING_ASSAY_KIND,
    SWEBENCH_ASSAY_KIND,
    read_cases_sidecar,
    report_from_cells,
    suite_from_meta,
)


def _write_swebench_fixture(tmp_path: Path, *, arm: str = "swebench_solver") -> Path:
    """Two firewall-clean SWE-bench cells + the meta + the sidecar. Config is fingerprint-stamped so
    provenance reads `verified` (the same shape bench_coding.py writes for the coding path)."""
    cfg = {
        "assay_kind": SWEBENCH_ASSAY_KIND,
        "arm_name": arm,
        "role": "full",
        "control_arm": arm,
        "models": ["stub-model"],
        "n": 3,
        "margin": 0.10,
        "pass_k": 1,
        "dataset": "princeton-nlp/SWE-bench_Lite",
        "split": "test",
    }
    fp = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:12]
    meta = {"config_fp": fp, "run_id": "test-run", **cfg}
    cells = tmp_path / "swebench_cells.jsonl"
    rows = [
        {
            "arm": arm,
            "role": "full",
            "case_id": "pallets_1776_flask-4045",
            "trial": 0,
            "passed": True,
            "elapsed_ms": 1000,
            "config_fp": fp,
            "run_id": "test-run",
            "source": "run",
        },
        {
            "arm": arm,
            "role": "full",
            "case_id": "astropy_1776_astropy-12907",
            "trial": 0,
            "passed": False,
            "elapsed_ms": 2000,
            "config_fp": fp,
            "run_id": "test-run",
            "source": "run",
        },
    ]
    cells.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (cells.with_suffix(".meta.json")).write_text(json.dumps(meta, indent=2, sort_keys=True))
    sidecar = [
        {
            "case_id": "pallets_1776_flask-4045",
            "instance_id": "pallets__flask-4045",
            "repo": "pallets/flask",
            "base_commit": "abc123",
            "version": "2.0",
            "image": "sweb.eval.x86_64.pallets_1776_flask-4045:latest",
            "regression_files": ["tests/test_blueprints.py"],
            "exclude": ["tests/test_basic.py"],
            "passed_at_base": ["test_a", "test_b"],
        },
        {
            "case_id": "astropy_1776_astropy-12907",
            "instance_id": "astropy__astropy-12907",
            "repo": "astropy/astropy",
            "base_commit": "def456",
            "version": "5.0",
            "image": "sweb.eval.x86_64.astropy_1776_astropy-12907:latest",
            "regression_files": ["astropy/modeling/tests/test_separable.py"],
            "exclude": ["astropy/modeling/tests/test_grade.py"],
            "passed_at_base": ["test_c"],
        },
    ]
    (tmp_path / "swebench_cells.cases.json").write_text(
        json.dumps(sidecar, indent=2, sort_keys=True)
    )
    return cells


def test_default_assay_kind_is_coding_backwards_compatible():
    # Pre-152 cells files carried no `assay_kind` key. `suite_from_meta({})` must still return the
    # coding Suite it always did — no silent breaking change for existing readers.
    suite = suite_from_meta({})
    assert suite.name.startswith("coding")


def test_swebench_kind_reconstructs_from_sidecar():
    # The load-bearing path: `assay_kind == "swebench"` + a full `.cases.json` sidecar yields a
    # Suite whose case_ids match the sidecar entries and whose control arm is the meta's arm_name.
    meta = {
        "assay_kind": SWEBENCH_ASSAY_KIND,
        "arm_name": "swebench_solver",
        "control_arm": "swebench_solver",
        "margin": 0.10,
    }
    sidecar = [
        {"case_id": "case_a", "instance_id": "pallets__flask-4045"},
        {"case_id": "case_b", "instance_id": "astropy__astropy-12907"},
    ]
    rows = [
        {"arm": "swebench_solver", "role": "full", "case_id": "case_a"},
        {"arm": "swebench_solver", "role": "full", "case_id": "case_b"},
    ]
    suite = suite_from_meta(meta, rows=rows, cases_sidecar=sidecar)
    assert suite.name == "swebench"
    assert [c.case_id for c in suite.cases] == ["case_a", "case_b"]
    assert suite.cases[0].ground_truth == {"instance_id": "pallets__flask-4045"}
    assert suite.control_arm == "swebench_solver"
    assert len(suite.arms) == 1
    assert suite.arms[0].name == "swebench_solver"


def test_swebench_kind_falls_back_to_rows_when_sidecar_missing():
    # A mid-flight abort might leave the JSONL without the sidecar. The reconstruction must still
    # yield a scorable Suite from the observed case_ids in rows — good enough for the paired
    # comparison, only missing the per-instance metadata a substrate-ui pane would render.
    meta = {"assay_kind": SWEBENCH_ASSAY_KIND, "arm_name": "swebench_solver"}
    rows = [
        {"arm": "swebench_solver", "role": "full", "case_id": "case_a"},
        {"arm": "swebench_solver", "role": "full", "case_id": "case_b"},
    ]
    suite = suite_from_meta(meta, rows=rows, cases_sidecar=[])
    assert [c.case_id for c in suite.cases] == ["case_a", "case_b"]
    # ground_truth degrades to just the case_id (no instance_id available without the sidecar).
    assert suite.cases[0].ground_truth == {"instance_id": "case_a"}


def test_swebench_kind_reconstructs_multiple_arms_from_rows():
    # Sprint 159 introduces multi-arm SWE-bench runs. The reconstruction reads arm structure from
    # the OBSERVED rows so a report grades whatever actually ran, not what meta was configured to
    # run — the control_arm from meta anchors the pairing.
    meta = {
        "assay_kind": SWEBENCH_ASSAY_KIND,
        "arm_name": "single_draft_baseline",
        "control_arm": "single_draft_baseline",
    }
    rows = [
        {"arm": "single_draft_baseline", "role": "baseline", "case_id": "case_a"},
        {"arm": "n_drafts_repair", "role": "full", "case_id": "case_a"},
        {"arm": "n_drafts_repair", "role": "full", "case_id": "case_b"},
    ]
    suite = suite_from_meta(meta, rows=rows, cases_sidecar=[])
    arm_names = {a.name for a in suite.arms}
    assert arm_names == {"single_draft_baseline", "n_drafts_repair"}
    assert suite.control_arm == "single_draft_baseline"


def test_unknown_assay_kind_raises_rather_than_silently_defaulting():
    # A future assay kind should surface at read time as a versioning event, NOT read the wrong
    # dispatch and produce a nonsense report. The error names the supported values so a caller has
    # a fix path in the message itself.
    with pytest.raises(ValueError, match="unknown assay_kind"):
        suite_from_meta({"assay_kind": "not-a-real-kind"})


def test_report_from_cells_dispatches_swebench_end_to_end(tmp_path):
    # The full read path: the confirmatory-runner-shape fixture (meta + jsonl + sidecar) rebuilds
    # into a real Report through `report_from_cells`. Two cases, one arm, one trial each; the arm
    # IS the control so `delta_vs_control` is None (there is nothing to pair against) but the
    # `passes`/`pass_rate` land on the ArmReport and the `_provenance` reads `verified` because
    # the flat meta shape is what sprint 144a gap #5 fixed.
    cells = _write_swebench_fixture(tmp_path)
    report, meta = report_from_cells(cells)
    assert report.suite == "swebench"
    assert report.control_arm == "swebench_solver"
    assert meta["_provenance"] == "verified"  # gap #5 pin — nested meta would report "tampered"
    (arm_report,) = report.arms
    assert arm_report.arm == "swebench_solver"
    assert arm_report.n_cases == 2
    assert arm_report.passes == 1
    assert arm_report.pass_rate == pytest.approx(0.5)


def test_swebench_kind_raises_when_neither_sidecar_nor_rows_have_cases():
    # A meta claiming SWE-bench with zero rows and no sidecar has nothing to reconstruct against;
    # `build_report` would silently produce an empty Report, which is exactly the shape a caller
    # might mistake for a legitimate zero-result run. Fail loud instead.
    with pytest.raises(ValueError, match="cannot reconstruct a SWE-bench Suite"):
        suite_from_meta({"assay_kind": SWEBENCH_ASSAY_KIND}, rows=[], cases_sidecar=[])


def test_read_cases_sidecar_returns_empty_when_absent(tmp_path):
    # `report_from_cells` must not crash on a coding cells file whose `.cases.json` never existed
    # — it should return `[]` and the coding branch of `suite_from_meta` simply ignores it.
    cells = tmp_path / "coding_cells.jsonl"
    cells.write_text("")
    assert read_cases_sidecar(cells) == []


def test_read_cases_sidecar_rejects_a_non_array(tmp_path):
    # A `.cases.json` that isn't a JSON array is a corrupt sidecar — refuse to parse it into
    # something a downstream reader would silently mis-shape. The runtime file layout is a
    # contract.
    cells = tmp_path / "corrupt_cells.jsonl"
    cells.write_text("")
    (cells.with_suffix(".cases.json")).write_text(json.dumps({"not": "a list"}))
    with pytest.raises(ValueError, match="malformed"):
        read_cases_sidecar(cells)


def test_coding_dispatch_still_reads_a_coding_fixture(tmp_path):
    # A coding cells file (no `assay_kind` in meta — pre-152 shape) must reach the coding branch
    # and produce a Report with the coding Suite's name. This is the backward-compat regression.
    from substrate.assay.coding_problems import coding_problem_bank

    cfg = {
        "strong_model": "s",
        "weak_models": ["w"],
        "trials": 1,
        "margin": 0.1,
        "n_problems": min(2, len(coding_problem_bank())),
    }
    fp = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:12]
    meta = {"config_fp": fp, "run_id": "coding-r1", **cfg}
    cells = tmp_path / "coding_cells.jsonl"
    rows = [
        {
            "arm": "strong_ref",
            "role": "baseline",
            "case_id": coding_problem_bank()[0].problem_id,
            "trial": 0,
            "passed": True,
            "elapsed_ms": 100,
            "config_fp": fp,
            "run_id": "coding-r1",
        }
    ]
    cells.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (cells.with_suffix(".meta.json")).write_text(json.dumps(meta, indent=2, sort_keys=True))
    report, meta_out = report_from_cells(cells)
    assert report.suite == "coding-firewalled"
    assert meta_out["_provenance"] == "verified"


def test_swebench_two_arm_report_exercises_delta_verdict_and_ci(tmp_path, monkeypatch):
    # Review finding 152-#1: the single-arm end-to-end test never invoked the delta/verdict/CI
    # path because the one arm was its own control. This test adds a second arm so `build_report`
    # actually runs the bootstrap CI + score-adjacent verdict shape through the SWE-bench
    # dispatch. A control arm that never resolves + a candidate arm that always resolves gives a
    # loud SUPERIOR signal — enough to pin the shape, not enough to over-fit on numbers.
    #
    # `_has_committed_record` is stubbed to True because this test's subject is the SWE-bench
    # dispatch + build_report shape, NOT the control-ran conformance guard (that has its own
    # tests at test_assay_control_plane.py:127). Writing 12 hand-crafted RunFinalised records
    # here would test the record loader, not the dispatch — the wrong subject.
    monkeypatch.setattr("substrate.assay.conformance._has_committed_record", lambda _root: True)
    cfg = {
        "assay_kind": SWEBENCH_ASSAY_KIND,
        "arm_name": "candidate",
        "role": "full",
        "control_arm": "control",
        "margin": 0.10,
        "pass_k": 1,
    }
    fp = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:12]
    meta = {"config_fp": fp, "run_id": "two-arm-run", **cfg}
    cells = tmp_path / "two_arm.jsonl"

    case_ids = [f"case_{i:03d}" for i in range(6)]
    rows = []
    for cid in case_ids:
        rows.append(
            {
                "arm": "control",
                "role": "baseline",
                "case_id": cid,
                "trial": 0,
                "passed": False,
                "elapsed_ms": 100,
                "config_fp": fp,
                "run_id": "two-arm-run",
            }
        )
        rows.append(
            {
                "arm": "candidate",
                "role": "full",
                "case_id": cid,
                "trial": 0,
                "passed": True,
                "elapsed_ms": 200,
                "config_fp": fp,
                "run_id": "two-arm-run",
            }
        )
    cells.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (cells.with_suffix(".meta.json")).write_text(json.dumps(meta, indent=2, sort_keys=True))
    sidecar = [
        {"case_id": cid, "instance_id": f"repo__thing-{i}"} for i, cid in enumerate(case_ids)
    ]
    (tmp_path / "two_arm.cases.json").write_text(json.dumps(sidecar, indent=2, sort_keys=True))

    report, _meta = report_from_cells(cells)
    assert report.control_arm == "control"
    by_name = {a.arm: a for a in report.arms}
    assert set(by_name) == {"control", "candidate"}

    # control has None on every delta field — it IS the control.
    ctrl = by_name["control"]
    assert ctrl.delta_vs_control is None
    assert ctrl.discordant_control_only is None
    assert ctrl.equivalence is None
    assert ctrl.pass_rate == 0.0  # substance check, not just wiring

    # candidate: 6/6 passes vs control's 0/6 -> delta = +1.0, all 6 pairs discordant arm-only,
    # McNemar p tiny, bootstrap CI clears +margin -> SUPERIOR verdict.
    cand = by_name["candidate"]
    assert cand.pass_rate == 1.0
    assert cand.delta_vs_control == pytest.approx(1.0)
    assert cand.discordant_control_only == 0
    assert cand.discordant_arm_only == 6
    assert cand.p_value is not None and cand.p_value < 0.05
    assert cand.ci_low is not None and cand.ci_high is not None
    assert cand.ci_low > 0.0  # the whole CI sits above zero — a real difference
    assert cand.equivalence == "superior"  # from stats.SUPERIOR


def test_cells_module_exposes_kind_constants():
    # A downstream reader (substrate-ui, docs) should not need to know the string values by heart;
    # exporting the constants keeps the vocab-as-contract discipline at the module boundary.
    assert CODING_ASSAY_KIND == "coding"
    assert SWEBENCH_ASSAY_KIND == "swebench"
