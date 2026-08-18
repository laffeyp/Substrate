"""Sprint 193 (roadmap v2 S5.6): typed events on the B6 swebench-harness boundary.

`run_swebench_one` at `assay/swebench.py:397` emits `HarnessCallFired` on entry, then one
of `HarnessReportRead` / `HarnessCompleted` / `HarnessTimeout` / `HarnessError` on the
terminal branch. Same stderr-JSON pattern as Sprint 190's repo-clone events and Sprint 192's
image-pull events.

The empty-patch fast path exits before spawning the harness subprocess and is deterministic
under any environment (no Docker, no swebench install needed) — cover it here. The four
Docker-dependent branches (Timeout / ContainerCrashed / MissingReport / Completed via
`read_resolved`) fire under live Docker and land under
`tests/test_assay_swebench_harness_binding.py` when the swebench harness gate is enabled.
Source-scan pins verify the emit call sites survive future edits.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _load_events(captured: str) -> list[dict]:
    events = []
    for line in captured.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("boundary") == "harness":
            events.append(obj)
    return events


def test_empty_patch_emits_call_fired_then_completed(capsys, tmp_path):
    """The empty-patch fast path returns Verdict.FAIL immediately without spawning the
    harness. Emits `HarnessCallFired` on entry and `HarnessCompleted` (verdict=fail) on
    the fast-path terminal."""
    from substrate.assay.oracle import Verdict
    from substrate.assay.swebench import run_swebench_one

    outcome = run_swebench_one(
        instance_id="test__instance",
        model_patch="",  # empty patch → fast-path FAIL
        dataset_name="princeton-nlp/SWE-bench_Lite",
        model_name="test-model",
        run_id="test-run",
        report_dir=tmp_path / "reports",
        timeout_seconds=60,
    )
    assert outcome.verdict is Verdict.FAIL

    captured = capsys.readouterr()
    events = _load_events(captured.err)
    kinds = [e["kind"] for e in events]
    assert kinds == ["HarnessCallFired", "HarnessCompleted"], (
        f"expected [HarnessCallFired, HarnessCompleted] on the empty-patch fast path; got {kinds}"
    )
    assert events[0]["payload"]["instance_id"] == "test__instance"
    assert events[0]["payload"]["patch_bytes"] == 0
    assert events[1]["payload"]["verdict"] == "fail"
    assert events[1]["payload"]["reason"] == ""
    assert events[1]["payload"]["wall_ms"] >= 0


def test_harness_source_contains_five_event_kinds() -> None:
    """Source-scan pin: `run_swebench_one` emits all five vocab v0.3 § G.5 kinds. A future
    refactor that drops any of the five trips this. The Docker-dependent branches
    (Timeout / two flavors of HarnessError / HarnessReportRead / HarnessCompleted via
    read_resolved) are hard to reach without live Docker; the pin catches the emit sites
    surviving a rewrite."""
    src = Path(sys.modules["substrate.assay.swebench"].__file__ or "").read_text()
    for kind in (
        "HarnessCallFired",
        "HarnessReportRead",
        "HarnessCompleted",
        "HarnessTimeout",
        "HarnessError",
    ):
        assert kind in src, (
            f"expected {kind!r} event kind at the harness boundary; Sprint 193 wired all five"
        )
    assert '"harness"' in src, "expected the boundary marker `harness` in the emit helper"
