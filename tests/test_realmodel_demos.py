"""Real-model demo suite — every application's CLAIM, proven against a LIVE local model.

Deterministic CI proves only the wiring; per the spec it "sanitizes away the thing each topology
exists to demonstrate". This suite runs each application against a REAL local LLM (Ollama) and
asserts the claim FROM THE RECORD. The model's words are non-deterministic and irrelevant; the
topology's BEHAVIOUR is what we assert, with a deterministic predicate — NEVER an LLM-as-judge.

Every predicate here is SUBSTANTIVE and is built to FAIL on a thin/wrong run, not just on a crash:
it asserts the *thing* (distinct answers = real disagreement; the decision parsed from the real turn,
not the detector's CI fallback; recursion actually reaching the depth bound), never just "an event
exists". A predicate that cannot fail on a thin run is worthless (see the suite's history: a
div-by-zero "ensemble" where everyone agreed once passed a shell predicate).

MODELS: weak+fast `llama3.2:1b` where the claim is STRUCTURAL (it just needs real output); the
capable `qwen2.5:7b-instruct` where the claim needs reasoning (disagreement, debate progression,
role-divergent review, a real game decision). `deepseek-r1:8b` is avoided — it returns empty content.

GATING — two outcomes, never conflated:
  - a required model ABSENT  -> SKIP (reason names the model); inert on machines without it.
  - model PRESENT but the predicate FAILS -> HARD FAIL (the demo did not demonstrate).
Run here (Ollama present): part of `uv run pytest`. Deselect elsewhere: `pytest -m "not realmodel"`.
"""

from __future__ import annotations

import re

import pytest

from substrate.api import Runtime, read_record
from substrate.reference._models import OllamaResponder
from substrate.reference.r1_ensemble import ensemble_topology
from substrate.topologies.code_review import DEFAULT_ROLES, code_review_topology
from substrate.topologies.conversation_demos import (
    debate_topology,
    intel_asymmetry_topology,
    natural_conversation_topology,
    prisoners_dilemma_topology,
)
from substrate.topologies.pair_coding import pair_coding_topology
from substrate.topologies.recursive_decomposition import recursive_decomposition_topology

pytestmark = pytest.mark.realmodel

_OLLAMA_V1 = "http://localhost:11434/v1"
_FAST = "llama3.2:1b"  # structural claims: just needs real output
_SMART = "qwen2.5:7b-instruct"  # capability claims: disagreement, progression, real decisions


def _require(*models: str) -> None:
    """SKIP (never fail) iff Ollama or a required model is absent — the presence gate."""
    try:
        import httpx

        ids = {m["id"] for m in httpx.get(_OLLAMA_V1 + "/models", timeout=4).json().get("data", [])}
    except Exception as exc:  # noqa: BLE001 - any unreachability is a SKIP
        pytest.skip(f"real-model demo skipped — Ollama not reachable ({type(exc).__name__})")
    missing = [m for m in models if m not in ids]
    if missing:
        pytest.skip(f"real-model demo skipped — model(s) absent: {', '.join(missing)}")


def _payloads(root, kind):  # noqa: ANN001
    return [e["payload"] for e in read_record(root) if e["kind"] == kind]


def _has_decision_token(text: str) -> bool:
    return bool(re.search(r"\bTALK\b|STAY\s+SILENT|\bSILENT\b", text, re.IGNORECASE))


# ── ensemble (R-1): real DISAGREEMENT + real adjudication + cancel-others ───────
@pytest.mark.timeout(120)
async def test_ensemble_real_disagreement_and_cancel(tmp_path):
    _require(_FAST, _SMART)
    fast = {
        f"m{i}": OllamaResponder(_FAST, max_tokens=12, temperature=0.9, system="Answer with ONE short word. No explanation.")
        for i in range(3)
    }
    slow = {
        n: OllamaResponder(_FAST, max_tokens=12, temperature=0.9, system="Answer with ONE short word. No explanation.")
        for n in ("slowA", "slowB")
    }
    adj = OllamaResponder(_SMART, max_tokens=24, system="Given candidate answers labelled by member id, pick the single best one. Reply with JUST the member id (e.g. m0).")
    topo = ensemble_topology(
        "In one word, what is the most important quality in a leader?",
        members={**fast, **slow}, adjudicator=adj, quorum=3,
        slow_members=frozenset(slow), linger_seconds=8.0, deterministic=False,
    )
    await Runtime(tmp_path / "run").run(topo)
    envs = list(read_record(tmp_path / "run"))
    answers = [e["payload"]["answer"].strip().lower() for e in envs if e["kind"] == "Candidate"]
    verdicts = [e for e in envs if e["kind"] == "Verdict"]
    cancelled = [e for e in envs if e["kind"] == "substrate.ProducerCancelled"]
    # SUBSTANCE: the weak members genuinely DISAGREE (>=2 distinct answers) — fails on a "2+2" prompt.
    assert len(set(answers)) >= 2, f"no real disagreement; answers={answers}"
    assert len(verdicts) == 1 and verdicts[0]["payload"]["chosen"], "no real adjudication"
    assert len(cancelled) >= 2, "cancel-all-others did not fire on both lingering members"


# ── code review: role-DIVERGENT critiques + quorum adjudication + cancel-others ──
@pytest.mark.timeout(300)
async def test_code_review_role_divergence_and_cancel(tmp_path):
    _require(_SMART)
    code = (
        "def get_user(name):\n"
        "    q = \"SELECT * FROM users WHERE name = '\" + name + \"'\"\n"
        "    rows = db.execute(q)\n"
        "    out = []\n"
        "    for r in rows:\n"
        "        for s in rows:\n"
        "            if r.id == s.id: out.append(r)\n"
        "    return out"
    )
    topo = code_review_topology(
        code,
        responders={r: OllamaResponder(_SMART, max_tokens=60) for r in DEFAULT_ROLES},
        judge=OllamaResponder(_SMART, max_tokens=40), quorum=3,
        slow_roles=frozenset({"correctness", "clarity"}), linger_seconds=0.4,
    )
    await Runtime(tmp_path / "run").run(topo)
    envs = list(read_record(tmp_path / "run"))
    summaries = [str(e["payload"]["summary"]).lower() for e in envs if e["kind"] == "CritiquePosted"]
    verdicts = [e for e in envs if e["kind"] == "VerdictRendered"]
    cancelled = [e for e in envs if e["kind"] == "substrate.ProducerCancelled"]
    # SUBSTANCE: different roles surface DIFFERENT issues (>=2 distinct summaries) — fails when every
    # reviewer latches onto one glaring bug (the div-by-zero / "report the worst issue" anti-pattern).
    assert len(set(summaries)) >= 2, f"no role divergence; summaries={summaries}"
    assert len(verdicts) == 1, "the judge did not adjudicate"
    assert len(cancelled) >= 1, "lingering reviewers were not cancelled"


# ── prisoner's dilemma: the real DECISION (parsed from the real turn) is on record ──
@pytest.mark.timeout(180)
async def test_pd_real_decision_on_record(tmp_path):
    _require(_SMART)
    await Runtime(tmp_path / "run").run(
        prisoners_dilemma_topology(walkthrough=True, model=_SMART, max_rounds=1)
    )
    envs = list(read_record(tmp_path / "run"))
    turns = {t["speaker"]: t["text"] for t in (e["payload"] for e in envs if e["kind"] == "Turn")}
    decisions = {d["prisoner"]: d["choice"] for d in (e["payload"] for e in envs if e["kind"] == "Decision")}
    # SUBSTANCE: both prisoners decided, and each decision was PARSED FROM THE REAL TURN (the turn
    # contains an actual decision token) — NOT the detector's CI fallback. Fails on a thin/no-token run.
    assert set(decisions) == {1, 2}, f"both decisions not recorded: {decisions}"
    assert all(_has_decision_token(turns.get(p, "")) for p in (1, 2)), f"decision not from real turn: {turns}"
    assert all(c in {"silent", "talk"} for c in decisions.values())


# ── intel asymmetry: a calibrated JOINT CALL (from a real turn) is on record ────
@pytest.mark.timeout(240)
async def test_intel_real_jointcall_on_record(tmp_path):
    _require(_SMART)
    await Runtime(tmp_path / "run").run(
        intel_asymmetry_topology(walkthrough=True, model=_SMART, max_rounds=2)
    )
    envs = list(read_record(tmp_path / "run"))
    turns = " ".join(e["payload"]["text"] for e in envs if e["kind"] == "Turn")
    calls = [e["payload"] for e in envs if e["kind"] == "JointCall"]
    # SUBSTANCE: a calibrated assessment is recorded AND a real confidence % actually appeared in the
    # transcript (so the JointCall reflects the real model, not only the CI fallback). Fails if neither.
    assert calls, "no JointCall recorded"
    assert all(0 <= c["confidence"] <= 100 for c in calls)
    assert re.search(r"\d{1,3}\s*%", turns), f"no calibrated %% in any real turn: {turns[:200]!r}"


# ── debate: a two-sided pressure test that PROGRESSES (no echo) ─────────────────
@pytest.mark.timeout(240)
async def test_debate_progresses_without_echo(tmp_path):
    _require(_SMART)
    await Runtime(tmp_path / "run").run(debate_topology(walkthrough=True, model=_SMART, max_rounds=2))
    turns = _payloads(tmp_path / "run", "Turn")
    texts = [t["text"] for t in turns]
    # SUBSTANCE: both advocates argue across rounds AND every turn is DISTINCT (the round-2 echo bug
    # produced verbatim duplicates) — fails on the echo, which a turn-count predicate would pass.
    assert {t["speaker"] for t in turns} == {1, 2}, "both sides did not argue"
    assert len(set(texts)) == len(texts), f"echo: only {len(set(texts))} distinct of {len(texts)} turns"


# ── recursive decomposition: real recursion to the depth bound ─────────────────
@pytest.mark.timeout(180)
async def test_recursion_reaches_depth_bound(tmp_path):
    _require(_FAST)
    await Runtime(tmp_path / "run").run(
        recursive_decomposition_topology("build an auth feature", solver_model=OllamaResponder(_FAST), max_depth=2, fanout=2)
    )
    envs = list(read_record(tmp_path / "run"))
    subtasks = [e["payload"] for e in envs if e["kind"] == "SubtaskProposed"]
    solutions = [e for e in envs if e["kind"] == "SolutionReached"]
    # SUBSTANCE: the cascade actually reached the depth bound AND produced real leaf solutions —
    # fails if recursion stops short of the bound or no leaves are reached.
    assert subtasks and max(s["depth"] for s in subtasks) == 2, "recursion did not reach the depth bound"
    assert solutions, "no leaf SolutionReached — the recursion produced nothing"


# ── pair coding: the Route carries the navigator's real Suggestion into the driver ──
@pytest.mark.timeout(180)
async def test_pair_coding_route_carries_suggestion(tmp_path):
    _require(_FAST)
    await Runtime(tmp_path / "run").run(
        pair_coding_topology(
            "write a function to validate an email",
            driver_model=OllamaResponder(_FAST), navigator_model=OllamaResponder(_FAST),
            chunks=["def validate_email(s):\n", "    import re\n", "    return bool(re.match(r'.+@.+', s))\n"],
        )
    )
    envs = list(read_record(tmp_path / "run"))
    injections = [e for e in envs if e["kind"] == "substrate.InjectionApplied"]
    suggestions = [e["payload"] for e in envs if e["kind"] == "Suggestion"]
    # SUBSTANCE: real navigator Suggestions exist AND the Route actually staged them (InjectionApplied)
    # — fails if the navigator never produced one or the Route never carried it.
    assert suggestions, "the navigator produced no Suggestion"
    assert injections, "no InjectionApplied — the Route did not carry the suggestion to the driver"


# ── natural conversation: the instrument ablation DELTA (WITH vs WITHOUT) ───────
@pytest.mark.timeout(300)
async def test_instrument_ablation_delta(tmp_path):
    _require(_FAST)
    await Runtime(tmp_path / "with").run(
        natural_conversation_topology(instruments=True, walkthrough=True, model=_FAST, max_rounds=3)
    )
    await Runtime(tmp_path / "without").run(
        natural_conversation_topology(instruments=False, walkthrough=True, model=_FAST, max_rounds=3)
    )
    with_kinds = {e["kind"] for e in read_record(tmp_path / "with")}
    without_kinds = {e["kind"] for e in read_record(tmp_path / "without")}
    instrument_kinds = {"CommonGround", "Repair", "Grade"}
    # SUBSTANCE: composition is the DELTA — instruments fire WITH and are absent WITHOUT, over the
    # same prompts. Fails if the ablation shows no difference.
    assert instrument_kinds & with_kinds, "instruments did not emit in the WITH arm"
    assert not (instrument_kinds & without_kinds), "the WITHOUT arm leaked instrument events"
