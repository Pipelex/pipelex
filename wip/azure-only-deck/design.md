---
status: draft
item: L-260918-941a99
---

# Azure-only model deck — design

The kit's default model deck resolves to models from several providers: Anthropic for the general and premium tiers, Google for the small vision and creative tiers and the large-context tiers, OpenAI for the small tier, Google again for image generation. This campaign makes the shipped deck resolve exclusively to the models the Pipelex Gateway serves from Azure: the OpenAI language and image models, and Azure Document Intelligence for document extraction. Today's multi-provider deck stays in the codebase, unloaded, and cannot drift from the shipped one.

**Scope.** What the deck resolves to by default in real use, when a method names a preset or an alias, or names nothing at all. Not the test profiles, which keep naming Anthropic and Google handles so the runtime's support for those providers stays tested. Not routing: the Gateway already serves every OpenAI model from Azure through the same SDK, so nothing about where a request goes changes here.

## How the deck works today

The kit ships one deck directory, `pipelex/kit/configs/inference/deck/`, holding the numbered files (`1_llm_deck.toml`, `2_img_gen_deck.toml`, `3_extract_deck.toml`, `4_search_deck.toml`) and the two `x_custom_*` templates. `pipelex init` copies the directory into the project's `.pipelex/inference/deck/` and stamps `.kit_manifest.json` with the kit version and a hash per numbered file (`pipelex/cogt/models/deck_manifest.py`). At boot, the loader reads every `*.toml` in the installed directory in sorted order and deep-merges them into one `ModelDeckBlueprint` (`pipelex/cogt/models/model_manager.py`, `pipelex/cogt/models/model_deck_loader.py`). `pipelex update` and `pipelex doctor` diff the installed numbered files against the kit's by hash and never touch `x_custom_*` files. Nothing in the kit, the loader or the manifest knows of more than one deck.

The deck is a vocabulary. Methods, the cookbook, the test bundles and the authoring skills reference aliases (`@default-premium`) and presets (`$writing-factual`, `$engineering-code`), never a provider. Most presets resolve through an alias; a handful name a model handle directly (`retrieval-cheap`, `retrieval-premium`, `engineering-code-cheap`, `engineering-code-cheaper`, and the `synthesize-*` and image-to-image testing presets in the image deck). The model handles are the only provider-specific content in the deck.

## Decisions

### 1. The alias and preset vocabulary is the contract; the handles are the edition

Every alias and preset name in the shipped deck keeps its name. Only what each name resolves to changes. Nothing downstream needs an edit: the sweep of the tests, the cookbook, `mthds-plugins` and `pipelex-plugins` found them referencing names, not models. The one deliberate exception is decision 8.

### 2. The Azure deck is the kit's one shipped deck

The numbered files under `pipelex/kit/configs/inference/deck/` become the Azure deck, under the same filenames. `init`, `update`, `doctor` and the manifest keep working unchanged.

An edition selector (an `init` flag, an `edition` field in the manifest, and `update` and `doctor` reading it to pick the kit directory to diff against) was considered and declined for now. It is a change at several sites for a switch nobody flips yet. If a second edition is ever wanted at runtime, the parked variant of decision 3 is what the selector would point at.

### 3. Today's deck is parked as an unloaded variant, guarded by a parity test

Today's numbered files move, unchanged, to `pipelex/kit/configs/inference/deck_variants/multi_provider/`. Nothing loads that directory: not `init`, not `update`, not the manifest. Re-enabling it is a directory swap.

A unit test keeps "disabled" from meaning "rotting": for every directory under `deck_variants/`, it loads the variant's numbered files through the same loader as the shipped deck, checks that they validate as a `ModelDeckBlueprint`, and asserts that the variant defines exactly the same alias names and preset names, per model type, as the shipped deck. The only permitted difference is the set of provider-named aliases the shipped deck drops (decision 8), listed explicitly in the test. A preset added to one deck and not the other fails the test.

### 4. LLM aliases

| Alias | Today | Azure deck | Why |
| --- | --- | --- | --- |
| `default-premium`, `default-premium-vision`, `default-premium-structured` | claude-4.8-opus | gpt-5.5 | The flagship. Its fixed temperature only produces a warning when a preset carries its own temperature. |
| `default-general` (the choice default for `for_text` and `for_object`) | claude-4.6-sonnet | gpt-5.4 | The model every unnamed pipe gets. One step below premium, mirroring today's sonnet-below-opus shape. |
| `default-large-context-text`, `default-large-context-code` | gemini-flash-latest, gemini-pro-latest | gpt-5.4 | General tier. |
| `default-small`, `default-small-structured`, `default-small-vision`, `default-small-creative` | gpt-4o-mini, gpt-4o-mini, gemini-flash-latest, gemini-flash-latest | gpt-5.4-nano | Current generation with image and PDF input, at a small-tier price. |
| `best-gpt` | gpt-5.5 | gpt-5.5 | Unchanged. |
| `best-claude`, `best-gemini`, `best-mistral` | claude-4.8-opus, gemini-pro-latest, mistral-large | removed | Decision 8. |

Presets that name a model directly move to the tier they belong to: `retrieval-premium` to gpt-5.5, `engineering-codebase-analysis` (today `@best-gemini`) to `@default-premium`, `engineering-code-cheap` to gpt-5.4, `retrieval-cheap` and `engineering-code-cheaper` to gpt-5.4-nano. The two reasoning presets (`deep-analysis`, `quick-reasoning`) keep their `reasoning_effort` and follow `@default-premium`.

### 5. Image generation aliases

| Alias | Today | Azure deck |
| --- | --- | --- |
| `default-general` (the image choice default, behind `gen-image`) | nano-banana | gpt-image-2 |
| `default-premium` (behind `gen-image-high-quality`) | nano-banana-2 | gpt-image-2 |
| `default-small` (behind `gen-image-fast` and the testing presets) | gpt-image-1-mini | gpt-image-1-mini |
| `best-gpt` | gpt-image-2 | gpt-image-2 |
| `best-gemini` | nano-banana-2 | removed |

General and premium resolve to the same model, so `gen-image-high-quality` differs from `gen-image` only by its quality setting. The three presets naming `nano-banana-pro` directly (`synthesize-ui`, `synthesize-chart`, `gen-image-testing-img2img`) move to `@default-premium`; gpt-image-2 accepts input images, which is what those presets need.

### 6. Extract and search decks are unchanged

Document extraction already defaults to `azure-document-intelligence`. The two `pypdfium2-extract-pdf` aliases (`default-text-from-pdf`, `default-no-inference`) call no provider and stay. Search has no Azure equivalent: Linkup is the only search provider, the search section's `choice_default` is a required field, and `default-extract-web-page` is `linkup-fetch`. All of it stays, and the docs state that the Azure scope covers the three families Azure serves: language, image generation and document extraction.

### 7. Test profiles are untouched

`.pipelex-dev/test_profiles.toml` keeps naming Anthropic and Google handles directly so the runtime's support for those providers stays exercised. The `testing-*` presets ride the small tier, so a live run through them now uses gpt-5.4-nano instead of gpt-4o-mini.

### 8. The provider-named aliases are removed from the shipped deck

`best-claude`, `best-gemini` and `best-mistral` name a provider in the alias itself and cannot honestly resolve to a GPT model. They leave the shipped deck and stay defined in the parked variant. A method that references one fails validation with the usual alias-not-found error. The few tests that reference `@best-claude` are adjusted. Nothing in the cookbook or the authoring skills names them.

### 9. The `x_custom_*` templates keep their examples

The commented waterfall examples in `x_custom_llm_deck.toml` and `x_custom_extract_deck.toml` list Claude, Gemini and Mistral handles. They exist for a user who brings their own provider keys and are left as they are.

## Out of scope, and why

- **Routing.** The Gateway already serves the OpenAI language and image models from Azure. The deck decides which handles are named, not where a request goes, and nothing about the routing profiles or the remote config changes here.
- **Fixed-temperature constraints.** Several gpt-5.x handles carry `fixed_temperature = 1`. When a preset carries its own temperature, the worker forces the model's value and logs a warning. That is accepted.
- **An edition selector.** Declined, see decision 2.

## The backend model list moves first

The backend model lists under `pipelex/kit/configs/inference/backends/` are about to be updated by Louis, before or alongside this campaign, and the remote config in `pipelex-remote-config` is the authority on what a handle means. The tier structure and the vocabulary decisions above hold regardless. The concrete handles in the two tables are re-read against the updated backend lists when the build starts, and a handle that moved or was renamed is replaced by the tier's current equivalent, with the tables here updated to match.

## What the build changes

- The numbered deck files under `pipelex/kit/configs/inference/deck/`, per decisions 4 to 6, and the copy this repo keeps under `.pipelex/inference/deck/`.
- The parked variant directory and its parity test, per decision 3.
- The tests that reference `@best-claude` or a removed handle.
- The docs that name the current defaults: `docs/get-started/configure-ai-providers.md`, `docs/configuration/config-technical/inference-config.md`, `docs/building-methods/configure-ai-llm-to-optimize-methods.md`, and `docs/tools/cli/update.md` where it describes what an update run reports.
- A changelog entry marked breaking: the defaults move to Azure-served models, and three aliases are gone.

## Rollout notes

- Every existing install reports its numbered deck files as behind on its next `pipelex update`, and a user who edited a numbered file gets the usual timestamped backup. That is the mechanism working as designed, and the changelog entry says so.
- The consumers that keep their own deck copies (the hosted worker in `pipelex-server`, `pipelex-api`, the cookbook) pick the change up through the pin bump and `pipelex update`. The worker's numbered files are byte-identical to the kit's today, so nothing there needs hand-editing. The cookbook carries an extra `cookbook.toml` deck file to check for direct model names.
- The implementation tracker (`plan.md` beside this document) is written by the build session.
