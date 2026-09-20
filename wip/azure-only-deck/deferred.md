---
status: active
item: L-260918-941a99
---

# Deferred findings — Azure-only deck

Findings raised during this campaign's reviews that are real but outside its scope. Each says what was seen, why it was not done here, and what doing it would involve.

## Two inference error classes now have no raise site

`LLMSettingsValidationError` (`pipelex/cogt/exceptions.py:251`) lost its only raise site when this campaign deleted `ModelDeck.final_validate` and its `_validate_llm_setting` helper — the dead validator that would have rejected the Azure deck's premium tier. `ImgGenSettingsValidationError` (`:255`) was already in that state before this campaign and has no raise site anywhere in the tree either.

Both are still part of the documented error surface: `docs/errors/llm-settings-validation-error.md` and the generated identity snapshot carry them, and consumers outside this repository branch on `error_type`. Removing a class is therefore a wire change, needing `pipelex-dev generate-error-identity` and `generate-error-pages` and a changelog entry of its own, which is a different piece of work from shipping a deck.

**Verified**: `grep -rn 'LLMSettingsValidationError' --include='*.py'` returns only the class definition; the same for `ImgGenSettingsValidationError`.

**To do it**: decide whether the inference-settings validation these two named is coming back in some form. If it is not, delete both classes, regenerate the error identity and the error pages, and note the removed `error_type` values in the changelog as a breaking change for anyone branching on them.

## An offline boot can fail on a remote-config cache that predates `gpt-6-astra`

Raised by the Codex adversarial reviewer in round 3 and confirmed by the round's verifier. The cache at `~/.pipelex/cache/remote_config.json` carries `CACHE_SCHEMA_VERSION = 1` (`pipelex/system/pipelex_service/remote_config_cache.py:31`) with no TTL and no keying on the remote-config URL version, so a cache primed before `gpt-6-astra` was published stays valid and is served verbatim. `pipelex update` copies clean-behind deck files with `shutil.copy2` (`pipelex/cli/commands/update_cmd.py:156-159`) and never touches the cache. When the next boot cannot reach the network, `fetch_remote_config` falls back to that cache and returns `source=CACHED` rather than `None`, so `ModelManager._enforce_gateway_model_membership` runs and raises `GatewayUnknownModelError` at `model_manager.py:186` on the promoted handle.

It was not fixed here because the failure is loud rather than silent: the error names the handle, the backend and the config source, and `handle_gateway_unknown_model_error` prints two remediations, either of which clears it permanently — one online boot, or disabling the gateway backend. It also needs an offline boot and a pre-publication cache together. At round 3's `necessity` bar that is not ship-blocking, but it is the sharpest finding this campaign drew.

**Why no test catches it**: `tests/e2e/agent_cli/test_offline_run_dry.py` synthesises its cached payload *from the shipped kit deck*, and `test_primed_cache_specs_track_kit_deck_premium_alias` asserts that property deliberately. Every promoted handle is therefore present by construction, so no offline test can ever exercise version skew.

**To do it**: validate a candidate deck against the available cache before applying it, and refuse the update while preserving the current deck when a required handle is unavailable — or serve a fallback handle compatible with older caches. Either way it needs an end-to-end upgrade test built on a cache primed before the deck moved, which the current fixture design cannot express.

## Naming a premium alias directly in a pipe warns on every call

Raised by the Codex review pass in round 3 and confirmed by the round's verifier. `ModelDeck.get_llm_setting` resolves an alias by pairing its target with the deck-wide default temperature (`pipelex/cogt/models/model_deck.py:322-325`), which the shipped deck sets to 0.5. Because the premium tier now resolves to a model carrying `fixed_temperature = 1`, `_apply_constraints` overrides the value and logs a warning (`pipelex/cogt/llm/llm_worker_abstract.py:358-365`) from the per-job path, with no memoisation — once per call.

This is the corner the round-2 pass did not sweep when it set the twelve conflicting presets to temperature 1. The presets are covered; the alias path is not, and the shape is reachable from our own documentation, which teaches `model = "@default-premium"` inside a pipe at `docs/building-methods/pipes/pipe-operators/PipeStructure.md:123`.

**To do it**: decide where the constraint should be applied. Resolving an alias through the target model's `valued_constraints` at deck-build time is the direct fix, but it moves constraint knowledge into the deck layer; the alternative is to keep the override where it is and dedupe the warning per model. The choice belongs with whoever owns the resolution path, not with a deck change.

## `check-gateway-models` can never report drift

Found by the round-3 verifier while establishing how the gateway catalog listings had gone stale since 2026-07-27. `make check` runs `update-gateway-models-quiet` and then `check-gateway-models` in the same target, so the checker validates output the same target has just rewritten and cannot fail. `check-gateway-models` is not in `make agent-check` at all, so an agent never runs it even in the form that could report something.

That is why the listings drifted for months with every gate green, and why round 3 had to regenerate them by hand. It was not fixed here because it is a Makefile-wiring question about the drift regime rather than a deck change.

**To do it**: separate the two — either drop the regeneration from `make check` and let the checker speak, or move the checker into `make agent-check` in a form that reads the committed files rather than freshly generated ones.

## Whether large-codebase analysis belongs on the premium tier

Raised by the official code review in round 3. `engineering-codebase-analysis` now resolves to `@default-premium` (`gpt-6-astra`, input 10.0 / output 50.0, temperature fixed at 1) where the deck's own `default-large-context-code` alias resolves to `gpt-5.4` (input 2.5 / output 15.0, no fixed temperature) and is reached by no preset, no waterfall and no choice default.

The reviewer read this as an unremarked side effect of the sweep, and the verifier refuted that reading: `design.md` decision 4 names the repointing explicitly and `plan.md` Phase 3 repeats it as an instruction, and it was forced, since `best-gemini` is one of the provider-named aliases decision 8 removes. The alias was equally unreachable on `origin/dev`, where the preset reached its model through `@best-gemini`. So the framing is rejected and the design question is what remains: the preset's description is still "Large codebase analysis", the alias exists for exactly that job, and the cost and determinism deltas are real.

**To do it**: decide whether `engineering-codebase-analysis` should name `@default-large-context-code`, and if not, whether that alias should exist at all — an alias nothing reaches is never exercised by the boot-time membership check (`_collect_deck_referenced_handles` walks presets and choice defaults only, by design), so it can rot silently either way.

## Unverified deferrals from round 3

These were raised by reviewers and sorted as deferrals without being sent to the verifier, because at the round's bar they would not have been fixed whatever the verdict. Each rests on the reviewer's word alone.

**Unverified — preset descriptions no longer describe distinct presets** (cubic, and independently the official code review). `writing-factual` ("high accuracy") and `writing-creative` ("high variability") both resolve to `@default-premium` at temperature 1 and would issue identical calls; `engineering-structured`, `vision-diagram` and `vision-table` likewise lost the parameter their descriptions imply. These descriptions surface through `check-model` and the docs, so a reader choosing a preset by its description may be misled. The tier move itself was ratified at Checkpoint A, so what is open is whether the descriptions should be rewritten or the presets given distinct targets.

**Unverified — the parked variant ships to every install** (cubic). `get_kit_deck_variants_dir` is a public kit API whose only caller is the parity test, and the hatch wheel includes all of `pipelex/`, so `deck_variants/` reaches every install although the README states nothing loads it. Resolving the variants root inside the test, or excluding the directory from the wheel the way `pipelex/cli/dev_cli` is excluded, would keep the runtime surface to what the runtime uses.

**Unverified — nothing gates a preset against its model's fixed temperature** (official code review). Deleting `final_validate` removed the only code that could have caught the conflict this campaign had to find in review and fix by hand, and the boot-time membership check does not look at temperature. The next deck edit pointing a preset at a fixed-temperature model would reintroduce the warning storm with no gate going red. A unit test over the shipped deck, asserting each preset's temperature is compatible with its resolved model's `valued_constraints`, was the reviewer's suggestion. See also the entry above on the two error classes left with no raise site, which is the other half of that deletion.

**Unverified — the variant parity guard is blind to choice defaults** (official code review). `extract_vocabulary` reads aliases, presets and waterfalls, and `extract_model_handles` collects from alias targets, waterfall entries and preset models, so `[llm.choice_defaults]` and the img-gen, extract and search choice defaults are invisible to both halves of the guard. A variant whose choice default named a retired handle, or diverged from the shipped deck, would pass every assertion.

**Unverified — the retirement check reads backends the variant would never route through** (official code review). `list_declared_backend_handles()` unions the top-level tables of every `backends/*.toml`, including backends disabled by default and the bulk third-party catalogs. A handle retired from every backend the variant actually uses still passes as long as one unused file mentions it, which weakens what the README advertises as the way a parked deck goes stale.

**Unverified — image fixture generation runs on the premium tier** (official code review). `gen-image-testing-img2img`, `synthesize-ui` and `synthesize-chart` were repointed to `@default-premium` (`gpt-image-2`, input 8.0 / output 30.0) and declare no `quality`, so they fall to the default on the most expensive image model in the deck. `gpt-image-1-mini` declares the same image inputs and would satisfy the img2img requirement these presets exist for.
