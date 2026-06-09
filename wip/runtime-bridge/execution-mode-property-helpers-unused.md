# `PipelexExecutionMode` property helpers — tested but not yet consumed

**Status:** deferred follow-up (not a bug). Intentionally kept as a tested, intention-revealing surface; wiring them into `bridge.py` (or removing them) is a follow-up. Migrated here from the PR #969 reviewer's guide (`TODOS.md`) when that file was retired at merge — it was the only live item in that guide not already recorded under `wip/`.

## What

`PipelexExecutionMode` (`pipelex/runtime_bridge/execution_mode.py`) exposes three `@property` helpers:

- `requires_pipelex_temporal` — True for `TEMPORAL_BLOCKING` / `TEMPORAL_FIRE_AND_FORGET`.
- `requires_mistral_workflows_extra` — True for `MISTRAL_NATIVE`.
- `is_fire_and_forget` — True for `TEMPORAL_FIRE_AND_FORGET`.

They are covered by `tests/unit/pipelex/runtime_bridge/test_execution_mode.py`, but **`bridge.py` does not consume them** — it inlines the equivalent `match` / identity checks at each dispatch and validation site instead.

## Why it's on file, not fixed

The helpers were written as the intention-revealing form of the mode predicates, ahead of `bridge.py` being refactored to call them. Keeping them tested-but-unused is a deliberate, low-risk surface (the `match` bodies are exhaustive, so the linter guards them if a mode is added), not a silent gap. There is no behavioural bug: the inlined checks in `bridge.py` and the helpers agree.

## Follow-up (pick one when next touching the bridge)

- **Wire them in** — replace the inlined predicates in `bridge.py` (`_validate_input`'s fire-and-forget guard, the per-mode extra-dependency guards) with the helpers, so the predicate lives in one place. Lowest-churn, removes the duplication the reviewer flagged.
- **Or remove them** — if `bridge.py`'s `match execution_mode:` dispatch stays the single source of truth and the helpers earn no second caller, delete them with their tests.

Not urgent either way; no correctness impact.
