# Deferred: propagate the `Date` / `Time` ISO contract to the docs a model reads

Deferred out of the `fix/Native-date-time` work (PR #1089). Both items are cross-repo and release-gated — neither is a code defect in `pipelex`, and neither blocks that PR.

Background: the fix gave the `Date` and `Time` natives one ISO 8601 contract, owned by `pipelex/core/stuffs/iso_temporal.py` and shared by the content models and `StuffContentFactory`. The natives now accept the **extended** forms only, and refuse the end-of-day `24:00` spelling. See `TODOS.md` in this repo for the full plan and the round-by-round review decisions.

## 1. The authoring guidance still says plain "ISO 8601"

`mthds-plugins/mthds/skills/shared/native-content-types.md` (and its sibling copies in the other plugin targets) describes `Date` and `Time` without mentioning the extended-only rule or the `24:00` refusal.

Why it matters: that file is part of what an LLM is prompted with when authoring or filling these natives, so it is a surface of the same contract the code now pins. A model told only "ISO 8601" can legitimately answer `15:40:00+0200` or `24:00:00` and get a validation error the guidance never warned about. The re-ask loop recovers (workers pass `make_instructor_schema_retrying`, and the error message names the expected shape), so this costs a retry rather than a failed run — which is why it is a sweep, not a fix.

Do it when a released `pipelex` carries the fix, alongside the other release-gated plugin sweeps.

## 2. `pipelex-app`'s date-format note documents a runtime model that is already false

`pipelex-app/src/lib/run-form/date-format.ts` states in its header — explicitly as "measured, not assumed" — that pydantic accepts `"2026-07-06T00:00:00Z"` for `native.Date`'s `date` field. It does not: the datetime-shaped-string guard on `DateContent.date` rejects it, and rejected it before this PR too.

No wire impact, and nothing to fix in behavior: `asCalendarDate` normalizes to a bare `YYYY-MM-DD` before sending, and the app emits no time-of-day values at all. This is a stale comment that predates the branch. Correct it the next time that file is touched.
