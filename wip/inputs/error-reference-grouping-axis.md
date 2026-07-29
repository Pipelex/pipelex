# Deferred: the error reference groups by module path, and runtime errors under `core/` land in "Authoring & language"

**Raised:** 2026-07-29, during the `refactor/Layer-boundary` checkpoint review. **Not a regression introduced by that branch** — it is a pre-existing property the branch made visible.

## What was observed

`error_pages_generator.py`'s `_SUBSYSTEM_SECTIONS` keys each error class on the **second dotted segment of its defining module** (`pipelex.<subsystem>.…`), and maps `core` → "Authoring & language". That is right for most of `core/`, which is the value data model and the language's own vocabulary.

It is not obviously right for the run-failure errors that live under `core/pipes/inputs/`. `PipeRunInputsError` and `OptionalValueAbsentError` are raised *while a method runs* — `OptionalValueAbsentError` is literally a data-dependent runtime failure, `error_domain = RUNTIME` — yet the public error reference files both under **Authoring & language / Core language**. Moving `PipeRunError` to `core.pipes.exceptions` put the base class beside them, which is an improvement in consistency (the base and its two subclasses are now in one section instead of two) but does not answer whether that section is the right one for any of the three.

## Why it was left alone

- Nothing about it is *new*. Both subclasses have been filed this way since they were written; the branch only stopped the base from being filed somewhere else.
- The alternatives are all bigger than the problem. Adding a per-class section override introduces a second, hand-maintained grouping axis that will drift from the module one. Re-keying on `error_domain` instead of the module path changes the section of every error class in the reference at once. Splitting the run-failure errors out of `core/pipes/inputs/` moves code to satisfy a docs grouping, which is the tail wagging the dog.
- The grouping axis is documented and deliberate: the generator's comment says the subsystem key "groups errors by the area of the codebase they originate from", and by that stated rule the current output is *correct*. The open question is whether that rule is the one a reader of the error reference wants, which is a product question, not a bug.

## What to decide, if this is ever picked up

Does the public error reference group by **where the error lives** (today's rule — stable, mechanical, needs no curation) or by **when the user hits it** (authoring vs running — more useful to a reader, but needs a second manifest and a way to keep it honest)? If the answer is the second, the honest implementation is probably `error_domain`, which already exists on every class and is already load-bearing for HTTP status mapping — not a new hand-maintained list.

Note the related hazard already recorded twice in `wip/drift-contracts/dogfood-log.md`: because the key is the *second segment*, any package move silently reclassifies every error class in it, with `make gep` exiting 0 either way. That is the same mechanism, and it is worth fixing (or gating) independently of the grouping-axis question.
