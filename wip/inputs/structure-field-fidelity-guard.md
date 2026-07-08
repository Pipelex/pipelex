# Deferred: `date`/`datetime` structure fields don't carry the native Date fidelity guard

**Status:** deferred design note — no code change. Surfaced during the Date-track PR #1029 adversarial review, 2026-07-07.

## What the reviewer flagged

The native `Date` concept is deliberately fidelity-strict: `DateContent._reject_lax_temporal` closes pydantic's lax-mode coercions that would silently corrupt data — a bare `int`/`float` or an all-digit string read as epoch seconds (DT6), a `datetime` on the `date` field truncated to drop its time and offset (DT3), no invented midnight (DT2).

DT8's severable field-type fix (`type = "date"` → `datetime.date`, `type = "datetime"` → `datetime.datetime`) generates **plain** pydantic `date`/`datetime` fields on user-defined structure classes. Those generated fields have **no** equivalent guard, so pydantic's lax coercion applies there:

- a `date` string into a `datetime` structure field silently becomes a midnight `datetime` (an invented time),
- a midnight-epoch int into a `date` structure field silently becomes that calendar date.

So the fidelity guarantees the native concept enforces are not enforced on user structure fields.

## Why this is a decision, not obviously a bug

- **Different surfaces, different contracts.** The native `Date` concept exists specifically to enforce document-fidelity. A user-defined structure field of `type = "date"` is an ordinary pydantic field on an arbitrary model — a more permissive surface. DT8's scope was the *type misnomer* (a `date` field should not force a time), explicitly **not** porting the native concept's anti-fabrication guard to every generated temporal field.
- **Porting the guard is broad and opinionated.** Making all generated `date`/`datetime` fields strict would change how every extraction into such a field behaves and could break pipelines that today rely on lax coercion (e.g. an LLM emitting a date string into a `datetime` field). That is a runtime-behavior change with a wide blast radius, not a local fix.

## Follow-up to consider

Decide, when structure-field temporal handling is revisited, whether to:

1. Leave structure fields permissive (document that only the native `Date` concept is fidelity-strict) — the likely intended non-goal; or
2. Emit a shared before-validator (or use pydantic strict / `Annotated` types) on generated `date`/`datetime` fields mirroring `DateContent._reject_lax_temporal`, so the native concept and structure fields behave consistently.

If (2), factor `_reject_lax_temporal` into a reusable validator so the two surfaces cannot drift. Related notes: `container-default-temporal-codegen-gap.md`.

No action needed inside the Date track.
