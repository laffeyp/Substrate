"""Sprint 190 (roadmap v2 S5.5): `_mother_clone` emits typed events on stderr.

The B5 GitHub-clone boundary runs in the prep phase before any substrate topology starts.
Sprint 190 emits typed `RepoCloneRequested` / `RepoCloneCached` / `RepoCloned` /
`RepoCloneFailed` events to stderr as canonical JSON lines. Pins:
- Cache hit path emits `RepoCloneRequested` then `RepoCloneCached`.
- Cache miss + successful fetch emits `RepoCloneRequested` then `RepoCloned` with a
  `fetch_ms` field.
- Kind names match vocab v0.3 § G.4.
- Every event is one canonical JSON line on stderr with `boundary=repo_clone`.

Cache-miss test skipped (would require a live github fetch); cache-hit test uses a
pre-populated fake mother directory to exercise the fast path deterministically.
"""

from __future__ import annotations

import json
import subprocess


def _load_events(captured: str) -> list[dict]:
    """Parse stderr for canonical JSON event lines emitted by `_emit_repo_clone_event`."""
    events = []
    for line in captured.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("boundary") == "repo_clone":
            events.append(obj)
    return events


def test_cache_hit_emits_requested_and_cached(tmp_path, capsys, monkeypatch):
    """Populate the mother-cache root with a fake bare-clone directory; `_mother_clone` sees
    it exists, emits `RepoCloneRequested` + `RepoCloneCached`, returns without a fetch."""
    from substrate.assay import swebench_suite

    fake_cache = tmp_path / "swe-mothers"
    fake_cache.mkdir(parents=True)
    fake_mother = fake_cache / "octocat__hello.git"
    fake_mother.mkdir()  # Pretending this is a bare clone; _mother_clone only checks .exists().

    monkeypatch.setattr(swebench_suite, "_MOTHER_CACHE_ROOT", fake_cache)

    returned = swebench_suite._mother_clone("octocat/hello")
    assert returned == fake_mother

    captured = capsys.readouterr()
    events = _load_events(captured.err)
    kinds = [e["kind"] for e in events]
    assert kinds == ["RepoCloneRequested", "RepoCloneCached"], (
        f"expected [Requested, Cached] on cache hit; got {kinds}"
    )
    assert events[0]["payload"]["repo"] == "octocat/hello"
    assert events[1]["payload"]["mother_path"] == str(fake_mother)
    assert events[1]["payload"]["wall_ms"] >= 0


def test_cache_miss_failure_emits_requested_and_failed(tmp_path, capsys, monkeypatch):
    """Cache miss with a network failure: `RepoCloneRequested` then `RepoCloneFailed`. Uses a
    non-existent github repo path so `git clone --bare` fails fast."""
    from substrate.assay import swebench_suite

    fake_cache = tmp_path / "swe-mothers-miss"
    fake_cache.mkdir(parents=True)
    monkeypatch.setattr(swebench_suite, "_MOTHER_CACHE_ROOT", fake_cache)

    # Force the subprocess to fail without hitting the network. Monkeypatch subprocess.run
    # to raise CalledProcessError when the command is `git clone --bare ...`.
    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if (
            isinstance(cmd, list)
            and len(cmd) >= 4
            and cmd[:4] == ["git", "clone", "--bare", "--quiet"]
        ):
            raise subprocess.CalledProcessError(128, cmd, output=b"", stderr=b"fake network fail")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(swebench_suite.subprocess, "run", fake_run)

    try:
        swebench_suite._mother_clone("nonexistent/nope-nope")
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError("expected CalledProcessError to propagate")

    captured = capsys.readouterr()
    events = _load_events(captured.err)
    kinds = [e["kind"] for e in events]
    assert kinds == ["RepoCloneRequested", "RepoCloneFailed"], (
        f"expected [Requested, Failed] on cache miss + fetch fail; got {kinds}"
    )
    assert "error" in events[1]["payload"]
    assert events[1]["payload"]["wall_ms"] >= 0
