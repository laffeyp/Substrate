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

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
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


class FirewallViolation(ValueError):
    """Sprint 143 — typed exception raised by `prepare_swebench_case` when `firewall_check` fails.

    Categorical (not stringly-typed) so a caller that catches the wrong ValueError does not
    silently admit a leaky instance. IS-A ValueError, so existing broad handlers keep working; new
    code should catch `FirewallViolation` explicitly. The `reason` attribute carries the string
    `firewall_check` returned.
    """

    def __init__(self, instance_id: str, reason: str) -> None:
        super().__init__(f"instance {instance_id} fails the firewall: {reason}")
        self.instance_id = instance_id
        self.reason = reason


def make_prediction(
    instance_id: str, model_patch: str, *, model_name: str = DEFAULT_MODEL_NAME
) -> dict[str, str]:
    """The exactly-three-field prediction the harness consumes (no extra/invented fields). `model_patch`
    is a unified git diff applied at the instance's base_commit; an empty patch is allowed (the harness
    counts it as an empty-patch instance, not an error)."""
    return {KEY_INSTANCE_ID: instance_id, KEY_MODEL: model_name, KEY_PREDICTION: model_patch}


def firewall_check(instance: Mapping[str, Any]) -> tuple[bool, str]:
    """Per-instance firewall assertion (reviews #53 / #58 / #64) — the solver may NEVER see the held-out
    tests. Two conditions, both data-level over the instance:

      - files(patch) ∩ files(test_patch) == ∅: the gold SOURCE fix does not touch the graded test files.
        A shared file means a held-out (FAIL_TO_PASS) test could be a PRE-EXISTING test the gold patch
        flips fail->pass — present at base_commit, visible to the solver. That instance leaks the grade.
      - every FAIL_TO_PASS test file ∈ files(test_patch): the graded tests are ADDED by test_patch, so they
        are ABSENT from the base repo the solver works on (the structural firewall).

    Returns (ok, reason). Exclude or flag any instance that fails when assembling a firewall-clean set;
    prefer SWE-bench_Verified (human-curated) as the base."""
    import ast
    import re

    def _added_files(diff: str) -> set[str]:
        return {
            ln[6:] for ln in diff.splitlines() if ln.startswith("+++ b/") and ln[6:] != "dev/null"
        }

    def _f2p_in_test_patch(test_id: str, tp_files: set[str]) -> bool:
        # pytest: "path/test_x.py::Class::test" -> the file is the path before "::".
        if "::" in test_id:
            return test_id.split("::")[0] in tp_files
        # unittest/django: "test_func (module.sub.Class)" -> the parenthesised group is the module
        # path, with a trailing class name. Drop the class, dot-join the module segments, append
        # ".py" — that IS the file path convention unittest uses. Compare for EQUALITY against
        # test_patch's added files, not substring.
        #
        # F7 fix (review 2026-08-08): the pre-fix "any(frag in f for f in tp_files)" was substring
        # match. For "test_x (myapp.tests)" -> frag = "myapp", which matched ANY tp_file under
        # myapp/ — so a pre-existing test at myapp/other/test_foo.py passed the firewall whenever
        # test_patch happened to add anything under myapp/. That is the exact leak the firewall
        # exists to catch.
        m = re.search(r"\(([\w.]+)\)", test_id)
        if not m:
            # Fail CLOSED on parse failure (sprint 142): an unparseable FAIL_TO_PASS id cannot be
            # verified to be added by test_patch, so we cannot certify the structural firewall for
            # this instance. Condition 1 (patch/test_patch file intersection) does NOT cover this
            # case — it catches shared source files, not held-out test ids we cannot resolve to a
            # file. Returning False here classifies the id as leaked (absent from test_patch);
            # firewall_check then surfaces it in the `leaked` list and the instance is excluded.
            return False
        parts = m.group(1).split(".")
        if len(parts) < 2:
            # A one-segment parenthesised group ("test_func (something)") is not a module.Class
            # form — cannot resolve to a file. Fail closed, same reason as unparseable ids.
            return False
        module_path = "/".join(parts[:-1]) + ".py"
        return module_path in tp_files

    patch_files = _added_files(str(instance.get("patch", "")))
    tp_files = _added_files(str(instance.get("test_patch", "")))
    f2p_raw = instance.get("FAIL_TO_PASS", [])
    f2p = ast.literal_eval(f2p_raw) if isinstance(f2p_raw, str) else list(f2p_raw)

    shared = patch_files & tp_files
    if shared:
        return (False, f"patch and test_patch share files (grade leak): {sorted(shared)}")
    leaked = [str(t) for t in f2p if not _f2p_in_test_patch(str(t), tp_files)]
    if leaked:
        return (
            False,
            f"FAIL_TO_PASS tests not added by test_patch (pre-existing -> leak): {leaked[:3]}",
        )
    return (True, "firewall ok")


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


def model_patch_from_record(record: Sequence[Mapping[str, Any]]) -> str:
    """The model_patch an Arm produced, read off its inner record: the last `SelectedPatch` event's
    `model_patch`. This is the SWE-bench Arm CONTRACT — a topology is a valid arm iff it emits a
    SelectedPatch carrying the diff. Empty string if the Arm emitted none (no candidate survived) ->
    graded not-resolved, never a crash."""
    patches = [e["payload"]["model_patch"] for e in record if e.get("kind") == "SelectedPatch"]
    return str(patches[-1]) if patches else ""


def grade_patch(
    instance_id: str,
    model_patch: str,
    *,
    report_root: Path | str,
    dataset_name: str,
    model_name: str = DEFAULT_MODEL_NAME,
    namespace: str = "swebench",
) -> bool:
    """ENV-GATED (Docker). Grade ONE model_patch for ONE instance via the official harness; return
    resolved. The run_id is HASHED from (model_name, patch) so distinct patches grade fresh and the
    swebench harness never reuses a prior run's verdict for this instance (the run_id cache-collision
    lesson — a constant run_id makes the harness skip re-evaluation and report a stale grade). An empty
    patch is not-resolved without invoking Docker."""
    if not model_patch.strip():
        return False
    h = hashlib.sha1(f"{model_name}:{model_patch}".encode()).hexdigest()[:10]
    run_id = f"assay-{instance_id}-{h}"
    rdir = Path(report_root) / instance_id
    pred = make_prediction(instance_id, model_patch, model_name=model_name)
    run_swebench(
        [pred],
        dataset_name=dataset_name,
        run_id=run_id,
        instance_ids=[instance_id],
        report_dir=rdir,
        max_workers=1,
        namespace=namespace,
    )
    return read_resolved(rdir, run_id, model_name, instance_id)


def swebench_record_oracle(
    *,
    report_root: Path | str,
    dataset_name: str,
    model_name: str = DEFAULT_MODEL_NAME,
    grade: Callable[[str, str], bool] | None = None,
) -> ExternalGraderOracle:
    """The SWE-bench external-grader Oracle for the assay control plane: grade an ARM'S RECORD against a
    SWE-bench instance. It extracts the model_patch the Arm emitted (`SelectedPatch`) and grades it with
    the official Docker harness, reporting `resolved`. `ground_truth` is the instance (a mapping carrying
    `instance_id`, or the id itself). Run-and-observe (replayable=False). `grade(instance_id, patch)->bool`
    overrides the Docker call for tests; the default grades for real via `grade_patch`. A run that emitted
    no patch grades not-resolved with a note, never a crash."""

    def _default_grade(instance_id: str, model_patch: str) -> bool:
        return grade_patch(
            instance_id,
            model_patch,
            report_root=report_root,
            dataset_name=dataset_name,
            model_name=model_name,
        )

    do_grade = grade or _default_grade

    def grader(record: list[Mapping[str, Any]], ground_truth: Any) -> tuple[bool, str]:
        instance_id = (
            str(ground_truth["instance_id"])
            if isinstance(ground_truth, Mapping)
            else str(ground_truth)
        )
        patch = model_patch_from_record(record)
        if not patch.strip():
            return (
                False,
                f"no model_patch on the record for {instance_id} (the Arm produced none)",
            )
        # drop edits to the GRADE's test files at the grade boundary (#72 NET 1): the inflation guard, applied
        # HERE so a topology that emits a raw diff (no internal drop, e.g. the repair topology) can't weaken a
        # graded test or collide with the held-out test_patch. Harness-side — the topology never sees test_patch.
        if isinstance(ground_truth, Mapping) and ground_truth.get("test_patch"):
            from .swebench_workspace import filter_diff, graded_test_files

            patch = filter_diff(
                patch, drop_files=frozenset(graded_test_files(str(ground_truth["test_patch"])))
            )
            if not patch.strip():
                return (False, f"patch empty after dropping graded-test edits for {instance_id}")
        resolved = do_grade(instance_id, patch)
        return (resolved, f"swebench resolved={resolved} for {instance_id} ({len(patch)}b patch)")

    return ExternalGraderOracle(grader=grader, metric="resolved")


__all__ = [
    "KEY_INSTANCE_ID",
    "KEY_MODEL",
    "KEY_PREDICTION",
    "DEFAULT_MODEL_NAME",
    "FirewallViolation",
    "firewall_check",
    "make_prediction",
    "write_predictions",
    "read_resolved",
    "read_run_report",
    "verify_constants",
    "run_swebench",
    "swebench_oracle",
    "model_patch_from_record",
    "grade_patch",
    "swebench_record_oracle",
]

# re-exported for callers that grade via the Oracle directly
_ = (EXTERNAL_GRADER, Result)
