# Sprint 192 — `docker pull` emits typed events (roadmap v2 S5.4)

Same shape as Sprint 190. `scripts/assay_swebench_confirmatory.py::_pull` (the prepull loop) emits `ImageRequested` on entry, then `ImagePulled` (rc=0) or `ImageMissing` (non-zero rc, includes returncode + stderr tail) on the terminal branch. Kind names match vocab v0.3 § G.3. Canonical JSON to stderr with `boundary=image_pull`; prep phase runs before any substrate topology.

Files: `scripts/assay_swebench_confirmatory.py` (in-line emit helper + refactored `_pull`) + `tests/test_image_pull_events.py` (source-scan pins covering the three kinds + the boundary marker + wall_ms field). 2/2 tests pass; ruff clean.
