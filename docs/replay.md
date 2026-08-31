# What "replay" means (read this before relying on it)

The product surface is the **run record**: a framed, CRC-protected, RFC 8785 (JCS)
canonically-encoded JSONL log. Replay reads back from it at four honesty tiers, one
per `--level`:

```
substrate replay <record> --level <1|2|3a|3b>
```

- **Level 1 — state reconstruction.** Re-derive any View's state at any sequence.
- **Level 2 — decision reconstruction.** Every runtime decision and resolved input
  is on the record. Level 2 reads them back and re-verifies the input hashes.
- **Level 3(a) — native re-execution.** Re-run the topology with real Producers.
  Precondition-checked (all kinds author-deterministic, replay ceiling `3a`) and
  refuses rather than diverging.
- **Level 3(b) — byte-identical substitution re-execution.** Deferred to post-1.0
  (product amendment A1.1). It needs a replay-mode writer that plays back the
  recorded wall-clock `t` values, which is not built.

## What ships in v1.0

Levels 1, 2, and 3(a). Plus the **D-8 log-equivalence** relation
(`first_divergence` / record diffing): two records are equivalent modulo
supplementary metadata — `t`, run ids, per-run instance ids.

The flagship "byte-identical replay" (Level 3(b)) is post-1.0. Do not rely on
byte-for-byte re-execution in v1.0. Rely on Levels 1, 2, and 3(a) plus D-8
equivalence; the four together cover state reconstruction, decision
reconstruction, provenance, and divergence localisation.

`substrate replay --level 3b` reports the deferral. It never fakes success
silently.
