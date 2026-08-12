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
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from msgspec import Struct

from .oracle import EXTERNAL_GRADER, ExternalGraderOracle, Result, Verdict

# Default grader_error_band for SWE-bench Lite (Xia & Chen 2025, arxiv 2503.15223). Rides on every
# SWE-bench Result so headline numbers can honestly report `resolved ± band × resolved`. Verified
# splits are ~0.02; SWE-bench-Live has no published residual.
_LITE_GRADER_ERROR_BAND = 0.078

# The prediction field names — the bridge mapping's KEY_* constants (swebench/harness/constants).
# Bound as literals so forming a prediction needs no swebench import; `verify_constants()` checks them
# against the installed package so a version bump that renamed a key fails loudly, not silently.
KEY_INSTANCE_ID = "instance_id"
KEY_MODEL = "model_name_or_path"
KEY_PREDICTION = "model_patch"

DEFAULT_MODEL_NAME = "substrate-coding-flow"


# H-3 (ratified 2026-08-10): the closed set of `reason` strings shared by the oracle and the
# runner. Every `NO_VERDICT` verdict carries exactly one of these strings; every runner-side
# cell-level error uses the same lexicon. `pass`/`fail` verdicts carry the empty string.
# One vocabulary, one translation table (design v3 §"The oracle contract"). Verified callers
# import the named constants, not the raw literals — the closed set is checked at the writer
# boundary.
REASON_TIMED_OUT = "timed_out"
REASON_CONTAINER_CRASHED = "container_crashed"
REASON_DOCKER_ERROR = "docker_error"
REASON_HARNESS_ERROR = "harness_error"
REASON_GIT_ERROR = "git_error"
REASON_FIREWALL_VIOLATION = "firewall_violation"
# Design DESIGN-2026-08-11-responder-rate-limit-shim.md §"Closed-set additions":
# a provider (Ollama Cloud tier, OpenAI RPM, Anthropic TPM, ...) rate-limited the
# request. Different from `harness_error` (a harness exception) and from
# `timed_out` (wall-clock exceeded); a rate-limit is a "capacity denied at the
# provider's gate" state. The 2026-08-10 N=300 Lite v2 run had 3337 rows that
# should have carried this reason but landed as no_verdict/harness_error.
REASON_RATE_LIMITED = "rate_limited"

_HARNESS_REASONS: frozenset[str] = frozenset(
    {
        REASON_TIMED_OUT,
        REASON_CONTAINER_CRASHED,
        REASON_DOCKER_ERROR,
        REASON_HARNESS_ERROR,
        REASON_GIT_ERROR,
        REASON_FIREWALL_VIOLATION,
        REASON_RATE_LIMITED,
    }
)

# Per-repo wall-clock timeouts for the harness (seconds). Loaded from swebench_timeouts.json
# so the pre-registration can pin the table's sha256. The default when a repo is unknown
# is 60 min — the design's fallback for the confirmatory (v3 §"The grader contract").
_DEFAULT_TIMEOUT_SECONDS = 60 * 60
_SWEBENCH_TIMEOUTS_PATH = Path(__file__).parent / "swebench_timeouts.json"


def read_swebench_timeouts(path: Path | None = None) -> dict[str, int]:
    """Load the per-repo timeout table (seconds). Path defaults to
    `assay/swebench_timeouts.json`; the pre-reg pins its sha256 so a change trips the gate.
    Returns {repo -> seconds}; empty dict if the file is absent (callers fall back to the
    default via `timeout_for_instance`)."""
    p = path or _SWEBENCH_TIMEOUTS_PATH
    if not p.exists():
        return {}
    return {str(k): int(v) for k, v in json.loads(p.read_text()).items()}


def timeout_for_instance(instance_id: str, table: Mapping[str, int] | None = None) -> int:
    """The wall-clock deadline for one instance (seconds). Reads the repo prefix off the
    instance_id (`{owner}__{repo}-{issue}` -> `{owner}/{repo}`) and looks it up in the table;
    falls back to `_DEFAULT_TIMEOUT_SECONDS` on any miss."""
    if table is None:
        table = read_swebench_timeouts()
    # instance_id shape: `astropy__astropy-12345`
    if "__" in instance_id:
        owner, _, rest = instance_id.partition("__")
        repo = rest.split("-")[0] if "-" in rest else rest
        key = f"{owner}/{repo}"
        if key in table:
            return table[key]
    return _DEFAULT_TIMEOUT_SECONDS


class HarnessOutcome(Struct, frozen=True):
    """One grader call's typed outcome (design v3 §"The grader contract"). `verdict` is one
    of `PASS | FAIL | NO_VERDICT`; on `NO_VERDICT`, `reason` names WHY out of the closed
    `_HARNESS_REASONS` set. On `PASS` or `FAIL`, `reason` is the empty string. `detail`
    carries a short human-readable note (exit code + last stderr chunk on
    `container_crashed`; exception class on `harness_error`)."""

    verdict: Verdict
    reason: str = ""
    detail: str = ""


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
        # unittest/django parenthesised form: "test_func (module.path[.Class[.method]])". The
        # unittest loader resolves this by importing `module.path` and walking attributes. The
        # FILE is `module/path.py` at some sys.path prefix. Match rule (F7-round-2, 2026-08-09):
        # tp_file matches iff it EQUALS the derived path OR ends with `"/" + derived` (`/` forces
        # a segment boundary so `myapp/tests.py` cannot match `some_myapp/tests.py`).
        #
        # Trailing segments: the parenthesised group can end in a Class, or Class.method
        # (Django's newer test-id form appends the method name to the parens too). Python
        # convention — Classes are PascalCase, modules and methods are snake_case. Peel off:
        #   * last segment IF PascalCase (class-drop): `module.path.py`
        #   * last two segments IF second-to-last is PascalCase (class-plus-method drop)
        #   * always try full-module (`module.path.class.method.py`) as fallback
        # Any candidate matching in tp_files admits the id.
        m = re.search(r"\(([\w.]+)\)", test_id)
        if m:
            parts = m.group(1).split(".")
            candidates: list[str] = []
            # New-Django form: `module.Class.snake_method` — drop the last two.
            if len(parts) >= 3 and parts[-2][:1].isupper() and not parts[-1][:1].isupper():
                candidates.append("/".join(parts[:-2]) + ".py")
            # Legacy form: `module.Class` — drop the class.
            if len(parts) >= 2 and parts[-1][:1].isupper():
                candidates.append("/".join(parts[:-1]) + ".py")
            # Full-module — last segment IS a module (rare but legal, e.g. `some_module`).
            candidates.append("/".join(parts) + ".py")

            for derived in candidates:
                for f in tp_files:
                    if f == derived or f.endswith("/" + derived):
                        return True

        # Docstring form (no parens at all) — Django's SimpleTestCase repr uses the docstring's
        # first line as the id. Cannot derive a file. Fall back to CONTENT match against
        # test_patch: if the id string appears in an ADDED line (starts with `+` in the diff),
        # the test IS being added by test_patch. Coarser than the structural match; only used
        # when structural resolution fails. The lookup is against the raw test_patch text,
        # which the outer scope has as `str(instance.get("test_patch", ""))`.
        tp_text = str(instance.get("test_patch", ""))
        # Truncated docstrings still work — even a 40-char prefix in an added line is a strong
        # match. Django's SWE-bench ids tend to run 40-80 chars.
        needle = test_id.strip()
        if len(needle) < 12:
            # Very short strings (a single word or two) would match too many `+` lines. Fail
            # closed rather than fabricate a match on `def` or a variable name.
            return False
        for line in tp_text.splitlines():
            if line.startswith("+") and not line.startswith("+++") and needle in line:
                return True
        return False

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


def _container_name(instance_id: str, run_id: str) -> str:
    """The container name the swebench harness pins for one instance/run pair
    (`test_spec.get_instance_container_name`, harness 4.x). Named here so `docker kill`
    can target it under `subprocess.TimeoutExpired` — the invariant lives in a named
    function, not a scattered f-string."""
    return f"sweb.eval.{instance_id.lower()}.{run_id}"


def _docker_kill(container_name: str) -> None:
    """Best-effort `docker kill <name>`. Never raises — the caller has already timed out
    and just needs the container gone. Absent daemon, missing container, permission errors
    all fall through silently (the no-orphan-container invariant is enforced by the caller
    that also calls `docker rm` cleanup if the harness leaves one behind)."""
    try:
        subprocess.run(
            ["docker", "kill", container_name],
            timeout=30,
            capture_output=True,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass


def run_swebench_one(
    instance_id: str,
    model_patch: str,
    *,
    dataset_name: str,
    model_name: str,
    run_id: str,
    report_dir: Path | str,
    timeout_seconds: int,
    split: str = "test",
    namespace: str = "swebench",
) -> HarnessOutcome:
    """ENV-GATED (Docker). Grade ONE instance in ONE container with a hard wall-clock.

    Owns the entire lifecycle for one grade call: writes the one-row predictions file,
    fires the harness in a subprocess (so `subprocess.run(timeout=T)` can enforce the
    deadline — an in-process `run_evaluation.main` call cannot be interrupted from a
    thread), kills the container by its deterministic name on timeout, parses the report
    on completion. Returns a typed `HarnessOutcome` — every one of the four failure modes
    from the design's verdict-mapping table lands on a distinct `reason` string from the
    shared `_HARNESS_REASONS` closed set.

    Container name is `sweb.eval.{instance_id}.{run_id}` (the harness's own naming rule);
    on `subprocess.TimeoutExpired`, `docker kill` targets that name so no orphan container
    survives the call (design v3 §"No orphaned containers")."""
    verify_constants()
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    if not model_patch.strip():
        # Consistent with the sync oracle: an empty patch is a definite FAIL, no harness
        # call needed. The oracle already returns FAIL for this shape; the grader is
        # defensive so a direct caller can't get a NO_VERDICT for an empty patch.
        return HarnessOutcome(verdict=Verdict.FAIL, reason="", detail="empty patch")

    pred = make_prediction(instance_id, model_patch, model_name=model_name)
    preds_path = write_predictions([pred], report_dir / f"preds_{run_id}.jsonl")
    container = _container_name(instance_id, run_id)

    cmd = [
        sys.executable,
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        dataset_name,
        "--split",
        split,
        "--instance_ids",
        instance_id,
        "--predictions_path",
        str(preds_path),
        "--max_workers",
        "1",
        "--run_id",
        run_id,
        "--timeout",
        str(timeout_seconds),
        "--namespace",
        namespace,
        "--report_dir",
        str(report_dir),
        "--cache_level",
        "env",
    ]
    try:
        proc = subprocess.run(
            cmd,
            timeout=timeout_seconds + 60,  # 60s margin over the harness's own timeout
            capture_output=True,
            text=True,
            check=False,
        )
    except subprocess.TimeoutExpired:
        _docker_kill(container)
        return HarnessOutcome(
            verdict=Verdict.NO_VERDICT,
            reason=REASON_TIMED_OUT,
            detail=f"wall-clock exceeded {timeout_seconds}s for {instance_id}",
        )
    except FileNotFoundError as e:
        return HarnessOutcome(
            verdict=Verdict.NO_VERDICT,
            reason=REASON_HARNESS_ERROR,
            detail=f"{type(e).__name__}: {e}",
        )

    # The harness always writes a report if the container ran to completion. Missing
    # report + non-zero exit => container_crashed; missing report + zero exit =>
    # harness_error (unusual but possible if the report writer itself died).
    try:
        resolved = read_resolved(report_dir, run_id, model_name, instance_id)
    except FileNotFoundError:
        if proc.returncode != 0:
            tail = (proc.stderr or "")[-400:]
            return HarnessOutcome(
                verdict=Verdict.NO_VERDICT,
                reason=REASON_CONTAINER_CRASHED,
                detail=f"exit={proc.returncode} stderr_tail={tail!r}",
            )
        return HarnessOutcome(
            verdict=Verdict.NO_VERDICT,
            reason=REASON_HARNESS_ERROR,
            detail=f"exit=0 but no report.json for {instance_id}",
        )
    return HarnessOutcome(
        verdict=Verdict.PASS if resolved else Verdict.FAIL,
        reason="",
        detail=f"resolved={resolved} for {instance_id}",
    )


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


def suspect_files_from_record(record: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """The LAST SuspectFiles event's file list on the record — the suspect set the localizer
    landed on for this instance. Empty tuple if no SuspectFiles event fired (a coding record,
    a topology that skipped localization, or a run whose localizer died before emitting)."""
    suspects = [e["payload"] for e in record if e.get("kind") == "SuspectFiles"]
    if not suspects:
        return ()
    return tuple(suspects[-1].get("files", ()))


def _recall_metrics(
    suspect_files: Sequence[str], gold_patch: str
) -> tuple[float | None, bool | None]:
    """Compute (recall_at_k, full_recall_at_k) from the suspect set + the gold patch's touched
    files. F2 fix (review 2026-08-08). Returns (None, None) when there's no gold patch on the
    instance (a synthetic case with no ground-truth fix) so a coding assay's oracle doesn't
    fabricate a localization signal from nothing."""
    gold = {
        ln[6:] for ln in gold_patch.splitlines() if ln.startswith("+++ b/") and ln[6:] != "dev/null"
    }
    if not gold:
        return (None, None)
    suspect_set = set(suspect_files)
    hits = len(gold & suspect_set)
    return (hits / len(gold), gold.issubset(suspect_set))


class SwebenchRecordOracle:
    """The SWE-bench Oracle — constructs Result directly (F2 fix, review 2026-08-08) rather than
    routing through `ExternalGraderOracle`'s lambda wrapper, so the extra typed fields
    (`grader_error_band`, `recall_at_k`, `full_recall_at_k`) ride on every graded Result. Reads
    `SelectedPatch.model_patch` and `SuspectFiles.files` off the record, and `ground_truth`
    (the instance dict) for the gold patch. Grades via the official Docker harness. `run-and-
    observe` (replayable=False) — the verdict is captured once per run.

    Satisfies the Oracle protocol; `run_arm_on_case` (assay/run.py:77) calls `.grade(record,
    ground_truth) -> Result`."""

    def __init__(
        self,
        *,
        report_root: Path | str,
        dataset_name: str,
        model_name: str = DEFAULT_MODEL_NAME,
        grade: Callable[[str, str], bool | HarnessOutcome] | None = None,
        grader_error_band: float | None = _LITE_GRADER_ERROR_BAND,
        namespace: str = "swebench",
    ) -> None:
        self._report_root = report_root
        self._dataset_name = dataset_name
        self._model_name = model_name
        self._grade_override = grade
        self._grader_error_band = grader_error_band
        self._namespace = namespace

    def _default_grade(self, instance_id: str, model_patch: str) -> HarnessOutcome:
        # H-3 (ratified 2026-08-10): route the real grade through `run_swebench_one` so the
        # grader owns container lifecycle + wall-clock, and the NO_VERDICT states carry
        # typed reason strings from the closed `_HARNESS_REASONS` set.
        h = hashlib.sha1(f"{self._model_name}:{model_patch}".encode()).hexdigest()[:10]
        run_id = f"assay-{instance_id}-{h}"
        return run_swebench_one(
            instance_id,
            model_patch,
            dataset_name=self._dataset_name,
            model_name=self._model_name,
            run_id=run_id,
            report_dir=Path(self._report_root) / instance_id,
            timeout_seconds=timeout_for_instance(instance_id),
            namespace=self._namespace,
        )

    def grade(self, record: Any, ground_truth: Any) -> Result:
        events = list(record) if not isinstance(record, list) else record
        instance_id = (
            str(ground_truth["instance_id"])
            if isinstance(ground_truth, Mapping)
            else str(ground_truth)
        )
        # F2 fix: compute recall metrics unconditionally — a graded Result carries them even when
        # the model_patch is empty (localization can be right while repair fails), so the writeup
        # can attribute the ceiling correctly.
        suspects = suspect_files_from_record(events)
        gold_patch = str(ground_truth.get("patch", "")) if isinstance(ground_truth, Mapping) else ""
        recall, full_recall = _recall_metrics(suspects, gold_patch)

        patch = model_patch_from_record(events)
        if not patch.strip():
            # No patch on the record means the topology produced none — a definite FAIL,
            # not a NO_VERDICT. The harness never ran because there was nothing to grade.
            return Result(
                verdict=Verdict.FAIL,
                score=0.0,
                metric="resolved",
                oracle_class=EXTERNAL_GRADER,
                replayable=False,
                detail=f"no model_patch on the record for {instance_id} (the Arm produced none)",
                grader_error_band=self._grader_error_band,
                recall_at_k=recall,
                full_recall_at_k=full_recall,
            )
        # drop edits to the GRADE's test files at the grade boundary (#72 NET 1): the inflation
        # guard, applied HERE so a topology that emits a raw diff (no internal drop, e.g. the
        # repair topology) can't weaken a graded test or collide with the held-out test_patch.
        # Harness-side — the topology never sees test_patch.
        if isinstance(ground_truth, Mapping) and ground_truth.get("test_patch"):
            from .swebench_workspace import filter_diff, graded_test_files

            patch = filter_diff(
                patch, drop_files=frozenset(graded_test_files(str(ground_truth["test_patch"])))
            )
            if not patch.strip():
                # After the graded-test-file drop the patch is empty — same FAIL semantics
                # as "no model_patch on the record" (nothing to grade).
                return Result(
                    verdict=Verdict.FAIL,
                    score=0.0,
                    metric="resolved",
                    oracle_class=EXTERNAL_GRADER,
                    replayable=False,
                    detail=f"patch empty after dropping graded-test edits for {instance_id}",
                    grader_error_band=self._grader_error_band,
                    recall_at_k=recall,
                    full_recall_at_k=full_recall,
                )
        if self._grade_override is not None:
            raw = self._grade_override(instance_id, patch)
            outcome = (
                raw
                if isinstance(raw, HarnessOutcome)
                else HarnessOutcome(
                    verdict=Verdict.PASS if raw else Verdict.FAIL,
                    reason="",
                    detail=f"override resolved={raw}",
                )
            )
        else:
            outcome = self._default_grade(instance_id, patch)
        return Result(
            verdict=outcome.verdict,
            score=1.0 if outcome.verdict is Verdict.PASS else 0.0,
            metric="resolved",
            oracle_class=EXTERNAL_GRADER,
            replayable=False,
            detail=f"{outcome.detail} ({len(patch)}b patch)",
            reason=outcome.reason,
            grader_error_band=self._grader_error_band,
            recall_at_k=recall,
            full_recall_at_k=full_recall,
        )


def swebench_record_oracle(
    *,
    report_root: Path | str,
    dataset_name: str,
    model_name: str = DEFAULT_MODEL_NAME,
    grade: Callable[[str, str], bool | HarnessOutcome] | None = None,
    grader_error_band: float | None = _LITE_GRADER_ERROR_BAND,
) -> SwebenchRecordOracle:
    """Legacy factory kept for backward compat. Returns a `SwebenchRecordOracle` (F2 fix, review
    2026-08-08) — the pre-fix return was `ExternalGraderOracle` wrapping a lambda that could not
    thread `recall_at_k`, `full_recall_at_k`, or `grader_error_band` through the fixed-shape
    grader signature. Same call sites, same grade behaviour, richer Result."""
    return SwebenchRecordOracle(
        report_root=report_root,
        dataset_name=dataset_name,
        model_name=model_name,
        grade=grade,
        grader_error_band=grader_error_band,
    )


# 2026-08-09 batch-grade path (review item 1). Pre-fix, every cell called `run_swebench` inline
# → one fresh `run_evaluation` subprocess per cell → 1500 harness starts on pass 1 for zero
# parallelism (`max_workers=1`). The swebench harness natively accepts a batch predictions file
# and parallelises via `max_workers=N`. Deferring the grade to end-of-sweep and firing ONE
# `run_swebench` per arm cuts grade wall from ~37h (1500 × 90s serial) to ~1-2h.
#
# The oracle is split into TWO phases:
#   Phase 1 (during the sweep): `SwebenchExtractOnlyOracle.grade()` extracts the patch off the
#     record and returns a placeholder Result (passed=False, detail="deferred: patch=<len>"). No
#     docker.
#   Phase 2 (after the sweep): `batch_grade_from_records(records_dir, instances, ...)` walks
#     every record, builds a batch predictions file, calls `run_swebench` ONCE with
#     `max_workers=N`, reads the per-instance reports, returns {instance_id -> resolved: bool}.
#     The confirmatory runner then rewrites cells.jsonl replacing every deferred row's
#     `passed` and `detail` fields with the real grade.
class SwebenchExtractOnlyOracle:
    """Deferred-grade sibling of `SwebenchRecordOracle` for the batch path. `.grade()` extracts
    the patch off the record and returns a placeholder with `detail="deferred: patch=<len>"`.
    Docker never fires here. The runner reconstitutes the real grade via
    `batch_grade_from_records` after the sweep."""

    def __init__(
        self,
        *,
        grader_error_band: float | None = _LITE_GRADER_ERROR_BAND,
    ) -> None:
        self._grader_error_band = grader_error_band

    def grade(self, record: Any, ground_truth: Any) -> Result:
        events = list(record) if not isinstance(record, list) else record
        instance_id = (
            str(ground_truth["instance_id"])
            if isinstance(ground_truth, Mapping)
            else str(ground_truth)
        )
        suspects = suspect_files_from_record(events)
        gold_patch = str(ground_truth.get("patch", "")) if isinstance(ground_truth, Mapping) else ""
        recall, full_recall = _recall_metrics(suspects, gold_patch)

        patch = model_patch_from_record(events)
        if not patch.strip():
            # No patch on the record — definite FAIL, not NO_VERDICT (the harness never had
            # anything to grade).
            return Result(
                verdict=Verdict.FAIL,
                score=0.0,
                metric="resolved",
                oracle_class=EXTERNAL_GRADER,
                replayable=False,
                detail=f"no model_patch on the record for {instance_id} (the Arm produced none)",
                grader_error_band=self._grader_error_band,
                recall_at_k=recall,
                full_recall_at_k=full_recall,
            )
        # graded-test-file filter still applies at extract time so the batch grader sees the
        # clean patch (same #72 NET 1 discipline as `SwebenchRecordOracle.grade`).
        if isinstance(ground_truth, Mapping) and ground_truth.get("test_patch"):
            from .swebench_workspace import filter_diff, graded_test_files

            patch = filter_diff(
                patch, drop_files=frozenset(graded_test_files(str(ground_truth["test_patch"])))
            )
            if not patch.strip():
                return Result(
                    verdict=Verdict.FAIL,
                    score=0.0,
                    metric="resolved",
                    oracle_class=EXTERNAL_GRADER,
                    replayable=False,
                    detail=f"patch empty after dropping graded-test edits for {instance_id}",
                    grader_error_band=self._grader_error_band,
                    recall_at_k=recall,
                    full_recall_at_k=full_recall,
                )
        # Deferred placeholder — the runner batch-grades after the sweep. NO_VERDICT is the
        # honest interim state; the batch grade overwrites it with the real verdict when the
        # harness reports back. Reason `harness_error` names the deferred state honestly at
        # the closed-set boundary (the batch overwrite replaces it with empty on pass/fail).
        return Result(
            verdict=Verdict.NO_VERDICT,
            score=0.0,
            metric="resolved",
            oracle_class=EXTERNAL_GRADER,
            replayable=False,
            reason=REASON_HARNESS_ERROR,
            detail=f"deferred: patch={len(patch)}b for {instance_id}",
            grader_error_band=self._grader_error_band,
            recall_at_k=recall,
            full_recall_at_k=full_recall,
        )


def batch_grade_from_records(
    records_dir: Path | str,
    instances_by_case_id: Mapping[str, Mapping[str, Any]],
    *,
    report_dir: Path | str,
    dataset_name: str,
    model_name: str = DEFAULT_MODEL_NAME,
    run_id: str,
    max_workers: int = 8,
    namespace: str = "swebench",
    timeout: int = 1800,
) -> dict[str, bool]:
    """ENV-GATED (Docker). Batch grade every cell's patch in ONE `run_swebench` call. Walks
    `records_dir/<arm>__<case>__t<trial>/`, extracts each cell's `SelectedPatch.model_patch`,
    drops graded-test edits per `test_patch`, builds one predictions file keyed by a synthetic
    per-cell instance_id (see below), fires the harness with `max_workers`, reads back the
    per-cell `resolved` bool.

    KEY: the harness keys reports by `instance_id`. Multiple cells for the same instance_id
    (trials + arms) would collide. We disambiguate via the swebench `model_name_or_path` field —
    each cell gets a unique `model_name_or_path = f"{model_name}--{cell_dir_name}"`, and the
    report dir is per-cell too. That way reports don't stomp.

    Returns `{cell_dir_name -> resolved}` for every cell that produced a non-empty patch.
    Cells with no patch aren't invoked (the placeholder Result from
    SwebenchExtractOnlyOracle already carries `passed=False` for those).
    """
    from ..api import read_record

    records_dir = Path(records_dir)
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    predictions: list[Mapping[str, str]] = []
    cell_to_instance: dict[str, str] = {}
    for cell_dir in sorted(records_dir.iterdir()):
        if not cell_dir.is_dir() or "__" not in cell_dir.name:
            continue
        # cell_dir.name = "{arm}__{case_id}__t{trial}"; case_id has "_1776_" in place of "__"
        parts = cell_dir.name.split("__")
        if len(parts) < 3:
            continue
        case_id = parts[1]
        instance_meta = instances_by_case_id.get(case_id)
        if not instance_meta:
            continue
        instance_id = str(instance_meta.get("instance_id", ""))
        if not instance_id:
            continue
        try:
            events = list(read_record(cell_dir))
        except Exception:
            continue
        patch = model_patch_from_record(events)
        if not patch.strip():
            continue
        # graded-test-file filter (same discipline as the sync oracle).
        tp = instance_meta.get("test_patch", "")
        if tp:
            from .swebench_workspace import filter_diff, graded_test_files

            patch = filter_diff(patch, drop_files=frozenset(graded_test_files(str(tp))))
            if not patch.strip():
                continue
        # per-cell model_name_or_path disambiguates same-instance trial + arm collisions in the
        # harness report layout.
        cell_model = f"{model_name}--{cell_dir.name}"
        predictions.append(
            {
                KEY_INSTANCE_ID: instance_id,
                KEY_MODEL: cell_model,
                KEY_PREDICTION: patch,
            }
        )
        cell_to_instance[cell_dir.name] = instance_id

    if not predictions:
        return {}

    verify_constants()
    preds_path = write_predictions(predictions, report_dir / f"preds_{run_id}.jsonl")

    from swebench.harness import run_evaluation  # lazy, env-gated

    run_evaluation.main(
        dataset_name=dataset_name,
        split="test",
        instance_ids=sorted({p[KEY_INSTANCE_ID] for p in predictions}),
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
        report_dir=str(report_dir),
    )

    # Read per-cell resolved from the harness reports. The harness writes one report.json per
    # `{model}/{instance_id}/report.json` — the per-cell model_name in each prediction row is
    # what disambiguates trials + arms of the same instance_id.
    out: dict[str, bool] = {}
    for cell_name, instance_id in cell_to_instance.items():
        cell_model = f"{model_name}--{cell_name}"
        try:
            resolved = read_resolved(report_dir, run_id, cell_model, instance_id)
        except FileNotFoundError:
            resolved = False
        out[cell_name] = resolved
    return out


__all__ = [
    "KEY_INSTANCE_ID",
    "KEY_MODEL",
    "KEY_PREDICTION",
    "DEFAULT_MODEL_NAME",
    "FirewallViolation",
    "HarnessOutcome",
    "REASON_CONTAINER_CRASHED",
    "REASON_DOCKER_ERROR",
    "REASON_FIREWALL_VIOLATION",
    "REASON_GIT_ERROR",
    "REASON_HARNESS_ERROR",
    "REASON_RATE_LIMITED",
    "REASON_TIMED_OUT",
    "SwebenchRecordOracle",
    "SwebenchExtractOnlyOracle",
    "batch_grade_from_records",
    "firewall_check",
    "make_prediction",
    "write_predictions",
    "read_resolved",
    "read_run_report",
    "read_swebench_timeouts",
    "timeout_for_instance",
    "verify_constants",
    "run_swebench",
    "run_swebench_one",
    "swebench_oracle",
    "model_patch_from_record",
    "suspect_files_from_record",
    "grade_patch",
    "swebench_record_oracle",
]

# re-exported for callers that grade via the Oracle directly
_ = (EXTERNAL_GRADER, Result)
