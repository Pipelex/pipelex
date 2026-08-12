# Deferred: propagate the `Date` / `Time` ISO contract to the docs a model reads

Deferred out of the `fix/Native-date-time` work (PR #1089). Cross-repo and release-gated — not a code defect in `pipelex`, and it does not block that PR. A second deferred item from the same review concerns another repo entirely and is tracked at workspace level.

Background: the fix gave the `Date` and `Time` natives one ISO 8601 contract, owned by `pipelex/core/stuffs/iso_temporal.py` and shared by the content models and `StuffContentFactory`. The natives now accept the **extended** forms only, and refuse the end-of-day `24:00` spelling. See `TODOS.md` in this repo for the full plan and the round-by-round review decisions.

## The authoring guidance still says plain "ISO 8601"

`mthds-plugins/mthds/skills/shared/native-content-types.md` (and its sibling copies in the other plugin targets) describes `Date` and `Time` without mentioning the extended-only rule or the `24:00` refusal.

Why it matters: that file is part of what an LLM is prompted with when authoring or filling these natives, so it is a surface of the same contract the code now pins. A model told only "ISO 8601" can legitimately answer `15:40:00+0200` or `24:00:00` and get a validation error the guidance never warned about. The re-ask loop recovers (workers pass `make_instructor_schema_retrying`, and the error message names the expected shape), so this costs a retry rather than a failed run — which is why it is a sweep, not a fix.

Do it when a released `pipelex` carries the fix, alongside the other release-gated plugin sweeps.

