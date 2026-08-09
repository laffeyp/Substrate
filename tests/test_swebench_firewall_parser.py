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
    """Regression bar: a well-formed unittest id whose derived file path IS in test_patch passes.
    F7 fix (review 2026-08-08): the parser now maps `module.sub.ClassName` -> `module/sub.py` and
    requires FILE EQUALITY against test_patch's added files, not substring. So the test_patch
    must add the exact `module/sub.py` file, not any file with those segments in its path."""
    ok, reason = firewall_check(
        _instance(
            test_patch=_test_patch_adding("module/sub.py"),
            fail_to_pass=["test_method (module.sub.ClassName)"],
        )
    )
    assert ok is True, reason


def test_unittest_id_substring_leak_fails_closed_post_F7() -> None:
    """F7 fix (review 2026-08-08): pre-fix the parser used substring match against tp_files —
    `any(frag in f for f in tp_files)` where `frag = "myapp"`. That let a pre-existing test at
    `myapp/other/test_foo.py` pass the firewall whenever test_patch happened to add ANY file
    under `myapp/`. The exact leak the firewall exists to catch. Post-fix: the derived file
    path is `myapp.py`, which is NOT equal to `myapp/other/test_foo.py`, so the check fails."""
    ok, reason = firewall_check(
        _instance(
            # test_patch adds a file under myapp/ but NOT the specific file the unittest id
            # resolves to. Pre-F7 this passed (substring "myapp" hit). Post-F7 fails.
            test_patch=_test_patch_adding("myapp/other/test_foo.py"),
            fail_to_pass=["test_foo (myapp.tests)"],
        )
    )
    assert ok is False, "F7 regression: substring-leak of pre-existing tests must fail closed"
    assert "test_foo (myapp.tests)" in reason


def test_one_segment_parenthesised_group_fails_closed() -> None:
    """A one-segment parenthesised group ('test_func (something)') is not a `module.Class` form
    and cannot resolve to a file path. Fail closed, same reason as fully-unparseable ids."""
    ok, _reason = firewall_check(_instance(fail_to_pass=["test_func (somemodule)"]))
    assert ok is False
