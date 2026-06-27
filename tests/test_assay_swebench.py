"""SWE-bench external-grader Adapter — Sprint 5. Pure binding only: no Docker, no swebench installed.

Covers what the Adapter does WITHOUT the harness: forming the three-field prediction (no invented
fields), writing predictions JSONL, reading `resolved` off a per-instance report.json (including the
model-name '/'->'__' rewrite the harness uses), asserting the run-report schema_version, the
constants-verify no-op when swebench is absent, and the Oracle reading a verdict from a pre-run report
(stamped run-and-observe). The actual harness invocation (`run_swebench`) is env-gated and never called
here — it needs Docker + swebench + image pulls on the Architect's box.
"""

import json

import pytest

from substrate.assay.oracle import EXTERNAL_GRADER
from substrate.assay.swebench import (
    KEY_INSTANCE_ID,
    KEY_MODEL,
    KEY_PREDICTION,
    make_prediction,
    model_patch_from_record,
    read_resolved,
    read_run_report,
    swebench_oracle,
    swebench_record_oracle,
    verify_constants,
    write_predictions,
)


def _record(*kinds_payloads):
    return [{"kind": k, "payload": p} for k, p in kinds_payloads]


def test_model_patch_from_record_takes_the_selected_patch():
    rec = _record(
        ("SuspectFiles", {"files": ["m.py"]}),
        ("SelectedPatch", {"slot": 0, "model_patch": "diff --git a/m.py b/m.py\n+x"}),
    )
    assert model_patch_from_record(rec) == "diff --git a/m.py b/m.py\n+x"
    assert model_patch_from_record(_record(("Exhausted", {"rounds": 2}))) == ""  # no patch -> ""


def test_record_oracle_grades_the_extracted_patch_via_the_injected_grader():
    # stub grade: resolved iff the patch contains "GOOD" — no Docker, proves extraction + wiring.
    oracle = swebench_record_oracle(
        report_root="/unused", dataset_name="d", grade=lambda iid, patch: "GOOD" in patch
    )
    good = _record(("SelectedPatch", {"slot": 0, "model_patch": "diff GOOD"}))
    res = oracle.grade(good, {"instance_id": "pallets__flask-4045"})
    assert res.passed is True and res.metric == "resolved"
    assert res.oracle_class == EXTERNAL_GRADER and res.replayable is False  # run-and-observe, labeled

    bad = _record(("SelectedPatch", {"slot": 0, "model_patch": "diff BAD"}))
    assert oracle.grade(bad, {"instance_id": "x"}).passed is False


def test_record_oracle_drops_graded_test_edits_before_grading():
    # #72 NET 1: the grade boundary filters the SelectedPatch against the instance's test_patch files, so a
    # topology that emits a raw diff (no internal drop) can't weaken a graded test or collide with test_patch.
    captured = []
    oracle = swebench_record_oracle(
        report_root="/unused", dataset_name="d", grade=lambda iid, p: bool(captured.append(p)) or True
    )
    patch = (
        "diff --git a/src/app.py b/src/app.py\n@@ -1 +1 @@\n-x\n+y\n"
        "diff --git a/tests/test_x.py b/tests/test_x.py\n@@ -1 +1 @@\n-assert a\n+assert True\n"
    )
    gt = {
        "instance_id": "i",
        "test_patch": "diff --git a/tests/test_x.py b/tests/test_x.py\n--- a/tests/test_x.py\n+++ b/tests/test_x.py\n",
    }
    oracle.grade(_record(("SelectedPatch", {"slot": 0, "model_patch": patch})), gt)
    graded = captured[0]
    assert "src/app.py" in graded  # the real source edit is graded
    assert "tests/test_x.py" not in graded  # the graded-test edit was dropped before grading


def test_record_oracle_no_patch_is_not_resolved_without_grading():
    calls = []
    oracle = swebench_record_oracle(
        report_root="/unused", dataset_name="d", grade=lambda iid, patch: calls.append(1) or True
    )
    res = oracle.grade(_record(("Exhausted", {"rounds": 1})), "x")  # ground_truth as a bare id
    assert res.passed is False and "no model_patch" in res.detail
    assert calls == []  # the Docker grader is never invoked when there's nothing to grade


def test_make_prediction_has_exactly_the_three_real_fields():
    pred = make_prediction("astropy__astropy-12907", "diff --git a/x b/x\n...", model_name="m")
    assert pred == {
        "instance_id": "astropy__astropy-12907",
        "model_name_or_path": "m",
        "model_patch": "diff --git a/x b/x\n...",
    }
    assert set(pred) == {KEY_INSTANCE_ID, KEY_MODEL, KEY_PREDICTION}  # no invented fields


def test_write_predictions_jsonl_roundtrips(tmp_path):
    preds = [make_prediction("a", "pa"), make_prediction("b", "pb")]
    path = write_predictions(preds, tmp_path / "preds.jsonl")
    lines = path.read_text().strip().splitlines()
    assert [json.loads(line)["instance_id"] for line in lines] == ["a", "b"]


def _write_report(tmp_path, run_id, model, instance_id, resolved):
    d = tmp_path / run_id / model / instance_id
    d.mkdir(parents=True)
    (d / "report.json").write_text(
        json.dumps({instance_id: {"resolved": resolved, "patch_successfully_applied": True}})
    )


def test_read_resolved_reads_the_per_instance_report(tmp_path):
    _write_report(tmp_path, "run1", "substrate-coding-flow", "astropy__astropy-1", True)
    _write_report(tmp_path, "run1", "substrate-coding-flow", "django__django-2", False)
    assert read_resolved(tmp_path, "run1", "substrate-coding-flow", "astropy__astropy-1") is True
    assert read_resolved(tmp_path, "run1", "substrate-coding-flow", "django__django-2") is False


def test_read_resolved_mirrors_the_model_name_slash_rewrite(tmp_path):
    # the harness writes the model dir with '/' -> '__'; read_resolved must mirror that or miss it.
    _write_report(tmp_path, "run1", "org__model", "x-1", True)
    assert read_resolved(tmp_path, "run1", "org/model", "x-1") is True


def test_read_run_report_asserts_schema_version(tmp_path):
    good = tmp_path / "m.run1.json"
    good.write_text(json.dumps({"resolved_ids": ["a"], "total_instances": 1, "schema_version": 2}))
    assert read_run_report(good)["resolved_ids"] == ["a"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema_version": 1}))
    with pytest.raises(ValueError):
        read_run_report(bad)


def test_verify_constants_is_a_noop_without_swebench():
    # swebench is not installed here; verify_constants must return cleanly, not raise.
    verify_constants()


def test_swebench_oracle_grades_from_a_prerun_report(tmp_path):
    _write_report(tmp_path, "run1", "substrate-coding-flow", "astropy__astropy-1", True)
    oracle = swebench_oracle(report_dir=tmp_path, run_id="run1")
    res = oracle.grade([], "astropy__astropy-1")
    assert res.passed is True and res.oracle_class == EXTERNAL_GRADER and res.replayable is False
    # a missing report is not-resolved with a note, never a crash.
    miss = oracle.grade([], "never-ran-instance")
    assert miss.passed is False and "no swebench report" in miss.detail


def test_firewall_check_both_test_id_formats() -> None:
    from substrate.assay.swebench import firewall_check

    clean = {
        "patch": "+++ b/src/m.py\n",
        "test_patch": "+++ b/tests/test_m.py\n",
        "FAIL_TO_PASS": ["tests/test_m.py::test_new"],
    }
    assert firewall_check(clean)[0] is True

    # the gold patch touches a TEST file -> a held-out test could be pre-existing -> leak.
    shared = {
        "patch": "+++ b/tests/test_m.py\n",
        "test_patch": "+++ b/tests/test_m.py\n",
        "FAIL_TO_PASS": ["tests/test_m.py::test_new"],
    }
    assert firewall_check(shared)[0] is False

    # a FAIL_TO_PASS whose file is NOT added by test_patch is pre-existing -> leak.
    preexisting = {
        "patch": "+++ b/src/m.py\n",
        "test_patch": "+++ b/tests/test_other.py\n",
        "FAIL_TO_PASS": ["tests/test_m.py::test_x"],
    }
    assert firewall_check(preexisting)[0] is False

    # django/unittest format: "test (module.Class)" -> module maps to the test_patch file.
    django_clean = {
        "patch": "+++ b/django/db/models.py\n",
        "test_patch": "+++ b/tests/model_fields/tests.py\n",
        "FAIL_TO_PASS": ["test_x (model_fields.tests.SomeTest)"],
    }
    assert firewall_check(django_clean)[0] is True
