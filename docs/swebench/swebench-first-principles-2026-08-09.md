# What SWE-bench is, and what is wrong with what we are doing

2026-08-09.

## The object

An SWE-bench instance is one tuple scraped from a public GitHub repo:

    (repo, base_commit, issue_text, source_patch, test_patch,
     FAIL_TO_PASS_ids, PASS_TO_PASS_ids, problem_statement, version)

`source_patch` is the human fix. `test_patch` is the tests the fix ships with.
The solver sees the repo at `base_commit` and the issue. It must produce a
source patch. The harness applies the solver's patch + the test patch, runs
the tests, and grades pass iff every FAIL_TO_PASS test now passes AND every
PASS_TO_PASS test still passes.

Every instance is a real bug a real developer fixed. Not synthetic. Real
Python, real repos: Django, Flask, sympy, scikit-learn, matplotlib, astropy,
sphinx, requests, xarray, pylint, pytest.

## Lite vs Verified

Lite is 300 instances selected mechanically from the full 2,294 by patch
shape: ≤1 file, ≤3 hunks. Small and fast to run. No human review. Contains
instances where a FAIL_TO_PASS test already lived in the base repo — a
solver could grep for it. That is the leakage class we have spent this
morning writing parsers to detect and exclude.

Verified is 500 instances human-curated by trained software engineers under
Princeton, OpenAI, and Anthropic. Each was reviewed for: is the problem
statement clear, are the tests appropriate (neither too specific to the
reference solution nor underspecified), is the setup reproducible. Instances
failing any check were dropped. Verified was created specifically to remove
the leakage and ambiguity Lite carries.

## What is wrong with what we are doing

Three things.

**Wrong benchmark.** We chose Lite. Lite has leaks. We wrote firewall
parsers to route around the leaks. That parser code exists only because we
picked the dirty split. Verified was made for exactly this class of run.

**Wrong error posture.** The substrate kernel halts on `ProducerFailed`.
Our topology producers wrap every model call in `try / except` and swallow
the exception, emitting an empty artifact. That defeats the kernel's own
halt. Under a 429 storm from Ollama Cloud, half the calls failed silently
and the runner produced a "result." The right rule: any error stops the
sweep. Death-resilience was a well-meaning compensation and it turned every
systemic failure into a null number that looked like data.

**Wrong theoretical grounding.** We built a firewall because Lite is dirty.
We built death-resilience because model calls flake. Both are compensations
for the wrong choices upstream. A validation run of the substrate machinery
should not need either. Use a clean benchmark. Let errors halt. If the
machinery cannot complete a clean run, the machinery is not ready to
measure anything, and that is the honest signal.

## What this run is actually for

Proof the pipeline runs end-to-end on real inputs. Not a resolve-rate
number. A demonstration: cases prepare, the topology executes, cells write,
the report generates. That is the whole ask. The rate-limit contamination
in v4 masqueraded as a result. v5 was going to reproduce the same failure
mode with a smaller concurrency knob. Neither is what we need.

The rewrite: switch to Verified. Rip out the firewall pre-filter and every
producer's `try / except` swallow. Let the kernel halt on the first real
error. Run enough cases to prove the machinery works; do not chase a
number.
