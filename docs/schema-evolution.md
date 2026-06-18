# Evolving your event schema

Your topology's event kinds are frozen msgspec `Struct`s declared with a `schema_version`:
`producer_kind(..., schemas=[MyEvent], schema_version=1)`. The on-disk frame records
`schema="<kind>@<version>"`, so every event carries the version it was written under. How to
evolve a kind without breaking the records you already have:

## Additive, non-breaking — keep the version

Adding an OPTIONAL field (one with a default) to a frozen Struct is backward-compatible: old
records decode under the new Struct (the missing field takes its default) and new records carry
the field. You do NOT need to bump `schema_version` for an additive optional field.

```python
class Critique(Struct, frozen=True):
    role: str
    severity: int
    summary: str
    line_refs: tuple[int, ...] = ()   # added later, optional -> old records still decode
```

## Breaking — bump the version

A breaking change — removing or renaming a field, changing a field's type, or making an
optional field required — MUST bump `schema_version` (1 -> 2). New code declares
`schema_version=2`; old records remain readable under their own `@1` schema, because **each run
record is self-describing**: a persistent bus holding runs at different schema versions decodes
each via its OWN `RunStarted` manifest, with no cross-run reinterpretation. v2 code does not
silently reinterpret a v1 record.

## Reserved kinds are not yours to evolve

The `substrate.*` control-plane kinds are the kernel's vocabulary (versioned separately, via the
supervised-proposal taxonomy). A Producer cannot declare or emit them — the prefix is reserved
and enforced at registration and at the emit boundary. Evolve only your own kinds.

## Rule of thumb

Additive-optional → safe, no bump. Anything a v1 reader could misread → bump `schema_version`
and let each record describe itself.
