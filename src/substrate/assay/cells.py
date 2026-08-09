"""A cells JSONL (+ its `.meta.json`) -> an assay Report — the canonical "read a finished assay run"
seam, so the CLI (`scripts/bench_coding.py report`) and the substrate-ui server share ONE
implementation and the arm matrix can't drift between them.

Reconstructs CaseResults from the incrementally-written rows (null compute -> 0; a salvage/fail cell
legitimately made no calls) and the Suite from the meta sidecar + the pre-registered coding bank, then
runs the same `build_report`. Coding-assay-specific for now (it knows the coding bank); other assay
types reconstruct their own suite when they exist."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .coding import coding_suite
from .coding_problems import coding_problem_bank
from .oracle import EXTERNAL_GRADER, LogProjectionOracle, Result
from .report import Report, build_report
from .run import CaseResult, UsageTotals
from .suite import Arm, Case, Suite, Topology

CODING_ASSAY_KIND = "coding"
SWEBENCH_ASSAY_KIND = "swebench"


def read_meta(cells_path: Path) -> dict[str, Any]:
    """The provenance sidecar (config fingerprint, models, margin, pass_k, trials) — `{}` for a
    pre-provenance run; the report still reconstructs from defaults (arm structure is in the rows)."""
    meta = cells_path.with_suffix(".meta.json")
    return json.loads(meta.read_text()) if meta.exists() else {}


def read_rows(cells_path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in cells_path.read_text().splitlines() if line.strip()]


def caseresult_from_row(r: dict[str, Any]) -> CaseResult:
    """One JSONL row -> a CaseResult. Null compute (salvage/fail cells — no calls MADE) coerces to 0
    for the totals; the report's compute axis then reflects only what was measured. `reproduction`
    (sprint 158) reads the optional column added by the confirmatory runner — empty for coding
    rows and for SWE-bench rows that emitted no SelectedPatch / TestResults."""
    p = bool(r["passed"])
    # F2 fix (review 2026-08-08): read recall fields off the row when present so a report rebuilt
    # from cells.jsonl carries the localization diagnostics. `None` when the column is missing
    # (pre-F2 cells) or explicitly null (a coding row or a SWE-bench row without SuspectFiles).
    recall = r.get("recall_at_k")
    recall = float(recall) if recall is not None else None
    full_recall = r.get("full_recall_at_k")
    full_recall = bool(full_recall) if full_recall is not None else None
    return CaseResult(
        arm=str(r["arm"]),
        role=str(r["role"]),
        case_id=str(r["case_id"]),
        trial=int(r["trial"]),
        result=Result(
            passed=p,
            score=1.0 if p else 0.0,
            metric="resolved-held-out",
            oracle_class=EXTERNAL_GRADER,
            replayable=False,
            detail=str(r.get("source", "")),
            recall_at_k=recall,
            full_recall_at_k=full_recall,
        ),
        usage=UsageTotals(
            prompt_tokens=int(r.get("prompt_tokens") or 0),
            completion_tokens=int(r.get("completion_tokens") or 0),
            inference_ms=int(r.get("inference_ms") or 0),
            model_calls=int(r.get("model_calls") or 0),
            estimated=bool(r.get("estimated", False)),
        ),
        elapsed_ms=int(r.get("elapsed_ms") or 0),
        root=str(r.get("root", "")),
        reproduction=str(r.get("reproduction", "") or ""),
    )


def read_cases_sidecar(cells_path: Path) -> list[dict[str, Any]]:
    """The `.cases.json` sidecar the SWE-bench confirmatory runner writes alongside the JSONL
    (sprint 144a gap #7 at scripts/assay_swebench_confirmatory.py:177). One entry per prepared Case,
    carrying `case_id`, `instance_id`, `repo`, `base_commit`, `image`, `regression_files`, `exclude`,
    `passed_at_base`. Missing sidecar returns `[]` — `suite_from_meta` then reconstructs the case
    set from the observed cell rows, which is enough for the paired-comparison report even without
    the runner primitives (those are needed only for a re-run, not for scoring)."""
    sidecar = cells_path.with_suffix(".cases.json")
    if not sidecar.exists():
        return []
    data = json.loads(sidecar.read_text())
    if not isinstance(data, list):
        raise ValueError(
            f"{sidecar} malformed: expected a JSON array of case descriptors, got {type(data).__name__}"
        )
    return data


def _stub_arm_build(_case: Case) -> Topology:
    """A cells-reconstructed Suite is for REPORTING only — `build_report` never calls `Arm.build`
    (it walks results). This stub trips a runtime error if a caller accidentally treats a
    reconstructed Suite as runnable, so the write-side and read-side of the assay layer don't share
    an accidental door."""
    raise RuntimeError(
        "this Suite was reconstructed from cells.jsonl for reporting; its arms are not runnable"
    )


def _stub_oracle() -> LogProjectionOracle:
    """Report-only oracle placeholder — `build_report` reads the recorded `CaseResult` grades, not
    the Suite's oracle. Constructing a real ExternalGraderOracle here would require a live report_dir
    and a dataset_name pointing at the harness, which the report path has no business needing."""
    return LogProjectionOracle(extract=lambda _record: None)


def _suite_from_meta_coding(meta: dict[str, Any]) -> Suite:
    """The pre-sprint-152 shape kept intact for `assay_kind == "coding"` (the default). Model names
    are labels; the arm STRUCTURE (strong control + the ablation ladder) is what `build_report`
    pairs on."""
    problems = coding_problem_bank()
    n = int(meta.get("n_problems", len(problems)))
    return coding_suite(
        problems[:n],
        strong_model=str(meta.get("strong_model", "strong")),
        weak_models=list(meta.get("weak_models", ["weak"])),
        equivalence_margin=float(meta.get("margin", 0.1)),
        pass_k=int(meta.get("pass_k", 1)),
    )


def _suite_from_meta_swebench(
    meta: dict[str, Any],
    rows: list[dict[str, Any]],
    cases_sidecar: list[dict[str, Any]],
) -> Suite:
    """Reconstruct a SWE-bench Suite for report generation.

    The confirmatory runner (`scripts/assay_swebench_confirmatory.py`, sprint 144a) writes three
    files per sweep: `<name>.jsonl` (one row per (arm, case, trial) cell), `<name>.meta.json`
    (config + fingerprint + arm/margin/pass_k), and `<name>.cases.json` (the per-case sidecar for
    reconstruction without re-cloning). This branch reads the last two — the arm structure comes
    from the observed cell rows (so a mid-flight resume grades whatever actually ran, not what
    meta was configured to run), and the case set comes from the sidecar; a missing sidecar falls
    back to the case_ids observed in the rows, which is sufficient for the paired McNemar / bootstrap
    but drops the instance-level metadata a substrate-ui pane would render.

    The oracle is a stub. `build_report` (assay/report.py:152-297) never calls `oracle.grade` — it
    walks the `CaseResult` list which already carries the recorded grade. Constructing a real
    `swebench_record_oracle` here would need a live Docker report directory and a dataset name that
    the READ path has no business owning; the write path (the confirmatory runner) is where the
    oracle actually lives.
    """
    control_arm = str(meta.get("control_arm") or meta.get("arm_name") or "swebench_solver")

    observed_arms: dict[str, str] = {}
    for row in rows:
        name = str(row.get("arm", ""))
        if name and name not in observed_arms:
            observed_arms[name] = str(row.get("role", "full"))
    if control_arm not in observed_arms:
        observed_arms[control_arm] = str(meta.get("role", "full"))

    if cases_sidecar:
        cases: tuple[Case, ...] = tuple(
            Case(
                case_id=str(entry["case_id"]),
                payload={},
                ground_truth={"instance_id": str(entry.get("instance_id", entry["case_id"]))},
            )
            for entry in cases_sidecar
        )
    else:
        seen: dict[str, None] = {}
        for row in rows:
            cid = str(row.get("case_id", ""))
            if cid and cid not in seen:
                seen[cid] = None
        cases = tuple(
            Case(case_id=cid, payload={}, ground_truth={"instance_id": cid}) for cid in seen
        )
    if not cases:
        raise ValueError(
            "cannot reconstruct a SWE-bench Suite: neither .cases.json nor rows carry any case_id"
        )

    arms = tuple(Arm(name=n, role=r, build=_stub_arm_build) for n, r in observed_arms.items())
    return Suite(
        name=str(meta.get("name", "swebench")),
        version=str(meta.get("version", "0.1")),
        cases=cases,
        arms=arms,
        oracle=_stub_oracle(),
        control_arm=control_arm,
        primary_metric=str(meta.get("primary_metric", "resolved")),
        null_rule=str(
            meta.get(
                "null_rule",
                "reconstructed from cells; the original run's null_rule is authoritative",
            )
        ),
        equivalence_margin=float(meta.get("margin", 0.1)),
        pass_k=int(meta.get("pass_k", 1)),
    )


def suite_from_meta(
    meta: dict[str, Any],
    *,
    rows: list[dict[str, Any]] | None = None,
    cases_sidecar: list[dict[str, Any]] | None = None,
) -> Suite:
    """Dispatch on `meta.get("assay_kind")` (sprint 152). The default is `"coding"` so
    pre-152 cells files (which never wrote the key) read the same way they always did. The
    `"swebench"` branch reconstructs from the `.cases.json` sidecar the confirmatory runner writes
    (sprint 144a gap #7); rows are used to recover the observed arm structure so a report grades
    whatever actually ran, not what meta was configured to run.

    A new `assay_kind` value raises rather than silently coding-parsing SWE-bench data. That's the
    signal-not-guess posture — an unknown assay kind is a versioning event, not a fallback."""
    kind = str(meta.get("assay_kind", CODING_ASSAY_KIND))
    if kind == CODING_ASSAY_KIND:
        return _suite_from_meta_coding(meta)
    if kind == SWEBENCH_ASSAY_KIND:
        return _suite_from_meta_swebench(meta, rows or [], cases_sidecar or [])
    raise ValueError(
        f"unknown assay_kind {kind!r} in meta.json — supported: "
        f"{sorted((CODING_ASSAY_KIND, SWEBENCH_ASSAY_KIND))!r}. Add a branch to suite_from_meta."
    )


def provenance_status(meta: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    """Is the recorded config trustworthy — or was the (editable) meta sidecar tampered post-hoc to
    manufacture a verdict (the cargo-cult via a loosened margin)?

      - verified: the meta's config_fp matches BOTH a recompute of its own config fields (so the margin/
        models were not edited) AND the fingerprint stamped on the cells at run time (the tamper-evident
        anchor in the append-only cell log).
      - tampered: a config_fp is present but does NOT match the recompute or the cells — the sidecar was
        changed after the run.
      - unverified: no fingerprint to check (a pre-provenance run); the verdict stands but is unanchored."""
    stored = meta.get("config_fp")
    cell_fps = {str(r.get("config_fp")) for r in rows if r.get("config_fp")}
    if not stored and not cell_fps:
        return "unverified"
    config = {k: v for k, v in meta.items() if k not in ("config_fp", "run_id", "_provenance")}
    recomputed = (
        hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12]
        if config
        else None
    )
    if stored and recomputed is not None and stored != recomputed:
        return "tampered"  # the meta's margin/models were edited but its fingerprint was not
    if stored and cell_fps and cell_fps != {str(stored)}:
        return "tampered"  # the meta disagrees with the per-cell stamps
    if stored and recomputed == stored:
        return "verified"
    return "unverified"


def report_from_cells(cells_path: Path) -> tuple[Report, dict[str, Any]]:
    """The whole read: rows + meta -> (Report, meta). The Report carries both currencies, the harsher
    delta_vs_control + McNemar, the pass@1 bootstrap + margin-verdict + FDR. `meta['_provenance']`
    flags whether the recorded config (the margin the verdict binds to) is verified / tampered /
    unverified — so a post-hoc-edited margin cannot silently drive a confirmatory verdict."""
    meta = read_meta(cells_path)
    rows = read_rows(cells_path)
    cases_sidecar = read_cases_sidecar(cells_path)
    meta["_provenance"] = provenance_status(meta, rows)
    results = [caseresult_from_row(r) for r in rows]
    return build_report(
        suite_from_meta(meta, rows=rows, cases_sidecar=cases_sidecar), results
    ), meta
