# What "replay" means (read this before relying on it)

The product surface is the **run record** — a framed, CRC-protected, RFC 8785 (JCS)
canonically-encoded JSONL log. Replay reconstructs from it at four honesty tiers
(`substrate replay <record> --level <1|2|3a|3b>`):

- **Level 1 — state reconstruction.** Re-derive any View's state at any sequence.
- **Level 2 — decision reconstruction.** Every runtime decision and resolved input
  is recorded; Level 2 reads and re-verifies them (input hashes recomputed).
- **Level 3(a) — native re-execution.** Re-run the topology with real Producers;
  precondition-checked (all kinds author-deterministic + replay ceiling `3a`) and
  refuses rather than diverging.
- **Level 3(b) — byte-identical substitution re-execution.** *Deferred to post-1.0*
  (product amendment A1.1): it needs a replay-mode writer that replays recorded
  wall-clock `t` values, not yet built.

## What ships in v1.0

Levels 1, 2, and 3(a), plus the **D-8 log-equivalence** relation (`first_divergence` /
record diffing — two records are equivalent modulo supplementary metadata like `t`,
run ids, and per-run instance ids).

**The flagship "byte-identical replay" (Level 3(b)) is post-1.0** — do not rely on
byte-for-byte re-execution in v1.0; rely on Levels 1/2/3a + D-8 equivalence, which
are sufficient for state/decision reconstruction, provenance, and divergence
localization. (`substrate replay --level 3b` surfaces the deferral explicitly; it
never silently fakes success.)
