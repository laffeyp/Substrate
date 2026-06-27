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
from .oracle import EXTERNAL_GRADER, Result
from .report import Report, build_report
from .run import CaseResult, UsageTotals
from .suite import Suite


def read_meta(cells_path: Path) -> dict[str, Any]:
    """The provenance sidecar (config fingerprint, models, margin, pass_k, trials) — `{}` for a
    pre-provenance run; the report still reconstructs from defaults (arm structure is in the rows)."""
    meta = cells_path.with_suffix(".meta.json")
    return json.loads(meta.read_text()) if meta.exists() else {}


def read_rows(cells_path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in cells_path.read_text().splitlines() if line.strip()]


def caseresult_from_row(r: dict[str, Any]) -> CaseResult:
    """One JSONL row -> a CaseResult. Null compute (salvage/fail cells — no calls MADE) coerces to 0
    for the totals; the report's compute axis then reflects only what was measured."""
    p = bool(r["passed"])
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
    )


def suite_from_meta(meta: dict[str, Any]) -> Suite:
    """Rebuild the same Suite the run used (arms / control / margin / pass_k) — model names are labels;
    the arm STRUCTURE (strong_ref control + the ablation ladder) is what build_report pairs on."""
    problems = coding_problem_bank()
    n = int(meta.get("n_problems", len(problems)))
    return coding_suite(
        problems[:n],
        strong_model=str(meta.get("strong_model", "strong")),
        weak_models=list(meta.get("weak_models", ["weak"])),
        equivalence_margin=float(meta.get("margin", 0.1)),
        pass_k=int(meta.get("pass_k", 1)),
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
        hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12] if config else None
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
    meta["_provenance"] = provenance_status(meta, rows)
    results = [caseresult_from_row(r) for r in rows]
    return build_report(suite_from_meta(meta), results), meta
