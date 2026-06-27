"""SWE-bench external-grader Adapter — Sprint 5.

Binds the assay layer's external-grader Oracle to the OFFICIAL swebench evaluation harness, per
docs/swebench-bridge-mapping.md (reverse-engineered from the real princeton-nlp/SWE-bench source, pin
4.1.0). The harness grades by running each instance in Docker and writing a per-instance report.json
with a `resolved` bool — an EXTERNAL, non-deterministic system, so this is an external-grader Oracle
(run-and-observe, NOT replayable), exactly the class the design reserves for it (design §3).

Pure and tested here: forming the prediction (the three real fields, no invention), reading `resolved`
off a report, reading the run report (asserting schema_version 2 so a harness bump fails loudly), and
verifying our field-name constants against the installed swebench when present (the bridge-mapping
discipline, executable). ENV-GATED (Docker + swebench + image pulls, on the Architect's box, never in
this session / CI): actually invoking the harness — `run_swebench` lazy-imports swebench and is the
run-and-observe truth source whose verdict is captured once. The Adapter never constructs Docker image
names by hand (the `__`->`_1776_` / arch / namespace rules live in swebench's TestSpec); it drives the
harness and reads its reports.

VALIDATION PATH (Architect's box): the harness accepts the literal predictions_path `"gold"` to run the
reference patches — so the binding can be differential-tested (gold must resolve; an empty patch must
not) WITHOUT any topology, isolating Adapter correctness from topology quality. Do that first.

Note: SWE-bench-Live (the contamination-dated split the design wants as PRIMARY) ships its OWN harness
and image set keyed by an `image_key` column — a DISTINCT backend, not wired here; this module targets
the stock swebench harness. SWE-bench-Live is a follow-up backend (bridge mapping §5.2 / §6).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .oracle import EXTERNAL_GRADER, ExternalGraderOracle, Result

# The prediction field names — the bridge mapping's KEY_* constants (swebench/harness/constants).
# Bound as literals so forming a prediction needs no swebench import; `verify_constants()` checks them
# against the installed package so a version bump that renamed a key fails loudly, not silently.
KEY_INSTANCE_ID = "instance_id"
KEY_MODEL = "model_name_or_path"
KEY_PREDICTION = "model_patch"

DEFAULT_MODEL_NAME = "substrate-coding-flow"


def make_prediction(
    instance_id: str, model_patch: str, *, model_name: str = DEFAULT_MODEL_NAME
) -> dict[str, str]:
    """The exactly-three-field prediction the harness consumes (no extra/invented fields). `model_patch`
    is a unified git diff applied at the instance's base_commit; an empty patch is allowed (the harness
    counts it as an empty-patch instance, not an error)."""
    return {KEY_INSTANCE_ID: instance_id, KEY_MODEL: model_name, KEY_PREDICTION: model_patch}


def write_predictions(predictions: Sequence[Mapping[str, str]], path: Path | str) -> Path:
    """Write predictions as JSONL (one object per line) — the harness loader accepts a JSON array or
    JSONL file. Returns the path written."""
    p = Path(path)
    p.write_text("\n".join(json.dumps(dict(pred)) for pred in predictions) + "\n")
    return p


def read_resolved(report_dir: Path | str, run_id: str, model_name: str, instance_id: str) -> bool:
    """Read the per-instance report.json and return its `resolved` bool (True ONLY on full resolution —
    FAIL_TO_PASS rate == 1.0 AND PASS_TO_PASS rate == 1.0; a partial fix is False, the all-or-nothing
    rule).

    The on-disk LOCATION has churned across swebench versions and is the most fragile part of this
    binding: the CLI default `report_dir` is ".", some versions nest under `logs/run_evaluation`, and
    the report.json may land in CWD regardless of `report_dir`. So SEARCH the known candidate roots
    rather than trust one hand-built path — and the **gold-differential test** (`predictions="gold"`)
    on the Architect's box is what PINS the real path against the installed wheel. Until a report is
    found, treat it as not-resolved (raise FileNotFoundError, which `swebench_oracle` turns into a
    not-resolved verdict with a note) — NEVER a hard pass."""
    safe_model = model_name.replace("/", "__")
    rel = Path(run_id) / safe_model / instance_id / "report.json"
    candidates = [
        Path(report_dir) / rel,
        Path(report_dir) / "logs" / "run_evaluation" / rel,
        Path.cwd() / rel,
        Path.cwd() / "logs" / "run_evaluation" / rel,
    ]
    for path in candidates:
        if path.exists():
            data = json.loads(path.read_text())
            entry = data.get(instance_id, {})
            return bool(entry.get("resolved", False))
    raise FileNotFoundError(
        f"no swebench report.json for {instance_id} in any known location "
        f"(searched {[str(c) for c in candidates]}); pin the path with the gold-differential test"
    )


def read_run_report(path: Path | str) -> dict[str, Any]:
    """Read the final run report ({model(/->__)}.{run_id}.json) and return it, asserting
    schema_version == 2 so a future harness schema bump fails loudly rather than being mis-parsed."""
    data: dict[str, Any] = json.loads(Path(path).read_text())
    schema = data.get("schema_version")
    if schema != 2:
        raise ValueError(
            f"swebench run-report schema_version 2 expected; got {schema!r} — "
            "re-verify docs/swebench-bridge-mapping.md against the pinned swebench"
        )
    return data


def verify_constants() -> None:
    """If swebench is importable, assert our prediction field-name literals match its constants — the
    bridge-mapping discipline made executable. A no-op (returns) when swebench is absent, so it is safe
    to call in any environment."""
    try:
        import swebench.harness.constants as sw  # lazy, env-gated (mypy: see [tool.mypy.overrides])
    except Exception:
        return
    drift = {
        name: (ours, theirs)
        for name, ours, theirs in (
            ("instance_id", KEY_INSTANCE_ID, sw.KEY_INSTANCE_ID),
            ("model", KEY_MODEL, sw.KEY_MODEL),
            ("prediction", KEY_PREDICTION, sw.KEY_PREDICTION),
        )
        if ours != theirs
    }
    if drift:
        raise AssertionError(
            f"swebench key constants drifted from the bridge mapping: {drift} — re-verify it"
        )


def run_swebench(
    predictions: Sequence[Mapping[str, str]],
    *,
    dataset_name: str,
    run_id: str,
    instance_ids: Sequence[str],
    report_dir: Path | str,
    split: str = "test",
    max_workers: int = 4,
    timeout: int = 1800,
    namespace: str = "swebench",
) -> dict[str, Any]:
    """ENV-GATED (Docker + swebench + image pulls — runs on the Architect's box, NEVER in this session
    or CI). Write the predictions, invoke the official harness over the named dataset/instances, and
    return the parsed run report. Lazy-imports swebench so this module imports without it. This is the
    run-and-observe truth source; its verdict is captured once and is not reproducible by replay."""
    from swebench.harness import run_evaluation  # lazy, env-gated (mypy: see [tool.mypy.overrides])

    verify_constants()
    rdir = Path(report_dir)
    rdir.mkdir(parents=True, exist_ok=True)
    preds_path = write_predictions(predictions, rdir / f"preds_{run_id}.jsonl")
    run_evaluation.main(
        dataset_name=dataset_name,
        split=split,
        instance_ids=list(instance_ids),
        predictions_path=str(preds_path),
        max_workers=max_workers,
        force_rebuild=False,
        cache_level="env",
        clean=False,
        open_file_limit=4096,
        run_id=run_id,
        timeout=timeout,
        namespace=namespace,
        rewrite_reports=False,
        modal=False,
        report_dir=str(rdir),
    )
    model_name = predictions[0][KEY_MODEL] if predictions else DEFAULT_MODEL_NAME
    # the harness writes the final run report to CWD (not report_dir) in swebench 4.x — search both,
    # the same path-churn lesson as read_resolved (pinned empirically on the Architect's arm64 box).
    report_name = f"{model_name.replace('/', '__')}.{run_id}.json"
    for cand in (rdir / report_name, Path.cwd() / report_name):
        if cand.exists():
            return read_run_report(cand)
    raise FileNotFoundError(f"no swebench run report {report_name} in {rdir} or {Path.cwd()}")


def swebench_oracle(
    *, report_dir: Path | str, run_id: str, model_name: str = DEFAULT_MODEL_NAME
) -> ExternalGraderOracle:
    """An external-grader Oracle grading a coding run against SWE-bench: it reads the per-instance
    `resolved` from the harness report. The harness grades a BATCH (run_swebench over all instances)
    BEFORE this Oracle reads one instance's verdict — so a SWE-bench assay runs the batch harness, then
    the control plane reads each Case's verdict through this Oracle. `ground_truth` is the instance_id.
    A missing report (the harness produced none for that instance) grades as not-resolved with a note,
    never a crash. The grade is run-and-observe (replayable=False)."""

    def grader(_record: list[Mapping[str, Any]], ground_truth: Any) -> tuple[bool, str]:
        instance_id = str(ground_truth)
        try:
            resolved = read_resolved(report_dir, run_id, model_name, instance_id)
        except FileNotFoundError:
            return (False, f"no swebench report for {instance_id} (harness produced none)")
        return (resolved, f"swebench resolved={resolved} for {instance_id}")

    return ExternalGraderOracle(grader=grader, metric="resolved")


__all__ = [
    "KEY_INSTANCE_ID",
    "KEY_MODEL",
    "KEY_PREDICTION",
    "DEFAULT_MODEL_NAME",
    "make_prediction",
    "write_predictions",
    "read_resolved",
    "read_run_report",
    "verify_constants",
    "run_swebench",
    "swebench_oracle",
]

# re-exported for callers that grade via the Oracle directly
_ = (EXTERNAL_GRADER, Result)
