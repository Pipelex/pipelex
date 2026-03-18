---
name: add-model
description: >
  Add a new AI model to the Pipelex inference system. Guides through all required
  steps: backend TOML configuration (OpenAI, Azure, Anthropic, Google, etc.), kit
  sync, test profile collections, and fixture regeneration. Use when the user says
  "add a model", "add GPT-X", "add Claude X", "new model", "register a model",
  "add Gemini X", "support model X", "add model to backend", or any variation of
  introducing a new AI model to the inference configuration. Also use when the user
  mentions a model name that doesn't exist in the backend configs yet and wants to
  add it.
---

# Add a New AI Model

This skill walks through all the steps needed to register a new AI model in the
Pipelex inference system. The process touches several files across the codebase
and must be done in order to keep everything consistent.

## Overview of what needs to happen

1. **Identify the model** — which provider, what capabilities, what costs
2. **Add to backend TOML(s)** — the model spec in each relevant backend config
3. **Sync kit configs** — propagate `.pipelex/` changes into `pipelex/kit/configs/`
4. **Add to test profile collections** — so the model is available for test selection
5. **Regenerate test fixtures** — refresh the generated model sets
6. **Run inference tests** — verify the model works end-to-end with real API calls
7. **Gateway (manual)** — the user handles this separately since it's remote config

## Step 1: Gather model information

Before editing any files, collect the following from the user. If the user already
provided some of this, confirm what you have and ask only for the missing pieces.

| Field | Description | Example |
|-------|-------------|---------|
| **Model name** | The handle used in Pipelex (the TOML section header) | `gpt-5.4` |
| **Model type** | `llm`, `img_gen`, `text_extractor`, or `search` | `llm` |
| **Provider** | Who made it — determines which backends to add it to | OpenAI |
| **Backends** | Which backend TOML files to add it to | `openai`, `azure_openai` |
| **Model ID** | The actual API model identifier (if different from name) | `gpt-5.4-2026-03-01` |
| **Inputs** | Supported input types | `["text", "images", "pdf"]` |
| **Outputs** | Supported output types | `["text", "structured"]` |
| **Costs** | USD per million tokens `{ input = X, output = Y }` | `{ input = 2.0, output = 8.0 }` |
| **Thinking mode** | `none`, `manual`, or `adaptive` | `manual` |
| **Constraints** | Any special constraints (e.g. fixed temperature) | `{ fixed_temperature = 1 }` |

### Looking up costs and capabilities

If the user doesn't know the model's pricing or capabilities, look them up on
OpenRouter. Read `references/openrouter-price-lookup.md` for the full API
reference, but here's the quick version:

1. Fetch `https://openrouter.ai/api/v1/models` (for LLMs) or
   `https://openrouter.ai/api/frontend/models?category=image-generation` (for
   image gen models).
2. Filter the response for the model by `id` or `name` (e.g., `openai/gpt-5.4`).
3. Convert prices from **per token** to **per million tokens** (multiply by
   1,000,000). Example: `"prompt": "0.000002"` becomes `input = 2.0`.
4. Map modalities: OpenRouter `image` -> our `images` (input) or `image` (output),
   OpenRouter `file` -> our `pdf`. If `"tools"` is in `supported_parameters`,
   add `"structured"` to outputs.

### Determining which backends

Each provider typically maps to specific backends:

| Provider | Backends to add to |
|----------|-------------------|
| OpenAI | `openai` + `azure_openai` |
| Anthropic | `anthropic` + `bedrock` |
| Google | `google` + `vertexai` |
| Mistral | `mistral` + `scaleway` |
| Meta (Llama) | `groq`, `bedrock`, `ollama` (varies) |
| xAI (Grok) | `xai` |

The **gateway** (`pipelex_gateway`) is always a separate manual step — its config
is fetched remotely. Remind the user about this at the end.

### Backend-specific differences

When adding a model to multiple backends, be aware of these differences:

- **OpenAI direct**: `model_id` is often omitted (defaults to the section name).
  SDK is `openai_responses`. May support `pdf` in inputs.
- **Azure OpenAI**: `model_id` is always required (includes a date suffix like
  `gpt-5.4-2026-03-01`). SDK is `azure_openai_responses`. Inputs typically use
  `images` but not `pdf`. Image gen models use `azure_rest_img_gen` SDK and need
  a `.rules` sub-table.
- **Anthropic direct**: SDK is `anthropic`. Uses `prompting_target = "anthropic"`,
  `structure_method = "instructor/anthropic_tools"`. Often has `max_tokens` and
  `max_prompt_images`.
- **Bedrock**: SDK is `bedrock_converse`. Has its own `prompting_target`.
- **Google direct**: SDK is `google`. Uses `prompting_target = "gemini"`,
  `structure_method = "instructor/genai_tools"`.

Each backend TOML has a `[defaults]` section — the model entry only needs to
specify fields that differ from those defaults. Read the defaults before writing
the entry so you include the minimum necessary fields.

## Step 2: Add the model to backend TOML files

The backend config files live in two mirrored locations. Edit the **`.pipelex/`**
copy (the project config), then sync to kit in the next step.

```
.pipelex/inference/backends/<backend_name>.toml     # <-- edit this one
pipelex/kit/configs/inference/backends/<backend_name>.toml  # <-- synced by make
```

### How to write the TOML entry

1. Read the target backend TOML file to understand its `[defaults]` and the
   existing model entries — match the style and ordering conventions.
2. Place the new model in the right section (models are grouped by series with
   comment headers like `# --- GPT-5.4 Series ---`).
3. Quote the section header if the model name contains dots: `["gpt-5.4"]`.
4. Only include fields that differ from `[defaults]`. At minimum you need:
   `inputs`, `outputs`, `costs`. Add `model_id` if it differs from the name.

**Example — adding `gpt-5.4` to `openai.toml`:**

```toml
# --- GPT-5.4 Series -----------------------------------------------------------
["gpt-5.4"]
inputs = ["text", "images", "pdf"]
outputs = ["text", "structured"]
costs = { input = 2.0, output = 8.0 }
thinking_mode = "manual"
```

**Example — adding `gpt-5.4` to `azure_openai.toml`:**

```toml
# --- GPT-5.4 Series -----------------------------------------------------------
["gpt-5.4"]
model_id = "gpt-5.4-2026-03-01"
inputs = ["text", "images"]
outputs = ["text", "structured"]
costs = { input = 2.0, output = 8.0 }
thinking_mode = "manual"
```

Note: Azure typically does not support `pdf` in inputs and always requires an
explicit `model_id` with a date suffix.

For **image generation models** on Azure, you also need a `.rules` sub-table:

```toml
["model-name".rules]
prompt = "positive_only"
num_images = "gpt"
aspect_ratio = "gpt"
background = "gpt"
inference = "gpt"
safety_checker = "unavailable"
output_format = "gpt"
```

## Step 3: Sync kit configs

After editing the `.pipelex/` files, sync them into `pipelex/kit/configs/`:

```bash
make ukc
```

This runs `rsync` from `.pipelex/` to `pipelex/kit/configs/`, keeping them in
sync. Then verify:

```bash
make ccs
```

This checks that the two directories match. If it reports differences, something
went wrong with the sync.

## Step 4: Add to test profile collections

Edit `.pipelex-dev/test_profiles.toml` to include the new model in the
appropriate collection(s).

Collections are organized by model type and manufacturer:

- **LLM models** go under `[collections.llm]` in the right manufacturer list
  (e.g., `openai`, `anthropic`, `google`).
- **Image gen models** go under `[collections.img_gen]` in the right list.
- **Extract models** go under `[collections.extract]`.
- **Search models** go under `[collections.search]`.

Add the model name to the relevant list, maintaining alphabetical order within
each series. For example, adding `gpt-5.4` to the OpenAI LLM collection:

```toml
[collections.llm]
openai = [
  # ... existing models ...
  "gpt-5.3-codex",
  "gpt-5.4",        # <-- add here
]
```

### Optionally add to specific profiles

If the model should be part of a named test profile (like `dev` or `coverage`),
add it there too. But usually the collections are enough — profiles reference
collections via `@collection_name` or glob patterns like `gpt-*`.

## Step 5: Regenerate test fixtures

Run the fixture regeneration to update the generated model sets:

```bash
make rtm
```

This runs `pipelex-dev preprocess-test-models --generate-fixtures --profile dev`
and updates `tests/integration/pipelex/fixtures/_generated_model_sets.py`.

Verify the generated file includes the new model if the active profile selects it.

## Step 6: Run inference tests against the new model

Once the model is registered and fixtures are regenerated, help the user run the
integration tests to verify the model actually works end-to-end with real API
calls.

### Create targeted test profiles — one per backend

**IMPORTANT**: You must test the model on **every backend** it was added to, not
just one. Create a separate temporary profile for each backend in
`.pipelex-dev/test_profiles_override.toml` (this file is gitignored so it won't
pollute the shared config).

For example, if the model was added to both `openai` and `azure_openai`:

```toml
[profiles.new_model_openai]
description = "Test the newly added model on OpenAI"
backends = ["openai"]
llm_models = ["gpt-5.4"]
img_gen_models = []
extract_models = []
search_models = []

[profiles.new_model_azure]
description = "Test the newly added model on Azure OpenAI"
backends = ["azure_openai"]
llm_models = ["gpt-5.4"]
img_gen_models = []
extract_models = []
search_models = []
```

Adjust the `backends` and model list fields based on what type the model is
(`llm_models`, `img_gen_models`, `extract_models`, or `search_models`).

### Regenerate fixtures and run tests for EACH backend

For each backend profile, regenerate fixtures and run the inference tests:

```bash
# Test on first backend
make rtm PROF=new_model_openai
make ti PROF=new_model_openai TEST=TestLLMInference

# Test on second backend
make rtm PROF=new_model_azure
make ti PROF=new_model_azure TEST=TestLLMInference
```

Use the appropriate test class for the model type:

- **LLM models**: `make ti PROF=<profile> TEST=TestLLMInference`
- **Image gen models**: `make ti PROF=<profile> TEST=TestImageGeneration`
- **Extract models**: `make ti PROF=<profile> TEST=TestExtract`
- **Search models**: `make ti PROF=<profile> TEST=TestSearch`

The `PROF` parameter selects the test profile (which controls which models are
tested), and `TEST` selects the test class or method to run.

These are live API calls, so they require valid API keys for the backend being
tested. If tests fail, check whether the issue is in the model config (wrong
model_id, missing capabilities) or in the API key / network setup.

### Restore the default profile after testing

Once all backends have been tested, regenerate fixtures back to the standard dev
profile:

```bash
make rtm
```

Ask the user if they want the temporary profiles removed from
`test_profiles_override.toml`. If they do, clean them up. If not, leave them
in place — the file is gitignored so it won't affect anyone else.

## Step 7: Gateway (manual — user action required)

Remind the user:

> The **Pipelex Gateway** configuration is fetched from a remote server. You
> cannot add the model to the gateway from this repo. To make the model available
> through the gateway, it needs to be added to the remote gateway configuration
> separately. Once it's there, it will be picked up automatically by Pipelex
> clients using the gateway backend.

The local file `.pipelex/inference/backends/pipelex_gateway.toml` only allows
overriding `sdk` and `structure_method` per model — you cannot define new models
in it.

## Step 8: Verify everything works

Run the boot sequence test to make sure config loading succeeds:

```bash
make tb
```

This tests the full boot sequence including config loading, which validates that
all TOML files parse correctly and model specs are well-formed.

Then run the full quality check:

```bash
make agent-check
```

## Checklist summary

Present this checklist to the user at the end so they can confirm everything:

- [ ] Model entry added to `<backend>.toml` in `.pipelex/inference/backends/`
- [ ] Kit configs synced (`make ukc` + `make ccs`)
- [ ] Model added to collections in `.pipelex-dev/test_profiles.toml`
- [ ] Test fixtures regenerated (`make rtm`)
- [ ] Inference tests pass on **every backend** the model was added to (one `make rtm PROF=...` + `make ti` per backend)
- [ ] Default fixtures restored (`make rtm`)
- [ ] Boot test passes (`make tb`)
- [ ] Quality checks pass (`make agent-check`)
- [ ] Gateway: user will add the model to the remote gateway config separately
