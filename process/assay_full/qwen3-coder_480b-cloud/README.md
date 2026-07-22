# results.jsonl — label annotation (2026-07-22)

`results.jsonl` is the checkpoint of the full SWE-bench Lite run (300 instances,
qwen3-coder:480b-cloud, n=3, 2026-06-27). The counts are authoritative and reproduce the
recorded tally exactly: resolved 108, wrong_patch 175, no_applicable_edit 12, ungraded 5,
sum 300; firewall_clean 291/300.

**Label drift, recorded rather than rewritten:** the 5 ungraded sympy rows carry
`status="error"` with detail `FileNotFoundError: no swebench report.json`. The
`grade_unavailable` status (KIT_DIARY finding 27) landed in `scripts/assay_full_run.py`
AFTER this run completed; this checkpoint was never re-emitted, so it predates the label.
Read the 5 `status="error"` rows as `grade_unavailable` — the topology produced a valid
patch for each; only the official harness's eval image was unavailable (the missing
report.json is the downstream symptom of the upstream image-build failure). A fresh run
through the current runner emits the corrected labels. The file itself is append-only
history and stays as written (no deletions; the audit trail is the work).

Affected instances (all sympy): 23191, 23262, 24066, 24213, 24909.
