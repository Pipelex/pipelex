---
name: add-model
description: >
  Add a new AI model to Pipelex's own inference configuration: the backend TOMLs in
  `.pipelex/inference/backends/` (OpenAI, Azure, Anthropic, Bedrock, Google, Vertex,
  Mistral and the rest), the kit copy, the test collections, live inference tests on
  every backend it lands on, and the changelog entry. Use when the user says "add a
  model", "add GPT-X", "add Claude X", "add Gemini X", "new model", "register a model",
  "support model X", "add model to backend", or names a model that no backend TOML
  declares yet and wants it available. The Pipelex Gateway and Manifold catalogs are
  not in this repository: in the Pipelex workspace, the workspace-level `/add-model`
  carries a model through them and runs this skill as its pipelex leg.
---

# Add a model to Pipelex

A model is added once per backend that serves it. Each backend TOML under `.pipelex/inference/backends/` declares the models that backend can call, the kit copy under `pipelex/kit/configs/` is what ships in the package, and `.pipelex-dev/test_profiles.toml` decides which models the parametrized inference tests can select. This skill touches those files and nothing else.

Two backends are different: `pipelex_gateway` and `pipelex_manifold` take their model catalogs from the **remote config**, a versioned artifact the runtime fetches at boot from the URL in `pipelex/system/pipelex_service/pipelex_details.py` (overridable with `PIPELEX_REMOTE_CONFIG_URL`). Their local TOMLs only let a user override `sdk` and `structure_method` per model, so a model cannot be added to them from here. See step 8.

## 1. Establish the facts, from the provider

Build a fact sheet before touching a file, and give every fact its source. The provider's own documentation is the primary source: its model page, its pricing page and its API reference name the exact model id, the input and output modalities, the prices, whether it reasons and how that is controlled, and which request parameters it refuses. Fetch those pages. OpenRouter is a useful cross-check for prices and modalities (`references/openrouter-price-lookup.md`), not a substitute: it lags new releases, and it cannot tell you which parameters a model deprecates.

| Fact | Where it goes | Watch for |
|---|---|---|
| Handle | The TOML table name, e.g. `["claude-5-sonnet"]` | Follow the family's existing naming, which is often not the provider's: `claude-5-sonnet`, not `claude-sonnet-5` |
| Model type | `model_type` when it differs from the file's `[defaults]` | `llm`, `img_gen`, `text_extractor` or `search` |
| Model id per backend | `model_id`, omitted when it equals the handle | Direct APIs, Azure deployments, Bedrock inference profiles and Vertex ids all differ; copy the shape the sibling uses on that backend |
| Inputs and outputs | `inputs`, `outputs` | Take the tokens from the sibling, because the runtime reads exact strings and a wrong one fails only when called. An LLM takes `text`, `images`, `pdf` (some hosts add `audio`, `video`) and outputs `text`, `structured`; a text extractor takes `pdf`, `image` (singular) or `web_page` and outputs `pages`; a search model outputs `sourced-answers`, `structured`; image generation outputs `image`. Declare `pdf` per backend: a backend that serves the model can still refuse documents |
| Costs | `costs = { input = …, output = … }` | USD per million tokens. Image models may price differently; copy the sibling's shape |
| Thinking | `thinking_mode` | `none`, `manual` (a budget the caller sets) or `adaptive` (the model decides) |
| Refused parameters | `listed_constraints`, `valued_constraints` | `temperature_unsupported`, `temperature_must_be_multiplied_by_2`, `max_tokens_must_be_high_enough`; `valued_constraints = { fixed_temperature = 1 }`. The vocabulary is `pipelex/cogt/model_backends/constraints.py` |
| Limits | `max_tokens`, `max_prompt_images` | Only where the sibling declares them |

A model spec declares nothing about how its prompts are formatted: templating style is authored on the pipe. And do not invent keys: a key the model-spec blueprint does not know fails the boot, unless it is a hyphenated header name with a plain string value, which is sent to the provider as an outbound HTTP header.

## 2. Find the footprint from the nearest sibling

The nearest sibling is the model the new one succeeds or sits beside: `claude-4.8-opus` for a new Opus, `gpt-5.5` for the next GPT, `gemini-3.5-flash` for the next Flash. Every place the sibling appears is a place the new model probably belongs:

```bash
grep -rnF -e '"<sibling>"' -e '[<sibling>]' -e '[<sibling>.' .pipelex/inference .pipelex-dev/test_profiles.toml
```

The three fixed strings match the handle as a whole token (a quoted table name or list entry, a bare table name, a bare `.rules` sub-table) and not as a prefix of a longer handle. The hits are the backend TOMLs, the test collection, and any deck alias or preset that names the sibling. The sibling's backends are the candidates, not the answer: a new model commonly reaches the provider's own API well before Bedrock, Vertex or Azure serve it, so check that each backend actually serves the new model before adding it there. Present the footprint to the user, backend by backend, with what you verified, and let them cut it down.

## 3. Write the entries

For each backend in the footprint, read the file's `[defaults]` table and the sibling's entry, then write the new entry beside the sibling under the same series comment header. Copy the sibling's shape and change only what the fact sheet says differs. Quote a table name that contains a dot: `["gpt-5.6"]`. An image-generation entry usually carries a `.rules` sub-table; copy the sibling's and check each rule against the provider's documentation. Edit the `.pipelex/` copy only; the next step syncs the kit.

## 4. Sync the kit

```bash
make ukc   # sync-kit-configs: .pipelex/ into pipelex/kit/configs/
make ccs   # check-config-sync: the two must now match
```

**If you edited `portkey.toml`, one migration golden moves with it.** The kit's `portkey.toml` is the reference document of the `inference-backend` migration surface, and the gates byte-compare `pipelex/migration/goldens/inference-backend/defaults@N.toml` against it, so `make check-migration-schemas` (`cmig`) turns red. That is the designed workflow: `make umig` rewrites the head goldens from the live source and `make cmig` is green again. No other backend file is coupled this way.

## 5. Add it to the test collections

In `.pipelex-dev/test_profiles.toml`, add the handle to the collection list the sibling is in: `[collections.llm]`, `[collections.img_gen]`, `[collections.extract]` or `[collections.search]`, under the manufacturer's key and next to the sibling. Profiles reference collections and globs, so a profile rarely needs editing.

## 6. Prove it live on every backend

A declared capability nobody has exercised is a claim, and the test fixtures are generated from these files, so run the model for real on every backend it was added to, one backend at a time. `/test-model` owns the procedure: the throwaway profile in the gitignored `.pipelex-dev/test_profiles_override.toml`, fixture regeneration through `PROF=`, the test class per model type, and reading the failures. Run it per backend.

For an LLM, go past `TestLLMInference` and exercise what the entry declares: `TestLLMGenObject` for `structured`, `TestLLMVision` for `images`, `TestLLMDocument` for `pdf`, and `TestLLMReasoning` when `thinking_mode` is not `none`. A failure there means the entry claims too much for that backend: fix the entry, or ask the user, rather than moving on.

## 7. Deck, changelog, checks

- **Deck.** Adding a model does not change the deck. Promoting it to an alias or preset in `.pipelex/inference/deck/` (`best-claude`, `default-premium`, a preset's `model`) changes what existing methods run on, so it is a separate decision: ask, and if the answer is yes, edit the deck, then run `make ukc` again. Promote only once the gateway catalog carries the model (step 8): under the default `all_pipelex_gateway` routing, a preset or choice default reaching a handle the catalog lacks raises `GatewayUnknownModelError` at boot, and `make tb` turns red. Then grep `docs/` for the alias you moved: `docs/configuration/config-technical/inference-backend-config.md` mirrors the deck's aliases, and other pages quote single ones.
- **Changelog.** One bullet under `## [Unreleased]` → `### Added` in `CHANGELOG.md`: the handle, the backends, what it takes and produces, and anything unusual such as a refused parameter.
- **Checks.** `make tb` boots the config, which parses every TOML and validates every spec. Then stage your changes (the drift digest reads the git index) and run `make agent-check`.

## 8. The gateway and manifold catalogs

This repository cannot add the model to `pipelex_gateway` or `pipelex_manifold`: their catalogs are published by the Pipelex team in the remote config. Tell the user so, and say which handle, model ids and capabilities the catalogs need. **In the Pipelex workspace, the workspace-level `/add-model` does that part**, and runs this skill as its pipelex leg.

Once a remote config carrying the model is published at the version this repository pins, regenerate the gateway model reference that ships in the package, then check it against that artifact:

```bash
make ugm   # update-gateway-models: rewrites pipelex_gateway_models*.md in .pipelex/ and the kit
make cgm   # check-gateway-models: both copies match the published artifact
```

Then `/test-model` on `pipelex_gateway` proves the model end to end through the gateway.

## Checklist

Show this to the user at the end, each box ticked or explained:

- [ ] Fact sheet, each fact with its source
- [ ] Entry in every backend TOML of the agreed footprint, under `.pipelex/inference/backends/`
- [ ] Kit synced (`make ukc`, `make ccs`), and the migration goldens if `portkey.toml` moved (`make umig`, `make cmig`)
- [ ] Handle in its test collection
- [ ] Live tests pass on every backend in the footprint, for every capability declared
- [ ] Deck left alone, or the promotion decided by the user, made after the gateway catalog carries the model, and mirrored in `docs/`
- [ ] Changelog entry under `[Unreleased]`
- [ ] `make tb` and `make agent-check` green
- [ ] Gateway and manifold catalogs handed off, and `make ugm` then `make cgm` run once they are published
