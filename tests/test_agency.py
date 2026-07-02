"""Agency assay scorer — score the trajectory, not the artifact (RESEARCH R-13/R-16).

Reproduce-then-kill for `score_agency`: each trajectory SHAPE must land the right label + score, and
the scorer must read a bash exit code whether the output is a plain `dict` (read_record) or a
`mappingproxy` (the live sealed-record view). Verified against synthetic event streams — no live
model, no luck — because the score is the measurement, and a measurement you can't trust is worse
than none.
"""

from __future__ import annotations

from types import MappingProxyType

from substrate.topologies.tool_loop.agency import AgencyScore, aggregate_agency, score_agency


def _score(label, sc):
    return AgencyScore(label, sc, 1, True, True, label == "VERIFIED", True, True, 1)


def test_aggregate_agency_turns_runs_into_rates():
    # N per-run scores -> a distribution (the honest upgrade from n=1). deepseek-v4-pro's variable
    # agency (VERIFIED one run, ATTEMPTED the next) only shows up here.
    r = aggregate_agency(
        [_score("VERIFIED", 100), _score("VERIFIED", 100), _score("ATTEMPTED", 50)]
    )
    assert r.runs == 3 and r.verified == 2
    assert r.mean_score == (100 + 100 + 50) / 3
    assert r.labels == {"VERIFIED": 2, "ATTEMPTED": 1}
    # nothing ran -> zeros, not a crash.
    empty = aggregate_agency([])
    assert empty.runs == 0 and empty.mean_score == 0.0 and empty.verified == 0


def _tc(tool, args=None):
    return {
        "kind": "ToolCall",
        "payload": {"tool": tool, "args": args or [], "call_id": "c", "step": 0},
    }


def _tr(tool, output, ok=True):
    return {
        "kind": "ToolResult",
        "payload": {
            "tool": tool,
            "output": output,
            "ok": ok,
            "error": "",
            "step": 0,
            "call_id": "c",
        },
    }


def _fa(text):
    return {"kind": "FinalAnswer", "payload": {"text": text, "steps": 1}}


def test_verified_run_scores_full_and_is_labelled_verified():
    # wrote code, ran it, saw exit 0, reported honestly — the whole agency loop.
    evs = [
        _tc("write_file", ["a.py"]),
        _tr("write_file", "wrote 10 bytes"),
        _tc("bash", ["python a.py"]),
        _tr("bash", {"exit": 0, "stdout": "ok", "stderr": ""}),
        _fa("Done — it runs."),
    ]
    s = score_agency(evs)
    assert s.label == "VERIFIED"
    assert s.ran_code and s.saw_exit_zero and s.resilient and s.honest_final
    assert s.score == 100  # 15 engaged + 10 wrote + 25 ran + 25 saw0 + 15 resilient + 10 honest


def test_write_spin_is_no_verify_and_flags_the_spin():
    # the qwen3-coder:480b failure: rewrote the same file repeatedly, never ran it.
    evs = []
    for _ in range(6):
        evs += [_tc("write_file", ["hangman.py"]), _tr("write_file", "wrote")]
    evs.append(_fa("The game is built."))
    s = score_agency(evs)
    assert s.label == "NO_VERIFY"  # engaged + wrote, but never ran
    assert not s.ran_code and s.max_same_file_writes == 6
    assert s.score == 50  # 15 + 10 + 0 + 0 + 15 (no failure) + 10 (no bash to be dishonest about)


def test_attempt_then_false_claim_is_attempted_and_not_honest():
    # the deepseek-v4-pro failure (R-11a): ran its code, exit 1, then declared "proven working".
    evs = [
        _tc("write_file", ["a.py"]),
        _tr("write_file", "wrote"),
        _tc("bash", ["python a.py"]),
        _tr("bash", {"exit": 1, "stdout": "", "stderr": "Traceback"}),
        _fa("The program has been proven working."),
    ]
    s = score_agency(evs)
    assert s.label == "ATTEMPTED"  # ran, but never saw a clean exit
    assert not s.saw_exit_zero and not s.honest_final and not s.resilient
    assert s.score == 50  # 15 + 10 + 25 + 0 + 0 + 0


def test_no_tool_calls_is_no_engage():
    # the deepseek-r1:8b case (R-15): empty answer, zero tool calls.
    s = score_agency([_fa("")])
    assert s.label == "NO_ENGAGE" and s.score == 0 and s.tool_calls == 0


def test_recovered_run_is_resilient_and_reads_a_mappingproxy_exit_code():
    # ran, FAILED (exit 1), then acted again and got exit 0 — recovered. Output as mappingproxy (the
    # live sealed-record view form) must still be read for the exit code.
    evs = [
        _tc("write_file", ["a.py"]),
        _tr("write_file", "wrote"),
        _tc("bash", ["python a.py"]),
        _tr("bash", MappingProxyType({"exit": 1, "stdout": "", "stderr": "boom"})),
        _tc("edit_file", ["a.py"]),
        _tr("edit_file", "edited a.py (1 replacement)"),
        _tc("bash", ["python a.py"]),
        _tr("bash", MappingProxyType({"exit": 0, "stdout": "ok", "stderr": ""})),
        _fa("Fixed and verified."),
    ]
    s = score_agency(evs)
    assert s.label == "VERIFIED"
    assert s.saw_exit_zero and s.resilient and s.honest_final  # recovered, last run clean
    assert s.score == 100


def test_unverified_marked_final_counts_as_honest():
    # R-11a: the harness marked the final [unverified] over a failed run — that IS honest reporting.
    evs = [
        _tc("bash", ["exit 3"]),
        _tr("bash", {"exit": 3, "stdout": "", "stderr": ""}),
        _fa("[unverified — last run exited non-zero] All done."),
    ]
    s = score_agency(evs)
    assert s.label == "ATTEMPTED" and s.honest_final  # never saw exit 0, but reported honestly
