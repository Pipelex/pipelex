---
status: active
item: L-260918-941a99
---

# Azure-only model deck — implementation plan

This is the build tracker for [`design.md`](design.md), which holds the decisions and their rationale. The build makes the kit's numbered deck files resolve only to Azure-served models, parks today's files as an unloaded variant guarded by a parity test, and updates the tests, docs and changelog that name the current defaults. It then files the downstream follow-ups this repository cannot fix itself.

## What planning found

Reading the code before writing this plan turned up facts that correct or sharpen the design. The design has been amended where it was wrong, and each amendment is marked below.

**The parked variant cannot live under `pipelex/kit/configs/`, so it moves to `pipelex/kit/deck_variants/multi_provider/`.** Design decision 3 put it at `pipelex/kit/configs/inference/deck_variants/multi_provider/`, but two mechanisms treat everything under `configs/` as a template to install. `ensure_global_config_exists` copies the whole kit configs tree into a new `~/.pipelex/`, recursively and with no skip list (`pipelex/system/configuration/config_loader.py:286-305`), so the parked deck would land in every user's global directory. `check-config-sync` holds this repository's `.pipelex/` to exactly the contents of `pipelex/kit/configs/` (`pipelex/cli/dev_cli/config_sync_exclusions.py`, module docstring), so it would demand a mirrored copy under `.pipelex/inference/deck_variants/`. A sibling of `configs/` avoids both and still ships in the wheel, because hatch packages the whole `pipelex` directory (`pyproject.toml`, `[tool.hatch.build.targets.wheel]`). Design decision 3 is amended to this path.

**The variant must never sit under a `deck/` directory.** The loader collects deck files recursively (`pipelex/cogt/models/model_manager.py:46-57`, `is_recursive=True`), so a variant nested inside `deck/` would be merged into the live deck at boot.

**The removed aliases are referenced downstream, which contradicts decision 8.** The cookbook uses `@best-gemini` in `examples/b_basics/document_extract/extract_slides/bundle.mthds:42` and `examples/b_basics/document_extract/answer_from_documents/bundle.mthds:162`, and names it in that example's `README.md:121`. `mthds-plugins` uses `@best-claude` as its example alias in `skills/mthds-build/references/model-references.md` (and its generated copies), including the command `mthds-agent check-model "@best-claude" --type llm`, which would fail against the new deck. In this repository, user-visible examples name `@best-claude` in the `check-model` argument help (`pipelex/cli/agent_cli/commands/check_model_cmd.py:57`), the syntax table of `pipelex/cogt/models/model_reference.py:9` and a docstring in `pipelex/cogt/models/model_suggestion.py:89`. `pipelex-plugins` and `conformance` reference none of them. The last sentence of decision 8 is amended.

**Only one test depends on what the shipped deck resolves to.** `tests/unit/pipelex/kernel/test_llm_ops_model_resolution.py:13` asserts that `@default-general` resolves to `claude-4.6-sonnet`. The `@best-claude` tests do not depend on the shipped deck: `tests/unit/pipelex/cli/test_check_model_cmd.py` builds its own fake deck (line 44), and `tests/unit/pipelex/cogt/models/test_model_reference.py` only parses the reference syntax. They stay as they are. The many other tests that name Claude, Gemini or `gpt-4o-mini` handles build their own decks or name handles directly in `.mthds` fixtures, so they are unaffected.

**The chosen handles are served from Azure today.** In `pipelex-remote-config` at commit `ae91eb8`, `pipelex_remote_config/remote_config/gateway_models.toml` serves `gpt-6-astra`, `gpt-5.4` and `gpt-5.4-nano` through the Portkey config `pc-openai-6e7576`, whose virtual key is `azure-openai` despite the config's name (`portkey_configs/pc-openai-6e7576.json` beside it). It serves `gpt-image-2` and `gpt-image-1-mini` through `pc-azure-2e01ce`, the Azure REST config, and it serves `azure-document-intelligence`. The same handles exist in `manifold_models.toml` beside it. All of them are also declared in the kit's `backends/azure_openai.toml` and listed in `backends/pipelex_gateway_models.md`.

**The backend lists were refreshed in pipelex v0.61.0, and the remote config followed.** `#1218` added the GPT-5.6 series and GPT-6 Astra to the Azure backend and `#1219` retired the GPT-4.1, o-series and GPT-5 to 5.2 generations; neither touched the numbered deck files, only the commented waterfall example in `x_custom_llm_deck.toml`. The remote config was published from `pipelex-remote-config` commit `ae91eb8` on 2026-09-20 and serves the same roster. Every handle in the design's tables survived both. The premium tier moved up to `gpt-6-astra` once the publish made it gateway-served, and the general and small tiers stay on 5.4 because every 5.6 and 6 handle is fixed-temperature; the design's out-of-scope section records that reasoning.

**The `add-model` skill names `best-claude` as its promotion example.** `.claude/skills/add-model/SKILL.md` (section 7, the deck step) cites `best-claude` beside `default-premium` as an alias a new model might be promoted to. Once the alias is gone the example points at nothing, so it joins the `@best-gpt` rename in Phase 3.

**This repository's own deck manifest is stale, independently of this campaign.** `.pipelex/inference/deck/.kit_manifest.json` records kit version `0.25.1`, and its hash for `1_llm_deck.toml` no longer matches the kit's file. The mirror step in Phase 3 restamps it.

**The deck copies outside this repository** are in `pipelex-server/worker/`, `pipelex-api`, `pipelex-cookbook` (which adds its own `cookbook.toml`), `cocode`, `conformance` and `mthds-ui`, each under `.pipelex/inference/deck/`. The `mthds-ui` hits for old handles are static story fixtures and generated graph specs, not deck lookups.

## Phase 1 — Confirm the handles

This is a short gate before any file changes.

- [x] Check whether Louis's backend update has landed on `dev` (`git log --oneline -- pipelex/kit/configs/inference/backends/`). It has: `#1218` and `#1219`, both in v0.61.0, which this branch contains.
- [x] For each handle in the tables of design decisions 4 and 5 (`gpt-6-astra`, `gpt-5.4`, `gpt-5.4-nano`, `gpt-image-2`, `gpt-image-1-mini`), confirm that it is still declared in `backends/azure_openai.toml` and still served from Azure in `pipelex-remote-config`'s `gateway_models.toml`. All five are, in the backend file, in the catalog at `ae91eb8`, and in the served remote config fetched after the 2026-09-20 publish; `gpt-6-astra` rides the same `pc-openai-6e7576` config as the 5.4 handles, with image and PDF input and structured output. The premium tier was moved from `gpt-5.5` to `gpt-6-astra` on that reading.
- [x] Confirm that `gpt-image-2` still accepts image input (`inputs = ["text", "images"]` and an `input_images` rule), because the `synthesize-ui`, `synthesize-chart` and `gen-image-testing-img2img` presets need it once they move to `@default-premium`. It does, with `input_images = "gpt_image"`.

## Phase 2 — Park today's deck and write the parity test first

The test is written before the Azure deck exists, so it goes red on the aliases the shipped deck still carries, and Phase 3 turns it green.

- [ ] Copy today's numbered files, byte for byte, from `pipelex/kit/configs/inference/deck/` to `pipelex/kit/deck_variants/multi_provider/`. Copy only the numbered files and not the `x_custom_*` templates, which stay single-sourced in the kit (design decision 9).
- [ ] Add `pipelex/kit/deck_variants/README.md`. It should say, in a few sentences, what a variant is, that nothing loads it, that the parity test guards it, and that re-enabling one means swapping its numbered files into `configs/inference/deck/`. It should also warn against placing a variant under any `deck/` directory, because the loader is recursive.
- [ ] Write `tests/unit/pipelex/kit/test_deck_variants.py`:
    - A comparator that takes two `ModelDeckBlueprint`s and the permitted drops, and returns the differences in alias, preset and waterfall names for each family (`llm`, `img_gen`, `extract`, `search`).
    - The permitted drops, written out in the test: `best-claude`, `best-gemini` and `best-mistral` for `llm`, and `best-gemini` for `img_gen`. Each dropped name must be present in the variant and absent from the shipped deck, so an entry that goes stale fails the test.
    - A test parametrized over every directory under `pipelex/kit/deck_variants/`. For each one, it asserts that the numbered filenames match the kit deck's, loads both sets with `load_model_deck_blueprint` (the same loader the runtime uses), and asserts that the comparator reports no differences.
    - A guard that at least one variant exists, so the parametrized test can never pass by running zero cases.
    - Negative tests that feed the comparator a blueprint with an extra preset, a missing alias and a dropped name that is still present, and assert that each is reported. This is the mutation check, written as tests so it runs every time rather than once by hand.
- [ ] Run the new test file and confirm it fails only on the dropped aliases.

## Phase 3 — Write the Azure deck

- [ ] Edit `pipelex/kit/configs/inference/deck/1_llm_deck.toml` according to design decision 4: set the aliases from the table, remove `best-claude`, `best-gemini` and `best-mistral`, and repoint the presets that name a model directly (`retrieval-premium`, `retrieval-cheap`, `engineering-code-cheap`, `engineering-code-cheaper`, and `engineering-codebase-analysis`, which moves from `@best-gemini` to `@default-premium`). Keep every alias and preset name, every temperature and every `reasoning_effort`.
- [ ] Edit `pipelex/kit/configs/inference/deck/2_img_gen_deck.toml` according to design decision 5: set the aliases, remove `best-gemini`, and repoint the presets that name `nano-banana-pro` to `@default-premium`.
- [ ] Leave `3_extract_deck.toml` and `4_search_deck.toml` untouched (design decision 6).
- [ ] Mirror the kit into this repository's `.pipelex/inference/deck/` with `.venv/bin/pipelex update --local --yes --no-backup`. That command copies the numbered files and restamps `.kit_manifest.json`, which also clears the pre-existing staleness. Then run `make check-config-sync`.
- [ ] Run the parity test and confirm it passes.
- [ ] Change `tests/unit/pipelex/kernel/test_llm_ops_model_resolution.py:13` to expect `gpt-5.4`.
- [ ] Replace `@best-claude` with `@best-gpt` in the user-visible examples: `check_model_cmd.py:57`, `model_reference.py:9`, `model_suggestion.py:89` and the promotion example in `.claude/skills/add-model/SKILL.md` (section 7). If a CLI help snapshot changes as a result, regenerate it.
- [ ] Run `make tb` to test the boot sequence against the new deck, then `make agent-check`, then the touched test modules.

### Checkpoint A — the deck is in place

Record here the SHA the deck landed in, any handle substituted in Phase 1 and why, and anything the checks reported that was not anticipated above. Open questions go here too. The next phase is documentation only and can start in a fresh session from this record.

- [ ] Run `/rev` on the deck change before the docs phase starts, and record the pass here.

## Phase 4 — Docs and changelog

- [ ] Update the pages that state what the deck resolves to by default:
    - `docs/get-started/configure-ai-providers.md`: this is the one place that states the Azure scope, meaning language models, image generation and document extraction are served from Azure while web search stays on Linkup (design decision 6).
    - `docs/configuration/config-technical/inference-config.md`.
    - `docs/configuration/config-technical/inference-backend-config.md`: its deck example lists `best-claude` and `best-gemini` (around lines 472-486).
    - `docs/building-methods/configure-ai-llm-to-optimize-methods.md`: its alias list (lines 30-32) was already stale, naming `claude-4.1-opus` and `gemini-2.5-pro`.
    - `docs/building-methods/pipes/pipe-operators/PipeImgGen.md:65`, which lists `best-gemini`.
    - `docs/tools/cli/update.md`, only if it describes what an update run reports in a way this change alters.
- [ ] Review the other pages that name the affected aliases or handles: `docs/under-the-hood/reasoning-controls.md`, `per-node-usage-attribution.md`, `test-profile-configuration.md`, `docs/features/validation-dry-run.md`, `docs/cookbook/generate-image.md`, `PipeLLM.md` and `PipeStructure.md`. Change only statements about what a name resolves to by default. A handle used as an explicit example of naming a model stays.
- [ ] Follow the MkDocs rule of a blank line before every list.
- [ ] Add a `CHANGELOG.md` entry under `[Unreleased]`, `### Changed`, marked Breaking and written in the condensed form: the default aliases and presets now resolve to Azure-served models (with the tiers named), and `best-claude`, `best-gemini` and `best-mistral` (and `best-gemini` for image generation) are removed. For migration, `pipelex update` refreshes the numbered deck files and backs up any that were edited locally, and a project that wants a removed alias back defines it in `x_custom_llm_deck.toml`, or in an `x_custom_*` file for image generation.

## Phase 5 — Verify, review, and file the follow-ups

- [ ] Re-read the handles against `pipelex/kit/configs/inference/backends/` in case the backend update landed during the build, and adjust both the deck and the design's tables if it did.
- [ ] Run `make agent-check` and `make agent-test`.
- [ ] Run a live smoke check through the gateway, limited to a few inference-marked tests that ride the default tiers: one LLM text case with no model named, one structured case, one vision case and one `$gen-image` case (`.venv/bin/pytest --pipe-run-mode live -m inference -k <names> -x`). The goal is to see gpt-6-astra, gpt-5.4 and gpt-image-2 answer. A fixed-temperature warning is expected and accepted.
- [ ] Run `/rev` on the branch before the pull request opens.
- [ ] File the downstream follow-ups in the ledger, each `--discovered-from L-260918-941a99` and blocked on the pipelex release that carries this change:
    - `pipelex-cookbook`: replace `@best-gemini` in the two extract bundles and the `answer_from_documents` README, run `pipelex update` at the pin bump, and check `cookbook.toml`'s direct model names against the Azure scope.
    - `mthds-plugins`: change the example alias in the `model-references.md` source, not in its generated copies, from `@best-claude` to `@best-gpt`.
    - `pipelex-server`, member `worker/`: run `pipelex update` in the worker's `.pipelex/` at the pin bump. Its numbered files match the kit byte for byte today, so the update should apply cleanly.
    - `pipelex-api`: run `pipelex update` at the pin bump.
    - `cocode`, `conformance` and `mthds-ui` get no item. The stale-deck notice prompts them on their next pin bump, and none of them references a removed alias.
- [ ] Open the pull request against `dev` as `feature/Azure-only-deck · L-260918-941a99`, with `Closes L-260918-941a99` in the body.

## Decisions taken during planning

- **The variant lives at `pipelex/kit/deck_variants/multi_provider/`**, for the reasons in the first finding above. The design is amended.
- **The `@best-claude` tests that build their own deck are left alone.** They test syntax and suggestion logic, not the shipped vocabulary, and nothing about them becomes false.
- **The mutation check is written as permanent negative tests of the comparator** rather than as a one-off hand edit, so the guard's ability to go red is checked on every run.
- **Only the numbered files are parked.** The `x_custom_*` templates are not part of the managed deck, and a second copy of them would only drift.
