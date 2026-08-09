"""Sprint 142 — firewall_check parses test ids and MUST fail closed on unparseable ones.

The unittest/django test-id branch (matching `test_func (module.sub.Class)`) previously returned
True on parse failure with the reasoning "condition 1 still guards" — but condition 1 checks
patch/test_patch FILE intersection, not held-out test-id resolution, so an unparseable FAIL_TO_PASS
id silently admitted an instance whose held-out tests could not be verified to be added by
test_patch. That is fail-open on a security check. Sprint 142 flips the default: an unparseable id
is treated as "not in test_patch" (a leak), so firewall_check surfaces it and the caller excludes
the instance.
"""

from __future__ import annotations

from substrate.assay.swebench import firewall_check


def _instance(*, patch: str = "", test_patch: str = "", fail_to_pass: list[str]) -> dict:
    return {
        "patch": patch,
        "test_patch": test_patch,
        "FAIL_TO_PASS": fail_to_pass,
        "instance_id": "test__sprint-142",
    }


def _test_patch_adding(path: str) -> str:
    # A minimal git-style diff header the _added_files parser recognises.
    return f"diff --git a/{path} b/{path}\n--- /dev/null\n+++ b/{path}\n@@ -0,0 +1 @@\n+pass\n"


def test_unparseable_unittest_id_fails_closed() -> None:
    """An id that matches neither pytest ('::') nor unittest ('(module.Class)') MUST exclude the
    instance. Pre-142 behaviour returned True here."""
    # No "::" (not pytest form), no "(module)" parens (not unittest form).
    ok, reason = firewall_check(_instance(fail_to_pass=["totally_unparseable_id_no_form"]))
    assert ok is False, "unparseable id must fail closed"
    assert "totally_unparseable_id_no_form" in reason


def test_parseable_pytest_id_added_by_test_patch_passes() -> None:
    """Regression bar: a well-formed pytest id whose file IS in test_patch still passes."""
    ok, reason = firewall_check(
        _instance(
            test_patch=_test_patch_adding("tests/test_x.py"),
            fail_to_pass=["tests/test_x.py::test_y"],
        )
    )
    assert ok is True, reason


def test_parseable_pytest_id_missing_from_test_patch_fails() -> None:
    """Regression bar: a well-formed pytest id whose file is NOT in test_patch still fails."""
    ok, reason = firewall_check(
        _instance(
            test_patch=_test_patch_adding("tests/test_other.py"),
            fail_to_pass=["tests/test_x.py::test_y"],
        )
    )
    assert ok is False
    assert "tests/test_x.py::test_y" in reason


def test_parseable_unittest_id_added_by_test_patch_passes() -> None:
    """Regression bar: a well-formed unittest id ('name (module.sub.Class)') whose module maps to
    a file fragment inside a test_patch path still passes."""
    ok, reason = firewall_check(
        _instance(
            test_patch=_test_patch_adding("django/tests/module/sub/test_thing.py"),
            fail_to_pass=["test_method (module.sub.ClassName)"],
        )
    )
    assert ok is True, reason
