"""Pre-registration gate for confirmatory assay runs — sprint 151.

Pins the three checks the gate enforces (presence, arms match, comparator) and the
`arms_fingerprint` canonical form. A pre-reg that trips any check must raise
`PreregistrationViolation` with a routable `reason` — the runner never sees a partial or silent
failure that would let a confirmatory run start against a stale or missing pre-reg.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from substrate.assay.preregistration import (
    ARM_PARAM_KEYS,
    REQUIRED_COMPARATOR_FIELDS,
    Preregistration,
    PreregistrationViolation,
    arms_fingerprint,
    check_arms_match,
    fingerprint,
    guard,
    load_preregistration,
)
from substrate.assay.suite import BASELINE, FULL, Arm


def _stub_arm(name: str, role: str = FULL) -> Arm:
    """A build-only Arm — the fingerprint hashes `name` + `role`, not the closure, so a stub with
    a raising build is enough to test the gate."""

    def _build(_case):  # type: ignore[no-untyped-def]
        raise NotImplementedError("stub for gate tests")

    return Arm(name=name, role=role, build=_build)


def _write_preg(
    tmp_path: Path,
    *,
    arms_hash: str = "abc123def456",
    comparator: dict | None = None,
    extra: dict | None = None,
) -> Path:
    body = {
        "arms_hash": arms_hash,
        "comparator": comparator
        if comparator is not None
        else {
            "source": "Agentless + GPT-4o (Xia et al. 2024)",
            "split": "SWE-bench Lite",
            "model": "gpt-4o-2024-08-06",
            "resolve_rate": 0.278,
        },
        **(extra or {}),
    }
    p = tmp_path / "run.preg.json"
    p.write_text(json.dumps(body, indent=2, sort_keys=True))
    return p


def test_arms_fingerprint_is_order_independent_and_stable():
    # Two runners building the same three arms in a different order must fingerprint identically
    # — else a trivial ordering change would trip the gate for no reason.
    a, b, c = _stub_arm("alpha"), _stub_arm("bravo", role=BASELINE), _stub_arm("charlie")
    hash1 = arms_fingerprint([a, b, c])
    hash2 = arms_fingerprint([c, b, a])
    assert hash1 == hash2
    assert len(hash1) == 12  # sha256[:12] contract


def test_arms_fingerprint_changes_when_role_changes():
    # The role is part of the identity (a full arm vs the same-named baseline are DIFFERENT arms
    # in the matrix). Reroll the pre-reg, don't silently accept a role change.
    full = arms_fingerprint([_stub_arm("solver", role=FULL)])
    baseline = arms_fingerprint([_stub_arm("solver", role=BASELINE)])
    assert full != baseline


def test_arms_fingerprint_changes_when_arm_added_or_dropped():
    solo = arms_fingerprint([_stub_arm("solver")])
    duo = arms_fingerprint([_stub_arm("solver"), _stub_arm("agentic")])
    assert solo != duo


def test_missing_preg_file_raises_missing_file(tmp_path):
    with pytest.raises(PreregistrationViolation) as excinfo:
        load_preregistration(tmp_path / "does_not_exist.preg.json")
    assert excinfo.value.reason == "missing_file"


def test_malformed_json_raises_not_json(tmp_path):
    p = tmp_path / "bad.preg.json"
    p.write_text("{ not: valid json,")
    with pytest.raises(PreregistrationViolation) as excinfo:
        load_preregistration(p)
    assert excinfo.value.reason == "not_json"


def test_missing_arms_hash_raises(tmp_path):
    p = tmp_path / "noarms.preg.json"
    p.write_text(json.dumps({"comparator": {}}))
    with pytest.raises(PreregistrationViolation) as excinfo:
        load_preregistration(p)
    assert excinfo.value.reason == "arms_mismatch"


def test_missing_comparator_raises_missing_comparator(tmp_path):
    # A pre-reg with no comparator block is the exact failure mode the roadmap round-3 fold
    # named: a confirmatory number without a public anchor is unreadable.
    p = tmp_path / "no_comp.preg.json"
    p.write_text(json.dumps({"arms_hash": "abc"}))
    with pytest.raises(PreregistrationViolation) as excinfo:
        load_preregistration(p)
    assert excinfo.value.reason == "missing_comparator"


def test_comparator_missing_required_field_raises_malformed(tmp_path):
    for field in REQUIRED_COMPARATOR_FIELDS:
        comp = {
            "source": "x",
            "split": "y",
            "model": "z",
            "resolve_rate": 0.5,
        }
        del comp[field]
        p = _write_preg(tmp_path, comparator=comp)
        with pytest.raises(PreregistrationViolation) as excinfo:
            load_preregistration(p)
        assert excinfo.value.reason == "malformed_comparator"
        assert field in excinfo.value.detail


def test_comparator_resolve_rate_out_of_range_raises_malformed(tmp_path):
    for bad in (-0.1, 1.1, "seventy-eight percent"):
        p = _write_preg(
            tmp_path,
            comparator={
                "source": "s",
                "split": "sp",
                "model": "m",
                "resolve_rate": bad,
            },
        )
        with pytest.raises(PreregistrationViolation) as excinfo:
            load_preregistration(p)
        assert excinfo.value.reason == "malformed_comparator"


def test_load_preregistration_returns_the_parsed_object(tmp_path):
    # The happy path — the gate hands back a Preregistration the runner can echo into meta.json.
    p = _write_preg(tmp_path, arms_hash="deadbeef1234")
    pre = load_preregistration(p)
    assert isinstance(pre, Preregistration)
    assert pre.arms_hash == "deadbeef1234"
    assert pre.comparator["source"].startswith("Agentless")
    assert pre.comparator["resolve_rate"] == 0.278
    assert pre.raw["arms_hash"] == "deadbeef1234"


def test_check_arms_match_accepts_the_correct_hash(tmp_path):
    arms = [_stub_arm("solver"), _stub_arm("baseline", role=BASELINE)]
    correct_hash = arms_fingerprint(arms)
    p = _write_preg(tmp_path, arms_hash=correct_hash)
    pre = load_preregistration(p)
    check_arms_match(pre, arms)  # no raise


def test_check_arms_match_rejects_wrong_hash(tmp_path):
    arms = [_stub_arm("solver")]
    p = _write_preg(tmp_path, arms_hash="wrong_hash_00")
    pre = load_preregistration(p)
    with pytest.raises(PreregistrationViolation) as excinfo:
        check_arms_match(pre, arms)
    assert excinfo.value.reason == "arms_mismatch"


def test_guard_one_call_load_and_check(tmp_path):
    # The runner's one-call entry: load + check in one atomic gate call.
    arms = [_stub_arm("solver"), _stub_arm("agentic", role=BASELINE)]
    p = _write_preg(tmp_path, arms_hash=arms_fingerprint(arms))
    pre = guard(p, arms)
    assert pre.comparator["model"] == "gpt-4o-2024-08-06"


def test_guard_refuses_when_arms_drift(tmp_path):
    # The runner built n=3 arms but the pre-reg was for n=1 — refuse and name the reason.
    p = _write_preg(tmp_path, arms_hash=arms_fingerprint([_stub_arm("solo")]))
    with pytest.raises(PreregistrationViolation, match="arms_mismatch"):
        guard(p, [_stub_arm("solo"), _stub_arm("also_solo")])


def test_preregistration_violation_is_a_valueerror():
    # Backwards-compat: existing broad `except ValueError` handlers still catch the gate failure.
    # Sprint 143's FirewallViolation used the same discipline.
    exc = PreregistrationViolation("path", "arms_mismatch", "detail")
    assert isinstance(exc, ValueError)


def test_arms_fingerprint_changes_when_arm_params_change():
    # Review finding 151-#1: an earlier version of `arms_fingerprint` hashed only {name, role},
    # so a reroll on the same arm name (N=3 -> N=5, or a swap of the models list) would pass
    # `check_arms_match` silently. The fix: params_by_arm threads (models, n, max_rounds) into
    # the hash. This is the specific regression the reviewer flagged.
    arms = [_stub_arm("solver")]
    hash_n3 = arms_fingerprint(
        arms, params_by_arm={"solver": {"models": ["m1"], "n": 3, "max_rounds": 2}}
    )
    hash_n5 = arms_fingerprint(
        arms, params_by_arm={"solver": {"models": ["m1"], "n": 5, "max_rounds": 2}}
    )
    hash_models = arms_fingerprint(
        arms, params_by_arm={"solver": {"models": ["m2"], "n": 3, "max_rounds": 2}}
    )
    hash_rounds = arms_fingerprint(
        arms, params_by_arm={"solver": {"models": ["m1"], "n": 3, "max_rounds": 4}}
    )
    assert len({hash_n3, hash_n5, hash_models, hash_rounds}) == 4
    # Same params, same hash — the fingerprint is stable given the same inputs.
    hash_n3_again = arms_fingerprint(
        arms, params_by_arm={"solver": {"models": ["m1"], "n": 3, "max_rounds": 2}}
    )
    assert hash_n3 == hash_n3_again


def test_arms_fingerprint_is_order_independent_on_models_list():
    # A rerun that shuffles the model list must not trip the hash — models are a SET-of-strings
    # in effect, so the canonical form sorts them. Otherwise a trivial reorder would be a false
    # positive for reroll detection.
    arms = [_stub_arm("solver")]
    a = arms_fingerprint(arms, params_by_arm={"solver": {"models": ["m1", "m2", "m3"], "n": 3}})
    b = arms_fingerprint(arms, params_by_arm={"solver": {"models": ["m3", "m1", "m2"], "n": 3}})
    assert a == b


def test_arms_fingerprint_omitting_params_matches_older_shape():
    # A caller that doesn't declare any per-arm params should get the {name, role}-only hash —
    # so pre-152-review pre-regs (which locked only name+role) still validate cleanly against a
    # runner that also declines to declare params. Deliberate: the pre-reg and the runner must
    # match at the level of declaration; both silent is fine.
    arms = [_stub_arm("solver")]
    no_params = arms_fingerprint(arms)
    empty_params = arms_fingerprint(arms, params_by_arm={})
    assert no_params == empty_params


def test_guard_rejects_reroll_of_arm_params_via_params_by_arm():
    # End-to-end regression pin for finding 151-#1 through the `guard` entrypoint. Pre-reg was
    # locked at N=3; runner tries to execute at N=5 under the same arm name. Gate must catch this.
    import tempfile

    arm = _stub_arm("solver")
    locked_hash = arms_fingerprint([arm], params_by_arm={"solver": {"models": ["m1"], "n": 3}})
    with tempfile.TemporaryDirectory() as td:
        p = _write_preg(Path(td), arms_hash=locked_hash)
        # runner invokes with N=5 — must fail.
        with pytest.raises(PreregistrationViolation, match="arms_mismatch"):
            guard(p, [arm], params_by_arm={"solver": {"models": ["m1"], "n": 5}})
        # runner invokes with N=3 — must pass.
        pre = guard(p, [arm], params_by_arm={"solver": {"models": ["m1"], "n": 3}})
        assert pre.arms_hash == locked_hash


def test_fingerprint_matches_bare_json_dumps_bytes():
    # Review finding 151-#2: preregistration.fingerprint MUST hash byte-identically to the
    # `_fingerprint` the two bench scripts already ship (`sha256(json.dumps(cfg, sort_keys=True))
    # [:12]`) — otherwise the pre-reg and the cell-provenance stamp would differ on the same
    # config and the consolidation the docstring promises is a lie. This test pins the byte match.
    import hashlib
    import json as _json

    for cfg in [
        {"models": ["m1", "m2"], "n": 3, "margin": 0.10},
        {"assay_kind": "swebench", "arm_name": "solver", "role": "full"},
        {"nested": {"a": 1, "b": [1, 2, 3]}, "top": "value"},
    ]:
        expected = hashlib.sha256(_json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:12]
        assert fingerprint(cfg) == expected


def test_arms_fingerprint_raises_on_stale_params_by_arm_key():
    # Review finding A1 (fold-pass audit): a `params_by_arm` key with no matching arm is
    # almost always a rename-forgotten-to-rekey mistake. Silently ignoring it means both sides
    # can drop to {name, role} and the arms_hash matches while the runner executes under
    # unpinned params. Raise instead so the mistake surfaces at the call boundary.
    arm = _stub_arm("solver")
    with pytest.raises(ValueError, match="params_by_arm has keys with no matching arm"):
        arms_fingerprint([arm], params_by_arm={"solver_OLD_NAME": {"n": 3}})
    # A caller that also passes params for a real arm alongside a stale one still fails —
    # the raise triggers on ANY stale key, not "only if all keys are stale".
    with pytest.raises(ValueError, match="solver_OLD_NAME"):
        arms_fingerprint([arm], params_by_arm={"solver": {"n": 3}, "solver_OLD_NAME": {"n": 5}})


def test_check_arms_match_raises_on_stale_params_via_guard():
    # End-to-end pin for A1 through `guard`: a caller who invokes guard with stale param keys
    # gets the ValueError, not a spurious pass.
    import tempfile

    arm = _stub_arm("solver")
    correct = arms_fingerprint([arm])  # pre-reg declared no params — {name, role} hash
    with tempfile.TemporaryDirectory() as td:
        p = _write_preg(Path(td), arms_hash=correct)
        # Runner passes stale params_by_arm — the raise fires INSIDE arms_fingerprint before
        # the hash comparison would silently pass on the degraded {name, role} shape.
        with pytest.raises(ValueError, match="no matching arm"):
            guard(p, [arm], params_by_arm={"the_arm_i_meant_to_pass_params_for": {"n": 3}})


def test_arm_param_keys_constant_names_the_reroll_surface():
    # ARM_PARAM_KEYS is exported so a caller (the runner, substrate-ui) can enumerate the exact
    # params a reroll can differ on without hardcoding the list. Any addition to this tuple is a
    # deliberate widening of the reroll-detection surface, not an accidental omission.
    assert ARM_PARAM_KEYS == ("models", "n", "max_rounds")
