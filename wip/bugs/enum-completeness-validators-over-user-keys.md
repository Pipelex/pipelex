# Completeness validators over user-supplied keys turn an enum addition into a boot failure

**Status:** confirmed defect, not yet fixed. Found 2026-08-15 while re-arguing Migrator ruling R8 (`wip/migrator-3/README.md` at the workspace root); recorded there as a deferred finding the migrator can *name* but not *fix*, because the fix is a model-design change in this repo, not a gate change. Filed here so it rides the migrator worktree and branch and gets its own pull request when someone picks it up. It is not on the Migrator v3 critical path.

## Problem

Two configuration fields are open mappings keyed by the **user's** names, and each carries a validator that demands **every member of an enum** as a key of every entry:

| Field | Type | Keyed by | Validator | Enum |
|---|---|---|---|---|
| `LLMConfig.effort_to_budget_maps` (`pipelex/cogt/config_cogt.py`) | `dict[str, EffortToBudgetMap]` = `dict[str, dict[str, int]]` | reasoning family (`anthropic`, `gemini`, …) | `validate_effort_to_budget_mapping` — raises `ConfigValidationError("Missing reasoning effort levels …")` | `ReasoningEffort` (`none minimal low medium high xhigh max`) |
| `ImgGenConfig.quality_to_steps_maps` (same file) | `dict[str, QualityToStepsMap]` = `dict[str, dict[str, int]]` | image model (`flux`, `sdxl_lightning`, `qwen_image`, …) | `validate_quality_mapping` — raises `ConfigValidationError("Missing quality levels …")` | `Quality` (`low medium high`) |

Both validators run on the **merged** configuration (`PipelexConfig.model_validate` after every tier is deep-merged), so the rule applies to whatever the user ends up with, packaged defaults included.

**The failure.** A user has a hand-authored override — say `~/.pipelex/pipelex_override.toml` or a project `.pipelex/pipelex.toml` — that adds a map for a family or model the packaged defaults do not know:

```toml
[cogt.llm_config.effort_to_budget_maps.my_finetune]
low = 512
medium = 2048
high = 8192
```

That file is valid today only if it names all seven efforts. It is complete on the day it is written. Then a release adds a member to `ReasoningEffort` — which happened on 2026-04-16 when `XHIGH` arrived (`cdabd29a8`), with `pipelex/pipelex.toml` updated in the same commit — and the user's next boot fails with `Missing reasoning effort levels in mapping: {'xhigh'} for target 'my_finetune'`. Nothing in the packaged defaults can rescue them: `deep_update` (`pipelex/tools/misc/json_utils.py`) merges recursively into keys the target *already has*, and the packaged file has no `my_finetune` key to merge beneath.

Users who override a **known** family (`anthropic`) with a sparse map are fine — the deep merge recurses into the packaged `anthropic` dict and the packaged `xhigh` survives. The seeded `~/.pipelex/pipelex.toml` is fine — the kit template (`pipelex/kit/configs/pipelex.toml`) does not carry either map. So the population hit is exactly the users who did the customization the open mapping invites: **their own model, their own family.**

The packaged defaults already pay for the rule in-repo. `pipelex/pipelex.toml:194` reads `none = 0      # Required by validator; unreachable at runtime (level map gates NONE as disabled before budget lookup)` — a dead entry that exists to satisfy the completeness check.

## Why the migration gate cannot catch it, and why that matters

The Migrator's coverage gate (`pipelex/migration/coverage.py`, Phase 1, on `dev` since `052b9df06`) diffs a fingerprint of the schema. It records `effort_to_budget_maps.*.*` as a bare `int` under two wildcard segments — the keys are `str`, so no enum appears on that path. `ReasoningEffort`'s only footprint in the config tree is elsewhere, where an added member is correctly classified as **additive → regenerate the golden, no bump, no entry**. So the gate is green, the changelog says nothing about migration, and the customized user's file breaks. This is the same failure family as value-domain narrowing (R8) — a change the schema calls additive that a validator makes breaking — and it is the case no fingerprint of any shape can see, because the narrowing lives in Python, not in the type.

The asymmetry with the *removal* direction is what makes the "missing" branch the wrong half of the validator. If a member were **removed** from `ReasoningEffort`, the "invalid" branch would fire on old keys — but the migrator can repair that with one wildcard op in the ledger (`delete_key` at `["cogt","llm_config","effort_to_budget_maps","*"]`, key `xhigh`), because removing a key from a user's file is structural. **Adding** a member cannot be repaired by any op in the vocabulary — the migrator will not materialize a value into a user's file, and there is no right value to materialize (a budget for the user's own family is the user's to choose). So the addition direction is exactly the one that must not break the boot.

## Proposed fix

**Drop the "missing" branch of both validators; keep the "invalid" branch.** The invalid branch is a typo guard and stays. Completeness stops being a boot-time invariant and becomes what it already is at the point of use:

- `get_reasoning_budget` already raises `ConfigValidationError("No budget found for reasoning effort '…' and reasoning family '…'")` on a miss.
- `get_num_inference_steps` already raises `ConfigValidationError("No number of inference steps found for quality '…' and model '…'")` on a miss.

That moves the failure from *every boot, for everyone with a custom key* to *the one call that asks for the missing level, for the one user who omitted it* — later, narrower, and with a message that names the exact key. It also retires the dead `none = 0` entry and its apologetic comment in the packaged file.

**Optionally, on top:** a reserved fallback key so a sparse per-family map is a first-class shape rather than a latent runtime error — `effort_to_budget_maps.default` consulted when the family's map lacks the level. That is a small feature, not part of the bug fix, and it should be its own decision (it reserves a name in the user's key space, which the ledger contract would want recorded).

Not proposed: retyping the inner map as `dict[ReasoningEffort, int]`. It reads better but changes nothing here — the migration fingerprint treats any mapping as an open node and records only the value schema, so the enum would still be invisible on that path, and the completeness rule would still be a validator.

## Test shape

`tests/unit/pipelex/cogt/llm/test_llm_config_reasoning.py` already pins the current behaviour and flips:

- `test_validator_missing_effort_level_raises` → becomes `test_validator_accepts_partial_map`: a map for a custom family carrying a subset of the levels validates.
- `test_validator_invalid_effort_level_raises` and `test_validator_missing_and_invalid_effort_levels_raises` → the invalid half stays red; the combined case now reports only the invalid keys.
- New: `get_reasoning_budget` on a family whose map lacks the requested level raises at lookup with the level and family in the message (this is existing behaviour, now the only line of defence, so it deserves its own assertion).
- Same three shapes for `ImgGenConfig` / `Quality` — there is no test file for `validate_quality_mapping` today; add one beside the LLM one.
- One boot-shaped test: layered TOMLs (packaged defaults + a temp override carrying `[cogt.llm_config.effort_to_budget_maps.my_family]` with a subset) → `PipelexConfig` validates. This is the user's actual situation, and it is the case the unit tests above do not cover because they build the model directly.

## Where it touches the Migrator

Nothing in `pipelex/migration/` changes. What the migrator does with this finding is *declare* it: R8 adds one sentence to the fingerprint section of `docs/migration-ledger.md` saying that domain narrowing expressed in a validator is not visible from the schema and stays the author's responsibility, and Phase 3's `config-docs` drift-contract `review` list gains the validator sites so a reviewer sees them on every config-docs run. This doc is the fix on the model side, and it can land in either order.

## Note on the reshape

The configuration reshape (`wip/migrator-3/reshape.md`) moves both fields — `cogt.llm_config.effort_to_budget_maps` → `inference.llm.effort_to_budget_maps`, `cogt.img_gen_config.quality_to_steps_maps` → `inference.img_gen.quality_to_steps_maps` — and does not touch the validators. Whoever fixes this should land it as its own small pull request against `dev`, and rebase across the reshape when it merges; the two changes do not conflict in substance, only in path names.
