"""Graph-projection tests (Wave 12 prep): topology_graph (static structure) and run_graph
(dynamic run-as-graph). Both are pure read-only projections — same record, same graph; they
accept a root path or an iterable of envelopes; they cite seqs. These pin the structure/edges,
the spawn forest with lifecycle spans, the concurrency the spans encode, and the edge cases
(a still-running instance, a record with no manifest).
"""

import pathlib

from substrate import api
from substrate.errors import RecordIncompleteError, SubstrateError
from substrate.projections.graph import run_graph, topology_graph
from substrate.topologies import bundled

CODE_REVIEW = bundled.record_path("code_review")
NAT_CONV = bundled.record_path("natural_conversation")


# ── topology_graph (static) ─────────────────────────────────────────────────────────────────
def test_topology_graph_nodes_and_roots() -> None:
    g = topology_graph(CODE_REVIEW)
    by_kind = {n.kind: n for n in g.producers}
    assert set(by_kind) == {
        "reviewer-security",
        "reviewer-performance",
        "reviewer-style",
        "reviewer-correctness",
        "reviewer-clarity",
        "judge",
    }
    # the five reviewers are the entry points (initial); the judge is spawned by adjudicate.
    assert by_kind["reviewer-security"].is_initial is True
    assert by_kind["judge"].is_initial is False
    assert by_kind["reviewer-security"].emits == ("CritiquePosted",)
    assert by_kind["judge"].emits == ("VerdictRendered",)


def test_topology_graph_is_initial_is_correct_for_a_cyclic_topology() -> None:
    # the round-robin footgun: natural_conversation's `after-N` trigger wraps to START speaker-1,
    # so "no incoming trigger edge" would wrongly report ZERO entry points. is_initial reads the
    # __initial__ firings instead, so speaker-1 is correctly an entry point despite being a target.
    g = topology_graph(NAT_CONV)
    by_kind = {n.kind: n for n in g.producers}
    assert by_kind["speaker-1"].is_initial is True
    assert by_kind["speaker-2"].is_initial is False  # only ever spawned by a Trigger
    assert sum(n.is_initial for n in g.producers) == 1  # exactly one entry point


def test_topology_graph_trigger_edges() -> None:
    g = topology_graph(CODE_REVIEW)
    adj = next(t for t in g.triggers if t.id == "adjudicate")
    assert adj.starts == "judge"
    assert adj.on == ("CritiquePosted",)
    assert adj.policy == "Once"


def test_topology_graph_routes_and_views() -> None:
    g = topology_graph(NAT_CONV)  # natural_conversation has Routes (the instruments stage forward)
    slots = {r.slot for r in g.routes}
    assert {"cg", "repair"} <= slots
    assert "transcript" in g.views
    assert g.termination  # the TerminationPolicy descriptor is present


def test_topology_graph_no_manifest_raises_typed_error() -> None:
    # a typed SubstrateError (review #29), not a bare ValueError, so an api-only consumer
    # catching SubstrateError to show "structure unavailable" still catches it.
    try:
        topology_graph([{"seq": 0, "kind": "NotARunStart", "payload": {}}])
    except RecordIncompleteError as e:
        assert "RunStarted" in str(e)
        assert isinstance(e, SubstrateError)
    else:
        raise AssertionError("expected RecordIncompleteError for a record with no manifest")


def test_topology_graph_accepts_path_and_iterable() -> None:
    from_path = topology_graph(CODE_REVIEW)
    from_iter = topology_graph(list(api.read_record(CODE_REVIEW)))
    assert from_path == from_iter  # frozen Structs compare by value


# ── run_graph (dynamic) ─────────────────────────────────────────────────────────────────────
def test_run_graph_spawn_forest() -> None:
    g = run_graph(CODE_REVIEW)
    assert g.status == "finalised" and g.final_reason is None and g.paused_on is None
    by_kind = {i.kind: i for i in g.instances}
    assert len(g.instances) == 6
    # initials: trigger __initial__, no parent.
    sec = by_kind["reviewer-security"]
    assert sec.trigger_id == "__initial__" and sec.parent is None and sec.status == "completed"
    assert sec.emitted == ("CritiquePosted",)
    # the judge: spawned by adjudicate, parented to the reviewer instance whose critique fired it.
    judge = by_kind["judge"]
    assert judge.trigger_id == "adjudicate" and judge.parent is not None
    assert judge.emitted == ("VerdictRendered",)
    # the two slow reviewers were cancelled (started, never completed, emitted nothing).
    assert by_kind["reviewer-correctness"].status == "cancelled"
    assert by_kind["reviewer-clarity"].emitted == ()


def test_run_graph_carries_the_firing_anchor() -> None:
    # fired_seq (the TriggerFired seq) is the t-free concurrency anchor the run-as-graph renders
    # on — it precedes started_seq (scheduled before it ran). review #29 follow-up.
    g = run_graph(CODE_REVIEW)
    judge = next(i for i in g.instances if i.kind == "judge")
    assert judge.fired_seq is not None and judge.started_seq is not None
    assert judge.fired_seq < judge.started_seq  # scheduled (fired) before it began running
    # every instance with a start has a firing that precedes it
    for i in g.instances:
        if i.fired_seq is not None and i.started_seq is not None:
            assert i.fired_seq <= i.started_seq


def test_run_graph_is_in_spawn_order() -> None:
    seqs = [i.started_seq for i in run_graph(CODE_REVIEW).instances]
    assert seqs == sorted(s for s in seqs if s is not None)


def test_run_graph_spans_encode_concurrency() -> None:
    # the design's load-bearing fact: producers run at once. Max concurrent spans must exceed 1.
    g = run_graph(CODE_REVIEW)
    spans = [
        (i.started_seq, i.ended_seq)
        for i in g.instances
        if i.started_seq is not None and i.ended_seq is not None
    ]
    max_concurrent = 0
    for s, _ in spans:
        active = sum(1 for a, b in spans if a <= s <= b)
        max_concurrent = max(max_concurrent, active)
    assert max_concurrent > 1  # at least two producers overlap in time


def test_run_graph_running_instance_has_no_end() -> None:
    # a producer that started but has no lifecycle-end event is "running", ended_seq None.
    envs = [
        {"seq": 0, "kind": "substrate.RunStarted", "payload": {"run_id": "R"}},
        {
            "seq": 1,
            "kind": "substrate.TriggerFired",
            "payload": {"instance": "i1", "factory": "worker", "trigger_id": "__initial__"},
        },
        {
            "seq": 2,
            "kind": "substrate.ProducerStarted",
            "payload": {"producer": {"kind": "worker", "instance": "i1", "parent": None}},
        },
        # no ProducerCompleted/Failed/Cancelled for i1
    ]
    g = run_graph(envs)
    (inst,) = g.instances
    assert inst.status == "running" and inst.ended_seq is None and inst.started_seq == 2
    # the RUN has no terminal RunFinalised -> "incomplete" (not a clean "running"); a torn/
    # medium-failed record must not read as fine after the engine->run_graph seam swap (review #31).
    assert g.status == "incomplete"


def test_run_graph_paused_run_is_distinct_from_running() -> None:
    # review #29: the outcome surface needs paused (awaiting input) distinguished from
    # still-running, with WHAT it awaits.
    envs = [
        {"seq": 0, "kind": "substrate.RunStarted", "payload": {"run_id": "R"}},
        {
            "seq": 1,
            "kind": "substrate.TerminationMatched",
            "payload": {"decision": "pause-await-input", "resume_condition": "OperatorOverride"},
        },
        # no RunFinalised — the run is paused, not finished
    ]
    g = run_graph(envs)
    assert g.status == "paused"
    assert g.paused_on == "OperatorOverride"


def test_run_graph_started_not_ended_is_interrupted_in_a_finished_run() -> None:
    # review #38: a Producer started but with no end-record, in a run that is OVER (finalised or
    # paused), is "interrupted" — it will never complete (e.g. cut off by a pause). NOT "running"
    # (a finished run must not show live work). "running" stays reserved for incomplete runs.
    env = [
        {"seq": 0, "kind": "substrate.RunStarted", "payload": {"run_id": "R"}},
        {
            "seq": 1,
            "kind": "substrate.TriggerFired",
            "payload": {"instance": "i1", "factory": "w", "trigger_id": "__initial__"},
        },
        {
            "seq": 2,
            "kind": "substrate.ProducerStarted",
            "payload": {"producer": {"kind": "w", "instance": "i1", "parent": None}},
        },
        # NO ProducerCompleted for i1 — interrupted
        {"seq": 3, "kind": "substrate.RunFinalised", "payload": {}},
    ]
    g = run_graph(env)
    assert g.status == "finalised"
    assert g.instances[0].status == "interrupted"  # over + un-ended -> interrupted, not "running"


def test_run_graph_run_level_failure_is_status_failed() -> None:
    # review #30 finding 1: a run-level failure (kernel_error / stuck_quiescent / view_failure)
    # is status="failed", NOT "finalised" — else the outcome surface renders it green (§7.2).
    for reason in ("kernel_error", "stuck_quiescent", "view_failure"):
        env = [
            {"seq": 0, "kind": "substrate.RunStarted", "payload": {"run_id": "R"}},
            {"seq": 1, "kind": "substrate.RunFinalised", "payload": {"reason": reason}},
        ]
        g = run_graph(env)
        assert g.status == "failed", reason
        assert g.final_reason == reason


def test_run_graph_clean_finalise_with_producer_failures_is_still_finalised() -> None:
    # the OTHER failure notion (finished != worked): the RUN finalised cleanly but a Producer
    # failed inside it. That is status="finalised" + a failed instance — not run-level "failed".
    env = [
        {"seq": 0, "kind": "substrate.RunStarted", "payload": {"run_id": "R"}},
        {
            "seq": 1,
            "kind": "substrate.TriggerFired",
            "payload": {"instance": "i1", "factory": "w", "trigger_id": "__initial__"},
        },
        {
            "seq": 2,
            "kind": "substrate.ProducerStarted",
            "payload": {"producer": {"kind": "w", "instance": "i1", "parent": None}},
        },
        {
            "seq": 3,
            "kind": "substrate.ProducerFailed",
            "payload": {
                "producer": {"kind": "w", "instance": "i1", "parent": None},
                "error": "boom",
            },
        },
        {"seq": 4, "kind": "substrate.RunFinalised", "payload": {}},
    ]
    g = run_graph(env)
    assert g.status == "finalised"  # the RUN itself finalised cleanly...
    assert (
        g.instances[0].status == "failed"
    )  # ...but a Producer inside it failed (finished!=worked)


def test_run_graph_is_deterministic() -> None:
    a, b = run_graph(CODE_REVIEW), run_graph(CODE_REVIEW)
    assert a == b


def test_run_graph_accepts_path_and_iterable(tmp_path: pathlib.Path) -> None:
    from_path = run_graph(CODE_REVIEW)
    from_iter = run_graph(list(api.read_record(CODE_REVIEW)))
    assert from_path == from_iter
