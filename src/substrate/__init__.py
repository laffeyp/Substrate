"""Substrate — a concurrent streaming dataflow runtime.

You bring computations (Producers) that take typed input and emit a stream of
typed Events; the runtime runs them concurrently, coordinates them through a
single totally-ordered append-only Bus, and creates new Producers dynamically
when Predicates over Views of the log are satisfied (Triggers). All state lives
on the log; the persisted run record is the canonical account of what happened.

Working name "substrate" (B-Q-1 deferred). Public API is re-exported from
`substrate.api`; see the kernel spec (v15), product spec (DRAFT 7), technical
spec (DRAFT 5), and the locked vocabulary at process/signals/0.1.json.
"""

__version__ = "0.0.0"
