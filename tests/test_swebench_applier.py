"""Observation contract for the SEARCH/REPLACE applier (sprint 135, gate #2).

The applier is DETERMINISTic given (candidate text, repo state), so its observation contract is an
ordinary unit test (design §4b / KIT_DIARY 11). Real git repos in tmp; asserts on the structured result
+ the produced model_patch + the on-disk bytes. Every tier and every reject path is exercised.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from substrate.topologies.swebench_solver.applier import apply_candidate, parse_candidate


def _repo(files: dict[str, bytes]) -> str:
    d = tempfile.mkdtemp()
    for rel, data in files.items():
        p = Path(d) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    for args in (
        ["git", "-C", d, "init", "-q"],
        ["git", "-C", d, "config", "user.email", "t@t"],
        ["git", "-C", d, "config", "user.name", "t"],
        ["git", "-C", d, "add", "-A"],
        ["git", "-C", d, "commit", "-qm", "base"],
    ):
        subprocess.run(args, capture_output=True, check=True)
    return d


def _block(path: str, search: str, replace: str) -> str:
    return f"# path: {path}\n<<<<<<< SEARCH\n{search}\n=======\n{replace}\n>>>>>>> REPLACE\n"


def test_exact_match_applies_and_diffs():
    d = _repo({"m.py": b"def f(x):\n    return x\n"})
    r = apply_candidate(_block("m.py", "    return x", "    return x + 1"), d)
    assert r.applied and not r.creates_file
    assert "+    return x + 1" in r.model_patch and "-    return x" in r.model_patch
    assert (Path(d) / "m.py").read_text() == "def f(x):\n    return x + 1\n"


def test_whitespace_flexible_match_tier2():
    # a genuine tier-2 case: the model emits the 2-line block at ITS OWN indentation (0 + 4 spaces), which
    # is NOT an exact substring of the file (4 + 8 spaces). Tier 1 (exact) misses; tier 2 (leading-ws
    # flexible, line-based) matches uniquely and RE-INDENTS the replacement to the file's real indentation.
    d = _repo({"m.py": b"class C:\n    def f(self):\n        return 1\n"})
    search = "def f(self):\n    return 1"  # model's indentation, not the file's
    replace = "def f(self):\n    return 2"
    assert search not in "class C:\n    def f(self):\n        return 1\n"  # confirms tier 1 cannot match
    r = apply_candidate(_block("m.py", search, replace), d)
    assert r.applied, r.error
    assert (Path(d) / "m.py").read_text() == "class C:\n    def f(self):\n        return 2\n"


def test_not_found_rejects():
    d = _repo({"m.py": b"a = 1\n"})
    r = apply_candidate(_block("m.py", "b = 2", "b = 3"), d)
    assert not r.applied and r.error is not None and "not found" in r.error
    assert (Path(d) / "m.py").read_text() == "a = 1\n"  # untouched


def test_ambiguous_rejects():
    d = _repo({"m.py": b"x = 0\nx = 0\n"})
    r = apply_candidate(_block("m.py", "x = 0", "x = 9"), d)
    assert not r.applied and r.error is not None and "ambiguous" in r.error


def test_overlapping_blocks_reject():
    d = _repo({"m.py": b"abcdef\n"})
    text = _block("m.py", "abc", "X") + _block("m.py", "bcd", "Y")  # spans [0,3) and [1,4) overlap
    r = apply_candidate(text, d)
    assert not r.applied and r.error is not None and "overlap" in r.error
    assert (Path(d) / "m.py").read_text() == "abcdef\n"  # untouched


def test_file_creation_empty_search():
    d = _repo({"m.py": b"x = 1\n"})
    r = apply_candidate(_block("new_mod.py", "", "VALUE = 42\n"), d)
    assert r.applied and r.creates_file
    assert "new file mode" in r.model_patch and "+VALUE = 42" in r.model_patch
    assert (Path(d) / "new_mod.py").read_text() == "VALUE = 42\n"


def test_empty_search_on_existing_file_rejects():
    d = _repo({"m.py": b"x = 1\n"})
    r = apply_candidate(_block("m.py", "", "OVERWRITE\n"), d)
    assert not r.applied and r.error is not None and "existing" in r.error


def test_crlf_preserved():
    d = _repo({"w.py": b"line1\r\nline2\r\n"})
    r = apply_candidate(_block("w.py", "line2", "line2x"), d)
    assert r.applied, r.error
    assert (Path(d) / "w.py").read_bytes() == b"line1\r\nline2x\r\n"  # CRLF restored


def test_atomic_across_files():
    # file A's block is valid, file B's block is not — NOTHING is written (all-or-nothing).
    d = _repo({"a.py": b"aaa\n", "b.py": b"bbb\n"})
    text = _block("a.py", "aaa", "AAA") + _block("b.py", "zzz", "ZZZ")
    r = apply_candidate(text, d)
    assert not r.applied and r.error is not None
    assert (Path(d) / "a.py").read_text() == "aaa\n"  # A NOT written despite being valid
    assert (Path(d) / "b.py").read_text() == "bbb\n"


def test_multiple_disjoint_blocks_one_file():
    d = _repo({"m.py": b"top = 1\nmid = 2\nbot = 3\n"})
    text = _block("m.py", "top = 1", "top = 11") + _block("m.py", "bot = 3", "bot = 33")
    r = apply_candidate(text, d)
    assert r.applied, r.error
    assert (Path(d) / "m.py").read_text() == "top = 11\nmid = 2\nbot = 33\n"


def test_parse_rejects_unterminated_block():
    import pytest

    with pytest.raises(ValueError):
        parse_candidate("# path: m.py\n<<<<<<< SEARCH\nfoo\n=======\nbar\n")  # missing close marker
