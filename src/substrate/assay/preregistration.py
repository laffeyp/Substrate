# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Pre-registration gate for confirmatory assay runs — sprint 151.

A confirmatory run is a bet with pre-declared stakes. `docs/benchmarking/benchmarking-preregistration-template.md`
(18 sections) states the discipline: copy the template, fill every field, commit the file
BEFORE the first arm executes, and never edit it in place. `provenance_status` at
`assay/cells.py:79-105` verifies AFTER the fact that the meta sidecar wasn't tampered; this
module refuses to WRITE cells unless a matching pre-registration is on disk and the arms the
runner is about to build match the arms the pre-reg declared.

The gate has three checks. Any failure raises `PreregistrationViolation` and the runner exits
before touching disk:

  1. **Presence.** `.preg.json` exists at the declared path and parses as JSON.
  2. **Arms match.** The pre-reg's `arms_hash` equals `arms_fingerprint(arms)` computed over the
     arm structure the runner just built. A rename or a reroll (adding N=5 where the pre-reg said
     N=3) fails here.
  3. **Comparator.** The pre-reg carries a non-empty `comparator: {source, split, model, resolve_rate}`
     block. A confirmatory number without a public anchor is unreadable (per Kapoor & Narayanan
     2024's "AI Agents That Matter"); the roadmap round-3 fold made this a hard requirement.

Timestamp verification (pre-reg commit hash strictly before first cell write) is out of scope for
this module — it requires shelling to git and a live commit; the confirmatory runner does that at
its own boundary. This module owns the file+arms+comparator half.

`arms_fingerprint` consolidates with `_fingerprint(cfg)` in `scripts/bench_coding.py:87` and
`scripts/assay_swebench_confirmatory.py:128` — same sha256(canonical-json)[:12] pipeline, one
authoritative helper so pre-reg validation and cell-provenance hash the same way.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .suite import Arm

REQUIRED_COMPARATOR_FIELDS = ("source", "split", "model", "resolve_rate")

# The per-arm parameters that make an arm identity-different: models, N (best-of-N), max_rounds.
# The pre-reg locks these alongside {name, role}; a runner invoking the SAME NAMED arm with
# different values must trip the arms_hash check (review finding 151-#1: N=3 vs N=5 under the
# same name would otherwise pass the gate silently).
ARM_PARAM_KEYS = ("models", "n", "max_rounds")


class PreregistrationViolation(ValueError):
    """A confirmatory run tried to execute against a pre-reg that doesn't exist, doesn't parse, is
    missing its comparator block, or declares arms that don't match what the runner just built.

    IS-A ValueError, so existing broad handlers keep working; new code should catch this
    explicitly. The `reason` attribute names the check that failed (`missing_file`, `not_json`,
    `arms_mismatch`, `missing_comparator`, `malformed_comparator`) so a caller can route the fix.
    """

    def __init__(self, path: Path | str, reason: str, detail: str) -> None:
        super().__init__(f"pre-registration {path}: {reason} — {detail}")
        self.path = str(path)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class Preregistration:
    """A parsed `.preg.json`. The runtime carries only the fields the gate checks; the full 18-
    section template lives in the JSON and reaches the substrate-ui pane by other paths.

    `graded_rate_floor` (Sprint 170, F3 fold): the minimum fraction of attempted cells that
    must produce a definitive verdict (PASS or FAIL — not NO_VERDICT) for the report to publish
    a confirmatory delta. Design v3 § "The report contract" mandates this floor; below it,
    `build_report` emits a `RunUnpublishable` block naming the arm and gap, and collapses the
    arm's delta / CI / equivalence / fdr fields to None. Default 1.0 (every attempted cell must
    grade) matches the pre-Sprint-170 arm-completeness gate exactly. Pre-reg files typically
    pin a looser floor (0.8) that reflects the fraction of NO_VERDICT the run's shape tolerates.
    """

    path: str
    arms_hash: str
    comparator: dict[str, Any]
    raw: dict[str, Any]
    graded_rate_floor: float = 1.0


def _canonical_bytes(obj: Any) -> bytes:
    """The one JSON canonicalisation shared by pre-reg hashing and cell-provenance hashing —
    `sort_keys=True` with json.dumps's default separators (`', '`, `': '`) and default
    `ensure_ascii=True`. Matches the exact bytes `bench_coding.py:87` and
    `assay_swebench_confirmatory.py:130` already produce, so the pre-reg's fingerprint hashes
    identically to the cells sidecar's `config_fp` — a review-caught divergence (151-#2) that
    would silently produce different [:12] hashes for the same config."""
    return json.dumps(obj, sort_keys=True).encode()


def fingerprint(obj: Any) -> str:
    """The 12-char sha256 the cells sidecar has always used, promoted to a public helper so the
    two bench scripts consolidate onto one hash rather than each carrying a copy. Matches the
    existing `_fingerprint(cfg) = sha256(json.dumps(cfg, sort_keys=True))[:12]` byte-for-byte —
    the scripts import this and drop their local copies."""
    return hashlib.sha256(_canonical_bytes(obj)).hexdigest()[:12]


def arms_fingerprint(
    arms: Iterable[Arm],
    *,
    params_by_arm: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    """`sha256(canonical_bytes(sorted list of {name, role, models, n, max_rounds}))[:12]` — the
    roadmap round-3 canonical form. Fix for review finding 151-#1: an earlier version hashed
    only `{name, role}`, so a reroll that kept the arm name but changed N or the model list
    (`n_drafts_repair` with N=3 vs. N=5) would pass `check_arms_match` silently. The arm-params
    (`models`, `n`, `max_rounds`) live in `Arm.build`'s closure and cannot be extracted
    reflectively; the caller passes them in via `params_by_arm={arm.name: {"models": ..., "n":
    ..., "max_rounds": ...}}`. Missing params for an arm are treated as absent (the key is not
    in the hash payload for that arm), so a caller that doesn't know the params for an arm gets
    a hash bound to just `{name, role}` for that arm — deliberate: the pre-reg does the same,
    absence in both places matches.

    Only the reproducible declarative fields hash — `Arm.build` is a closure and not
    canonicalisable. The pre-reg names arm-params in its section 4 (arms) and this helper
    reproduces the same canonical form so the pre-reg's `arms_hash` and the runner's computed
    hash match byte-for-byte on the same inputs.
    """
    params_by_arm = params_by_arm or {}

    # Sprint 151 review fold (finding A1): a `params_by_arm` key that does not match any built
    # arm name is almost always a caller mistake — the runner renamed an arm and forgot to
    # rekey the params dict. Silently ignoring it means the runner hashes {name, role} for
    # every arm and the pre-reg (also declaring no params) matches on the degraded hash while
    # the runner is executing under UNPINNED params. Raise instead so the mistake surfaces at
    # the call boundary, not silently at the metric boundary.
    arm_names = {a.name for a in arms}
    stale = sorted(set(params_by_arm) - arm_names)
    if stale:
        raise ValueError(
            f"params_by_arm has keys with no matching arm: {stale}. Built arms: "
            f"{sorted(arm_names)!r}. This is almost always a rename mistake — every "
            "params_by_arm key must be the name of an arm being built."
        )

    def _row(a: Arm) -> dict[str, Any]:
        row: dict[str, Any] = {"name": a.name, "role": a.role}
        arm_params = params_by_arm.get(a.name, {})
        for key in ARM_PARAM_KEYS:
            if key in arm_params:
                # sort list-valued params (models) so ordering never trips the hash — same posture
                # as `arms` themselves being sorted below.
                val = arm_params[key]
                row[key] = sorted(val) if isinstance(val, list) else val
        return row

    payload = sorted([_row(a) for a in arms], key=lambda d: d["name"])
    return fingerprint(payload)


def load_preregistration(path: Path | str) -> Preregistration:
    """Read + validate a `.preg.json` file for structural correctness. Structural correctness =
    is JSON, has `arms_hash: str`, has `comparator: dict` with the four required fields, and
    `resolve_rate` is a number in [0, 1]. Does NOT validate the arms match — that is
    `check_arms_match`'s job at runner entry, after the runner has built its arms."""
    p = Path(path)
    if not p.exists():
        raise PreregistrationViolation(
            p,
            "missing_file",
            f"expected a committed pre-reg at {p}; see docs/benchmarking/benchmarking-preregistration-template.md",
        )
    try:
        raw = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        raise PreregistrationViolation(p, "not_json", str(e)) from e
    if not isinstance(raw, dict):
        raise PreregistrationViolation(
            p, "not_json", f"expected a JSON object at the top level, got {type(raw).__name__}"
        )
    arms_hash = raw.get("arms_hash")
    if not isinstance(arms_hash, str) or not arms_hash:
        raise PreregistrationViolation(
            p, "arms_mismatch", "arms_hash field is missing or not a non-empty string"
        )
    comparator = raw.get("comparator")
    if not isinstance(comparator, dict):
        raise PreregistrationViolation(
            p,
            "missing_comparator",
            "comparator: {source, split, model, resolve_rate} is required — a confirmatory number "
            "without a public anchor is unreadable (Kapoor & Narayanan 2024)",
        )
    missing = [f for f in REQUIRED_COMPARATOR_FIELDS if f not in comparator]
    if missing:
        raise PreregistrationViolation(
            p,
            "malformed_comparator",
            f"missing fields {missing}; need {list(REQUIRED_COMPARATOR_FIELDS)}",
        )
    rr = comparator.get("resolve_rate")
    if not isinstance(rr, int | float) or not (0.0 <= float(rr) <= 1.0):
        raise PreregistrationViolation(
            p, "malformed_comparator", f"resolve_rate must be a number in [0, 1]; got {rr!r}"
        )
    # Sprint 170 (F3): parse the optional graded_rate_floor. Absent defaults to 1.0 (strict —
    # matches the pre-Sprint-170 arm-completeness gate). Presence must be a number in [0, 1].
    floor_raw = raw.get("graded_rate_floor", 1.0)
    if not isinstance(floor_raw, int | float) or not (0.0 <= float(floor_raw) <= 1.0):
        raise PreregistrationViolation(
            p,
            "malformed_graded_rate_floor",
            f"graded_rate_floor must be a number in [0, 1]; got {floor_raw!r}",
        )
    return Preregistration(
        path=str(p),
        arms_hash=arms_hash,
        comparator=comparator,
        raw=raw,
        graded_rate_floor=float(floor_raw),
    )


def check_arms_match(
    pre: Preregistration,
    arms: Sequence[Arm],
    *,
    params_by_arm: Mapping[str, Mapping[str, Any]] | None = None,
) -> None:
    """Assert the runner's arms hash equals the pre-reg's `arms_hash`. Any rename / re-role /
    add-drop / param-change of an arm changes the fingerprint and fails here — the runner cannot
    silently change the arm matrix mid-confirmatory-run. `params_by_arm` threads the arm params
    (models, n, max_rounds) into the hash so a reroll on the same arm NAME (finding 151-#1)
    trips the gate; omit only when the caller genuinely has no params to declare."""
    observed = arms_fingerprint(arms, params_by_arm=params_by_arm)
    if observed != pre.arms_hash:
        raise PreregistrationViolation(
            pre.path,
            "arms_mismatch",
            f"observed arms_hash={observed} (arms={sorted(a.name for a in arms)!r}) "
            f"does not match pre-reg arms_hash={pre.arms_hash}; either the arms drifted or the "
            "pre-reg names a different matrix — either way, this is not a confirmatory run",
        )


def guard(
    preg_path: Path | str,
    arms: Sequence[Arm],
    *,
    params_by_arm: Mapping[str, Mapping[str, Any]] | None = None,
) -> Preregistration:
    """The one-call entry the runner uses. Loads the pre-reg, checks the arms match, returns the
    parsed object so the runner can echo the comparator into its meta.json + writeup. Raises
    `PreregistrationViolation` on any failure — the runner does not need to know which check
    tripped, only that the run cannot proceed. `params_by_arm` threads arm params (models, n,
    max_rounds) so a same-name reroll trips the arms_hash check (finding 151-#1)."""
    pre = load_preregistration(preg_path)
    check_arms_match(pre, arms, params_by_arm=params_by_arm)
    return pre


__all__ = [
    "ARM_PARAM_KEYS",
    "PreregistrationViolation",
    "Preregistration",
    "REQUIRED_COMPARATOR_FIELDS",
    "arms_fingerprint",
    "check_arms_match",
    "fingerprint",
    "guard",
    "load_preregistration",
]
