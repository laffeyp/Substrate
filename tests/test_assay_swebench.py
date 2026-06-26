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
    read_resolved,
    read_run_report,
    swebench_oracle,
    verify_constants,
    write_predictions,
)


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
