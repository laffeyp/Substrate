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
    assert (
        res.oracle_class == EXTERNAL_GRADER and res.replayable is False
    )  # run-and-observe, labeled

    bad = _record(("SelectedPatch", {"slot": 0, "model_patch": "diff BAD"}))
    assert oracle.grade(bad, {"instance_id": "x"}).passed is False


def test_record_oracle_drops_graded_test_edits_before_grading():
    # #72 NET 1: the grade boundary filters the SelectedPatch against the instance's test_patch files, so a
    # topology that emits a raw diff (no internal drop) can't weaken a graded test or collide with test_patch.
    captured = []
    oracle = swebench_record_oracle(
        report_root="/unused",
        dataset_name="d",
        grade=lambda iid, p: bool(captured.append(p)) or True,
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

    # django/unittest format: "test (module.Class)" -> the parser maps `module.sub.Class` to
    # `module/sub.py` and checks FILE EQUALITY against test_patch (F7 fix, review 2026-08-08).
    # So `test_x (model_fields.tests.SomeTest)` derives to `model_fields/tests.py`, and
    # test_patch must add THAT file — not any file with those segments in its path.
    django_clean = {
        "patch": "+++ b/django/db/models.py\n",
        "test_patch": "+++ b/model_fields/tests.py\n",
        "FAIL_TO_PASS": ["test_x (model_fields.tests.SomeTest)"],
    }
    assert firewall_check(django_clean)[0] is True

    # F7 regression: substring-leak of pre-existing tests must fail closed.
    django_leak = {
        "patch": "+++ b/django/db/models.py\n",
        # test_patch adds a file UNDER model_fields/ but NOT the derived-file path
        # `model_fields/tests.py`. Pre-F7 the substring "model_fields" hit and this passed.
        "test_patch": "+++ b/model_fields/regression/new_test.py\n",
        "FAIL_TO_PASS": ["test_x (model_fields.tests.SomeTest)"],
    }
    assert firewall_check(django_leak)[0] is False


# F2 fix (review 2026-08-08): recall@k banking per instance at grade time.
def test_suspect_files_from_record_reads_last_suspects():
    from substrate.assay.swebench import suspect_files_from_record

    rec = _record(
        ("SuspectFiles", {"files": ["a.py", "b.py"]}),
        # A second SuspectFiles later in the record (a re-localize) — LAST wins.
        ("SuspectFiles", {"files": ["c.py", "d.py"]}),
    )
    assert suspect_files_from_record(rec) == ("c.py", "d.py")
    # Empty tuple when the record carries none — a coding record, a topology without localize.
    assert suspect_files_from_record(_record()) == ()


def test_recall_metrics_computed():
    from substrate.assay.swebench import _recall_metrics

    gold_patch = "+++ b/src/a.py\n+++ b/src/b.py\n+++ b/src/c.py\n"
    # 2 of 3 gold files hit -> fractional 0.667, full recall False.
    r, full = _recall_metrics(["src/a.py", "src/b.py", "src/other.py"], gold_patch)
    assert r == pytest.approx(2 / 3)
    assert full is False
    # All 3 hit -> 1.0, full True.
    r, full = _recall_metrics(["src/a.py", "src/b.py", "src/c.py", "extra.py"], gold_patch)
    assert r == pytest.approx(1.0)
    assert full is True
    # None hit -> 0.0, full False.
    r, full = _recall_metrics(["nothing.py"], gold_patch)
    assert r == pytest.approx(0.0)
    assert full is False
    # No gold patch on the instance -> (None, None) so a coding-style oracle doesn't fabricate.
    r, full = _recall_metrics(["a.py"], "")
    assert r is None and full is None


def test_swebench_record_oracle_stamps_recall_on_result():
    # The oracle constructs Result directly (F2 fix) with recall_at_k + full_recall_at_k
    # populated from the record's SuspectFiles + the instance's gold patch. Verifies the
    # end-to-end path: record -> suspects, ground_truth -> gold, Result -> both fields.
    oracle = swebench_record_oracle(
        report_root="/tmp/dummy",
        dataset_name="dummy",
        grade=lambda _iid, _patch: True,  # stub the harness
    )
    rec = _record(
        ("SuspectFiles", {"files": ["src/a.py", "src/b.py"]}),
        ("SelectedPatch", {"slot": 0, "model_patch": "diff --git a/src/a.py b/src/a.py\n+x\n"}),
    )
    ground_truth = {
        "instance_id": "test__x-1",
        "patch": "+++ b/src/a.py\n+++ b/src/b.py\n",  # 2 gold files, both in suspects
        "test_patch": "",
    }
    result = oracle.grade(rec, ground_truth)
    assert result.passed is True
    assert result.recall_at_k == pytest.approx(1.0)
    assert result.full_recall_at_k is True
    assert result.oracle_class == EXTERNAL_GRADER
    # grader_error_band rides on the Result (SWE-bench Lite default 0.078).
    assert result.grader_error_band == pytest.approx(0.078)


def test_swebench_record_oracle_stamps_recall_even_when_patch_empty():
    # A run that emitted no SelectedPatch still gets recall banked — localization can be right
    # while repair fails, and the writeup needs to see that separately.
    oracle = swebench_record_oracle(
        report_root="/tmp/dummy", dataset_name="dummy", grade=lambda _i, _p: False
    )
    rec = _record(
        ("SuspectFiles", {"files": ["src/a.py"]}),  # localizer found the file
        # NO SelectedPatch — repair failed.
    )
    ground_truth = {
        "instance_id": "x",
        "patch": "+++ b/src/a.py\n+++ b/src/b.py\n",  # 2 gold, 1 in suspects
        "test_patch": "",
    }
    result = oracle.grade(rec, ground_truth)
    assert result.passed is False
    assert result.recall_at_k == pytest.approx(0.5)  # 1 of 2 gold files hit
    assert result.full_recall_at_k is False


def test_swebench_record_oracle_recall_none_on_missing_gold_or_suspects():
    # No gold in ground_truth -> None (can't compute).
    oracle = swebench_record_oracle(
        report_root="/tmp/dummy", dataset_name="dummy", grade=lambda _i, _p: True
    )
    result = oracle.grade(
        _record(
            ("SuspectFiles", {"files": ["a.py"]}),
            ("SelectedPatch", {"slot": 0, "model_patch": "x"}),
        ),
        {"instance_id": "x", "patch": "", "test_patch": ""},
    )
    assert result.recall_at_k is None
    assert result.full_recall_at_k is None
