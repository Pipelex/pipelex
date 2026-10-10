---
description: "Set up AI model providers, routing profiles, and inference backends with your own API keys and custom routing."
---

# Inference Backend Configuration

The Inference Backend Configuration System manages how Pipelex handles AI model providers, model routing, and inference settings across LLMs, OCR, and image generation. This unified system provides a flexible and scalable way to configure multiple inference backends and route different types of AI models to the appropriate providers.

## Configuration Approaches

Pipelex calls AI models through backends you configure with your own provider API keys. This is how runs on this machine reach their models: a run on the hosted Pipelex API uses none of this configuration and no provider key, only a Pipelex API key (see [Running on the Hosted API](../../tools/cli/run.md#running-on-the-hosted-api)).

### Bring Your Own Keys

Use your own API keys from individual providers for full control and direct billing.

- ✅ Direct provider relationships
- ✅ Full control over billing
- ✅ No intermediary
- ✅ Support for all provider-specific features

See [Inference Backends](#inference-backends) section below for configuration.

### Mix & Match (Custom Routing)

Configure custom routing profiles to send some models to one provider and others to another. This gives you full flexibility to optimize for cost, performance, or rate limits.

- ✅ Cost optimization
- ✅ Performance tuning
- ✅ Gradual migration between providers

See [Routing Profiles](#routing-profiles) section below for setup.

## Overview

The inference backend system is built around four key concepts:

1. **Inference Backends**: Providers of AI services (OpenAI, Anthropic, Google Vertex AI, FAL, etc.) for LLMs, OCR, and image generation
2. **Model Specs**: Detailed information about specific models available through backends (text generation, text extraction, image generation)
3. **Routing Profiles**: Rules for selecting which backend should handle specific models across all AI capabilities
4. **Model Deck**: Unified collection of configured models, aliases, and presets for LLMs, OCR, and image generation

## Directory Structure

All inference backend configurations are stored in the `.pipelex/inference/` directory:

```
.pipelex/
└── inference/
    ├── backends.toml           # Backend provider configurations
    ├── backends_override.toml  # Personal overrides of backends.toml (git-ignored, optional)
    ├── routing_profiles.toml   # Model routing rules
    ├── routing_profiles_override.toml  # Personal overrides of routing_profiles.toml (git-ignored, optional)
    ├── backends/               # Individual backend model specifications
    │   ├── openai.toml         # OpenAI models (LLMs, image generation)
    │   ├── anthropic.toml      # Anthropic models (LLMs)
    │   ├── bedrock.toml        # Amazon Bedrock models (LLMs)
    │   ├── mistral.toml        # Mistral models (LLMs, OCR)
    │   ├── vertexai.toml       # Google Vertex AI models (LLMs)
    │   ├── fal.toml            # FAL models (image generation)
    │   ├── linkup.toml          # Linkup models (web search)
    │   ├── typesafe.toml       # TypeSafe models (judgment)
    │   ├── internal.toml       # Internal/local models (text extraction, the built-in document engine), managed by `pipelex update`
    │   └── ...
    └── deck/                   # Model deck configurations
        ├── 1_llm_deck.toml           # LLM aliases & presets
        ├── 2_img_gen_deck.toml       # Image generation config
        ├── 3_extract_deck.toml       # Document extraction config
        ├── 4_search_deck.toml        # Web search config
        ├── 5_doc_gen_deck.toml       # Document engines, by format and source
        ├── 6_judgment_deck.toml      # Judgment config
        ├── x_custom_llm_deck.toml    # Custom LLM waterfalls/overrides
        └── x_custom_extract_deck.toml # Custom extract waterfalls
```

Deck files are loaded in order by their numeric prefix (`1_`, `2_`, `3_`), with custom/override files (`x_` prefix) loaded last.

!!! tip "Numbered files are pipelex-managed; overrides go in `x_custom_*.toml`"
    The numbered deck files (`1_llm_deck.toml`...`6_judgment_deck.toml`) are refreshed by `pipelex update` when a new release ships an updated deck. Local edits to those files are preserved with a timestamped `.bak` backup but will not survive future updates.

    To customize aliases, presets, or default choices without conflict, edit (or create) any file in this directory whose name starts with `x_custom_` — Pipelex never tracks or overwrites those. See [`pipelex update`](../../tools/cli/update.md) for the full workflow.

## Inference Backends

Backends represent AI service providers that can offer LLMs, OCR models, or image generation models. Each backend is configured with its endpoint and authentication details.

### Backend Configuration

#### Step 1: Configure Environment Variables

First, set up your API keys in the `.env` file:

```bash
# Copy the example file
cp .env.example .env

# Edit .env and add your provider API keys
```

> **Note:** Pipelex automatically loads environment variables from `.env` files using python-dotenv. No need to manually source or export them.

The `.env.example` file contains all available providers with helpful comments:

```bash
OPENAI_API_KEY=

# Amazon Bedrock - For accessing models via Amazon Bedrock
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=

ANTHROPIC_API_KEY=
MISTRAL_API_KEY=

# Google AI Studio - Use GOOGLE_API_KEY for direct API access (simpler, rate-limited)
GOOGLE_API_KEY=

# Google Cloud Platform (GCP) - Use these for production Vertex AI access
# Choose GOOGLE_API_KEY OR GCP credentials, not both
GCP_PROJECT_ID=
GCP_LOCATION=
GCP_CREDENTIALS_FILE_PATH=gcp_credentials.json

FAL_API_KEY=

LINKUP_API_KEY=

TYPESAFE_API_KEY=
# ... (see .env.example for full list)
```

#### Step 2: Enable/Disable Backends

Configure which backends to use in `.pipelex/inference/backends.toml`:

```toml
[openai]
enabled = true  # Set to false to disable
api_key = "${OPENAI_API_KEY}"

[anthropic]
enabled = true
api_key = "${ANTHROPIC_API_KEY}"

[mistral]
enabled = true
api_key = "${MISTRAL_API_KEY}"

[fal]
enabled = true
api_key = "${FAL_API_KEY}"

[linkup]
enabled = true
api_key = "${LINKUP_API_KEY}"

[typesafe]
enabled = true
api_key = "${TYPESAFE_API_KEY}"

[internal]
enabled = true
# No API key needed for internal/local processing
```

The `${VARIABLE_NAME}` syntax automatically loads values from your `.env` file. Set `enabled = true` to activate a backend, or `false` to disable it.

Keys are needed only to call a provider. A process that runs methods resolves every enabled backend's variables when it starts, and refuses to start without one, naming it. A process that boots without inference, such as `pipelex validate`, `pipelex show backends` or a dry run, resolves none of them: it loads every enabled backend with all its models anyway, so a validation gives the same verdict whether or not your keys are set. Every backend reads its key from the variable its own `api_key` names, Linkup included.

A variable may stand only in a value that a call sends: `api_key`, `endpoint` and a backend's extra keys (such as `aws_region` or `gcp_project_id`) in `backends.toml`, and a model's `model_id`, `endpoint_path` and request headers in its backend's file. A field that describes the model, such as `model_type`, `sdk`, `thinking_mode`, `structure_method`, `inputs`, `outputs`, `costs` or the constraints, is written literally, because a boot without inference must know it without resolving anything. Pipelex refuses to boot on a variable in such a field and names the field and the variable.

An enabled backend must declare at least one model in its file under `backends/` (see [Model Specifications](#model-specifications)). Pipelex refuses to boot when one declares none, because routing would send models to a backend that cannot serve them: disable the backend, or list the models it serves. The `internal` backend is exempt, since plugins add its models at boot. A backend table also no longer accepts a `model_specs_section` key; an enabled backend that still carries one is refused, and the fix is to list its models in `backends/<name>.toml` and remove the key, or to disable the backend.

The `pipelex_gateway` backend that releases up to v0.72 shipped is gone. A configuration those releases set up, with it enabled, a routing profile such as `all_pipelex_gateway` active, or a `model_specs_section` key left behind, is refused with one error naming [`pipelex migrate`](../../tools/cli/migrate.md#a-configuration-a-former-release-set-up), which removes what they left, keeps a copy of each file it changes, and makes `all_enabled_backends` the active profile. The `pipelex_manifold` backend is not retired: what those releases left for it, a table they shipped disabled, its file under `backends/` and the `all_pipelex_manifold` profile, stays as it is.

Judgment models are served by their own backend alone, so the default routing profile sends them to their own backend through an optional route (`"jev-*" = "typesafe"`), which applies only while that backend is enabled. With a `TYPESAFE_API_KEY` set, `@default-judgment` works under the default profile with no routing edit.

### Model Specifications

Each backend has its own model specification file in `.pipelex/inference/backends/`:

```toml
# openai.toml
[defaults]
model_type = "llm"
sdk = "openai_responses"
structure_method = "instructor/openai_responses_tools"

[gpt-4o-mini]
model_id = "gpt-4o-mini"
inputs = ["text", "images"]
outputs = ["text", "structured"]
costs = { input = 0.15, output = 0.6 }

["gpt-5.4"]
model_id = "gpt-5.4"
inputs = ["text", "images", "pdf"]
outputs = ["text", "structured"]
costs = { input = 2.5, output = 15.0 }

[gpt-image-1]
model_id = "gpt-image-1"
sdk = "openai_img_gen"
model_type = "img_gen"
inputs = ["text"]
outputs = ["image"]
costs = { input = 0.04, output = 0.0 }
```

The `[defaults]` table applies to every model of the file, and a model table overrides any key of it.

#### One handle, several kinds of model

A handle names one model per model type. The same name may be an LLM and a judgment model at once, and each pipe reaches the kind its family asks for: a `PipeLLM` naming `acme-one` gets the LLM, and a `PipeJudge` naming it gets the judgment model. A table's name is its handle, and TOML forbids declaring a table twice, so the second model of a handle gets a table name of its own and says which handle it serves with `handle`:

```toml
# acme.toml
[defaults]
model_type = "llm"
sdk = "openai_responses"

["acme-one"]
inputs = ["text", "images"]
outputs = ["text", "structured"]
costs = { input = 0.1, output = 0.5 }

["acme-one-judgment"]
handle = "acme-one"
model_type = "judgment"
sdk = "acme_judgments"   # the judgment SDK the provider's plugin registers
inputs = ["text"]
outputs = ["judgments"]
costs = { input = 0.1, output = 0 }
```

The table name `acme-one-judgment` names the table and nothing else: methods, the model deck and the routing profiles all use the handle `acme-one`, and the model id defaults to the handle too. Two tables may share a handle only when their model types differ, so a file declaring one handle twice as the same type fails to load, naming both tables. `handle` cannot go in `[defaults]`, which every model of the file inherits, and like every key that describes the model rather than a value a call sends, it cannot reference a variable.

A routing profile routes a handle's name, so its route applies to every kind of model of that name. A model type the routed backend does not serve is looked for along the profile's `fallback_order`, or in the internal backend when it has none, when the name reached that backend by default, is left out when it reached it through a wildcard pattern, and is not served at all when the profile routes the name to that backend exactly: an exact route pins the name to one backend. A name the profile sends to no enabled backend, because no route matches it and neither its `default` nor any backend of its `fallback_order` is enabled, is served by the internal backend for each model type that backend declares under it, and by no other backend.

A method whose pipe names a handle the deck serves only as another kind of model is refused when it loads: a `PipeJudge` naming a handle served only as an LLM is told that the deck serves the handle, but not as a judgment model, and the suggestions list judgment models only.

#### Input formats

`inputs` lists what a model reads. For files, its entries are format keys, the same keys the runtime derives from a file's MIME type to check, before a run starts, that every file reaches a model able to read it: every image type is the `image` family, and any other type is its extension.

- **LLMs** declare `images` to read images (vision), and the document formats they read among `pdf`, `docx`, `pptx`, `xlsx` and `html`.
- **Extract models** declare the file formats they read among `pdf`, `docx`, `pptx`, `xlsx`, `html`, `md`, `csv`, `txt`, `vtt`, `eml` and `image`, and `web_page` when they fetch a web page from its URL themselves.

```toml
# internal.toml
[docling-extract-text]
model_type = "text_extractor"
sdk = "docling_sdk"
model_id = "extract-text"
inputs = ["pdf", "docx", "pptx", "xlsx", "html", "md", "csv", "txt", "vtt", "eml", "image"]
outputs = ["pages"]
costs = {}
```

A file whose format the consuming model does not declare is refused with an input error that names the input, the model and the formats it reads. A file whose format is unknown, with no type or the generic `application/octet-stream`, is left to the provider. Declare a format only once the model is known to read it.

#### Structure methods

`structure_method` says how a model is asked for structured output. A structure method names a provider, but the SDK decides how the request is sent. Each method stands for one of `instructor`'s core modes: every `*_tools` method is tool calling, and so is `instructor/openai_structured_outputs`, which sends OpenAI a non-strict tool schema; `instructor/mistral_structured_outputs` or `instructor/openrouter_structured_outputs` is a JSON-schema response format. So a method named after another provider still works through an OpenAI-compatible SDK.

One method keeps a behaviour of its own on the `anthropic` and `bedrock_anthropic` SDKs: tool calling forces the model to call the response tool, and `instructor/anthropic_reasoning_tools` leaves that choice to the model instead, steering it to the tool with a system line, for a model that refuses a forced tool choice. A structured call with thinking on, manual or adaptive, makes that same request on any Anthropic tool method, since a forced choice cannot carry thinking; so `instructor/anthropic_reasoning_tools` is only needed for a model that refuses a forced choice even without thinking.

On the `mistral` SDK, a reasoning setting on a structured output needs `instructor/mistral_tools`: a reasoning reply carries its answer beside a thinking chunk, which `instructor/mistral_structured_outputs` cannot parse, so that method refuses one.

The `google` backend uses `instructor/genai_structured_outputs`, Gemini's native JSON output. `instructor/genai_tools` works on it too: Gemini returns the function-call arguments as plain values, so pipelex validates them in pydantic's lax mode, where a string reaches an enum field as its member.

#### Temperature constraints

A job's temperature runs from 0 to 1, and three constraints adapt it to what a model's provider takes:

- `temperature_unsupported`, a listed constraint, is for a model whose provider refuses a temperature: no temperature is sent to it, on any SDK, and the model samples at its own default.
- `fixed_temperature`, a valued constraint, is for a model that takes one value only: the job's temperature is replaced by it, with a warning when the two differ.
- `temperature_must_be_multiplied_by_2`, a listed constraint, is for a provider whose scale runs from 0 to 2: the job's temperature is doubled.

```toml
# anthropic.toml
["claude-4.7-opus"]
model_id = "claude-opus-4-7"
listed_constraints = ["temperature_unsupported"]
```

A reasoning setting drops the temperature too on some SDKs, whatever the constraints say: the OpenAI SDKs, chat completions and Responses, send no temperature beside a reasoning effort, and the Anthropic SDKs none while thinking is on.

#### Thinking budget bounds

A model that thinks on a token budget (`thinking_mode = "manual"` on the `anthropic`, `bedrock_anthropic` and `google` SDKs) may declare the range of budgets its provider accepts, as two valued constraints, both inclusive and both optional:

```toml
# google.toml
["gemini-2.5-flash-lite"]
model_id = "gemini-2.5-flash-lite"
valued_constraints = { min_thinking_budget = 512, max_thinking_budget = 24576 }
```

A budget resolved from a reasoning effort, or set explicitly, is held within that range, and a `max_tokens` too small to hold the minimum beside the quarter kept for the answer is refused before the call is sent. The kit's Anthropic models declare Anthropic's minimum of 1,024 tokens, and its Gemini 2.5 models declare their ranges; a model that declares neither gets its budget fitted inside `max_tokens` alone.

On the `google` SDK, a reasoning effort of `none` is sent as a thinking budget of 0, which turns thinking off. A Gemini model that always thinks refuses that budget, so it lists the `thinking_cannot_be_disabled` constraint, and `none` on it is refused before the call is sent. The kit declares it on Gemini 2.5 Pro, Gemini 3.1 Pro and the `-latest` aliases that currently resolve to a model that always thinks:

```toml
# google.toml
["gemini-3.1-pro"]
model_id = "gemini-3.1-pro-preview"
listed_constraints = ["thinking_cannot_be_disabled"]
```

#### Sending extra request headers per model

A model table may carry keys beyond the model-spec fields. A key shaped like a request header — it contains a hyphen and its value is a string — is sent to the provider **as an HTTP request header** on each call to that model; this is how, for example, the Portkey backend routes each model to its upstream provider:

```toml
# portkey.toml
[gpt-4o-mini]
model_id = "gpt-4o-mini"
x-portkey-provider = "@openai"   # forwarded as the `x-portkey-provider` request header
```

**A header belongs on a model table and cannot go in `[defaults]`.** The two tables are read differently and it matters here: a model table has its header-shaped keys split off before validation, while `[defaults]` is copied into every model of the file as-is — so a header put there is not a shared header, it is an unknown model-spec field on every model at once, and the backend fails to load naming a model that never mentioned it. To apply the same header to several models, repeat it on each.

Because these strings go out over the network, an extra key is accepted as a header **only if it is shaped like one — it must contain a hyphen** (`x-portkey-provider`, `anthropic-beta`, `api-version`) **and its value must be a string** (quote it in TOML). Model-spec field names never contain a hyphen, so an unknown key without one is a misspelled setting or a field that no longer exists, and it is a configuration error rather than a header: the backend fails to load and the error names the key, the model and the file. A hyphenated spelling of a real field (`max-tokens` for `max_tokens`) is rejected the same way, with the field it resembles, and so is a header-shaped key whose value is not a string (`x-foo = 3`) — it is never stringified onto the wire. This holds in every boot mode, including the credential-free one used by `pipelex validate` and dry runs — a typo must never silently drop a backend and surface later as "model not found".

```text
Unknown key on model 'gpt-4o' for backend 'openai' from file '.pipelex/inference/backends/openai.toml':
'max_tokns' is not a known model-spec field, and not header-shaped. A per-model key that is not a
model-spec field is sent to the provider as a request header and must contain a hyphen
(e.g. 'x-portkey-provider'): fix the typo, or name the key like a header if that is what it is meant to be.
```

A key that clears that gate must also be *usable* as a header, so the name and the value are checked against what HTTP itself allows. A header name may contain only letters, digits and the characters ``!#$%&'*+-.^_`|~`` — so a quoted key like `"x-foo bar"` is rejected — and a header value must be printable ASCII on a single line with no leading or trailing whitespace, which rules out a line break, a control character, an accented letter, and the invisible trailing space in `x-foo = "value "`. Without this check the backend loaded happily and the HTTP client refused the request on the first call to that model, far from the file that caused it.

```text
Unknown key on model 'gpt-4o' for backend 'openai' from file '.pipelex/inference/backends/openai.toml':
'x-foo bar' cannot be a header name: ' ' is not allowed in one — a header name may contain only
letters, digits and the characters !#$%&'*+-.^_`|~.
```

`endpoint_path` is a declared model-spec field, not a header: it names the provider-side route for models that are called by raw path (some gateways' image models), and is never sent on the wire.

## Routing Profiles

Routing profiles determine which backend handles specific models. This is where you configure the **Mix & Match approach** to optimize your setup. Configure them in `.pipelex/inference/routing_profiles.toml`:

### Profile Examples

**Native Providers Only:**

Setup:
```bash
# In .env - add all provider keys you need
OPENAI_API_KEY="your-openai-key"
ANTHROPIC_API_KEY="your-anthropic-key"
GOOGLE_API_KEY="your-google-key"
FAL_API_KEY="your-fal-key"
```

In `.pipelex/inference/routing_profiles.toml`:
```toml
active = "custom_routing"

[profiles.custom_routing]
description = "Route models to their native providers"
default = "openai"

[profiles.custom_routing.routes]
"claude-*" = "anthropic"
"gemini-*" = "google"
"mistral-*" = "mistral"
"gpt-*" = "openai"
"gpt-image-*" = "openai"
"flux-*" = "fal"
```

**Mix & Match:**

Setup:
```bash
# In .env - combine the provider keys you need
ANTHROPIC_API_KEY="your-anthropic-key"
OPENAI_API_KEY="your-openai-key"  # For GPT models
FAL_API_KEY="your-fal-key"        # For image generation
```

In `.pipelex/inference/routing_profiles.toml`:
```toml
active = "hybrid"

[profiles.hybrid]
description = "Claude on Anthropic, GPT on OpenAI, FLUX on fal"
default = "anthropic"

[profiles.hybrid.routes]
# Use your own OpenAI key for GPT models and OpenAI image generation
"gpt-*" = "openai"
# Use your own FAL key for image generation (direct billing)
"flux-*" = "fal"
```

The `default` backend only serves the models it declares: Anthropic serves Claude models and nothing else, so a model with no route here that Anthropic does not serve, such as a Gemini or Mistral model, is left out of the deck. Give every model family you use a route, or list your backends in a `fallback_order` as the shipped `all_enabled_backends` profile does, so each model goes to the first enabled backend that serves it.

### Routing System Features

The routing system supports:

- **Exact matches**: `"gpt-4o-mini" = "openai"`
- **Wildcard patterns**: 
  - Prefix: `"gpt-*" = "openai"`
  - Suffix: `"*-turbo" = "openai"`
  - Contains: `"*-vision-*" = "openai"`
- **Default fallback**: `default = "anthropic"`

### Use Cases for Mix & Match

Common scenarios for hybrid routing:

1. **Cost Optimization**: Send expensive models to the provider that prices them best
2. **Rate Limits**: Spread high-volume models across providers to avoid rate limits
3. **Gradual Migration**: Move models from one provider to another one route at a time
4. **Provider Features**: Use a model's native provider when you need features an aggregator does not proxy

### Internal Backend (Always Available)

The **internal backend** is a special backend containing software-only models that run locally without requiring AI services. These include models for PDF text extraction, local document parsing, and other processing tasks that don't need external API calls.

Unlike other backends, internal backend models are **always available** regardless of which routing profile you select. This means you can use these models even when your routing profile is focused on a specific AI provider (e.g., `all_anthropic` or `all_openai`), and even when no backend your profile routes to is enabled: with the internal backend alone enabled, the shipped `all_enabled_backends` profile still serves every internal model.

Two things withhold an internal model. A route that sends its name to another backend on purpose, whether an exact route or a wildcard pattern that catches it, decides where that name goes, as it does for any model. Disabling the internal backend turns off all of its models, including the ones a plugin adds.

This behavior is automatic and requires no additional configuration. To see which models are available from the internal backend, check `.pipelex/inference/backends/internal.toml`.

`internal.toml` is the one backend file Pipelex manages: it declares the software-only models open Pipelex ships, so `pipelex update` refreshes it from the kit, and an existing install receives the models a release adds, such as the built-in document engine `reportlab-pdf`. A locally edited copy is backed up to `<file>.bak.<UTC timestamp>` first, unless you pass `--no-backup`, and your edits will not survive future updates, so declare models of your own in a backend of your own. Every other backend file is yours and is never touched. A plugin that ships a software-only engine declares its model in the internal backend itself when it loads, rather than in this file.

## Model Deck

The Model Deck is the unified configuration hub for all AI model-related settings, including LLMs, OCR models, and image generation models.

### Aliases

Define user-friendly names that map to model names. Aliases are defined in the deck files (e.g., `.pipelex/inference/deck/1_llm_deck.toml`):

```toml
[llm.aliases]
# Simple aliases map to a single model
best-gpt = "gpt-5.6-sol"

# Default aliases (used in presets)
default-general = "gpt-5.6-terra"
default-premium = "gpt-5.6-sol"
default-large-context-text = "gpt-5.6-terra"
default-small = "gpt-5.6-luna"
```

When using aliases in `.mthds` files or other configurations, prefix them with `@`:

```toml
model = "@best-gpt"              # References the best-gpt alias
model = "@default-general"       # References the default-general alias
```

### LLM Presets

Presets combine model selection with optimized parameters for specific tasks. Defined in `.pipelex/inference/deck/1_llm_deck.toml`:

```toml
[llm.presets]
# Every model this deck resolves to fixes its temperature at 1, so every preset
# declares that value rather than one the worker would override.
writing-factual = { model = "@default-premium", temperature = 1 }
writing-creative = { model = "@default-premium", temperature = 1 }

# Retrieval
retrieval = { model = "@default-large-context-text", temperature = 1 }

# Engineering
engineering-structured = { model = "@default-premium-structured", temperature = 1 }
engineering-code = { model = "@default-premium", temperature = 1 }

# Vision
vision = { model = "@default-premium-vision", temperature = 1 }
vision-cheap = { model = "@default-small-vision", temperature = 1 }
vision-diagram = { model = "@default-premium-vision", temperature = 1 }
```

When using presets in `.mthds` files, prefix them with `$`:

```toml
model = "$engineering-structured"   # Uses preset for structured extraction
model = "$vision"                   # Uses preset for image-to-text
model = "$writing-creative"         # Uses preset for creative writing
```

### Extract Presets

Extract presets combine document extraction model selection with optimized parameters. Defined in `.pipelex/inference/deck/3_extract_deck.toml`:

```toml
[extract.presets]
# Testing preset
extract-testing = { model = "@default-extract-document", max_nb_images = 5, image_min_size = 50 }
```

You can also use aliases directly in `.mthds` files for document extraction:

```toml
model = "@default-extract-document"   # Uses default document extraction alias
model = "@default-text-from-pdf"      # Uses alias for basic PDF text extraction
```

### Image Generation Presets

Image generation presets combine model selection with generation parameters. Defined in `.pipelex/inference/deck/2_img_gen_deck.toml`:

```toml
[img_gen.presets]
# General purpose image generation
gen-image = { model = "@default-general", quality = "medium" }
gen-image-fast = { model = "@default-small", quality = "low" }
gen-image-high-quality = { model = "@default-premium", quality = "high" }
```

When using image generation presets in `.mthds` files, prefix them with `$`:

```toml
model = "$gen-image"              # Uses default image generation preset
model = "$gen-image-fast"         # Uses fast image generation preset
model = "$gen-image-high-quality" # Uses high quality image generation preset
```

### Search Presets

Search presets combine a search model with result options. Defined in `.pipelex/inference/deck/4_search_deck.toml`:

```toml
[search.presets]
standard = { model = "linkup-standard", include_images = false, include_inline_citations = true }
deep = { model = "linkup-deep", include_images = false, include_inline_citations = true }
```

When using search presets in `.mthds` files, prefix them with `$`:

```toml
model = "$standard"    # Standard web search
model = "$deep"        # More thorough web search
```

Search presets support the following options:

- `model`: The search model to use (e.g., `linkup-standard`, `linkup-deep`)
- `include_images`: Whether to include images in search results
- `include_inline_citations`: Whether to include inline citations in the answer

### Document Engines

The engines a `PipeDocGen` step prints with are models of the `doc_gen` family in the `internal` backend. `reportlab-pdf` is built into Pipelex, declared in `internal.toml`, and prints a `pdf` from the auto-layout of the step's inputs. `pipelex-pdf`, `pipelex-xlsx`, `pipelex-docx` and `pipelex-pptx` come with the Pipelex document generation plugin, which declares them when it loads, so no file of yours lists them. Each lists the sources it prints from as its `inputs` (`layout`, `html` or `template_file`) and its format as its `outputs`. `.pipelex/inference/deck/5_doc_gen_deck.toml` names the engine a step prints with when it names none, for the one format and source open Pipelex prints:

```toml
[doc_gen.choice_defaults]
"pdf.layout" = "@default-pdf"

[doc_gen.aliases]
default-pdf = "reportlab-pdf"
```

The plugin declares the defaults for a `pdf` from a template and for `xlsx`, `docx` and `pptx` itself, beneath the deck files. You can still set any default yourself, for any format and source, in an `x_custom_*.toml` deck file, which overrides both. A step names another engine with `model`, such as `model = "pipelex-pdf"` for a PDF without a template. See [PipeDocGen](../../building-methods/pipes/pipe-operators/PipeDocGen.md).

### Default Choices

Set default models for different types of AI operations:

```toml
[llm.choice_defaults]
for_text = "@default-general"
for_object = "@default-general"

[extract]
choice_default = "@default-extract-document"

[img_gen]
choice_default = "$gen-image"

[search]
choice_default = "@default-search"
```

Note the sigil prefixes: `@` for aliases and `$` for presets.

## Customization

### Personal overrides

`backends.toml` and `routing_profiles.toml` are tracked files: the project ships them, and `pipelex init` writes them. To run on a different backend without editing them — to try a backend the project keeps off, or to move every project on your machine onto one provider — write the change in a personal override file beside them:

- `backends_override.toml` layers over `backends.toml`
- `routing_profiles_override.toml` layers over `routing_profiles.toml`

An override carries only the keys it sets. Tables merge into the base's tables, so `[anthropic]` with a single `enabled = true` flips that one flag and leaves the backend's other keys alone; scalars and lists replace the base's value whole, so a `fallback_order` in an override is the whole list, not an addition to it. The merge happens before validation, which is why `active = "all_anthropic"` on its own is a complete routing override.

Both files are optional and git-ignored: `pipelex init` writes the rule into `.pipelex/.gitignore` for a fresh project (a project set up earlier adds the two names to its own `.gitignore`), the kit never ships them, and `pipelex migrate` never touches them.

Where a file lives decides its reach. The base file resolves as before — the project's copy if it has one, otherwise the global one — and the overrides merge over it in this order:

1. the base `backends.toml` / `routing_profiles.toml`
2. `~/.pipelex/inference/<file>_override.toml` — the global override, applied in every project on the machine (under the directory `PIPELEX_HOME` names, when it is set: see [the home configuration directory](../index.md#the-home-configuration-directory-pipelex_home))
3. `{project}/.pipelex/inference/<file>_override.toml` — the project override, which wins

The global override reaches a project that carries its own tracked base, which is the point: one edit under `~/.pipelex/inference/` and every project follows. Deleting the override files restores the shipped default.

A developer who wants a whole machine on Anthropic alone writes two files once:

```toml
# ~/.pipelex/inference/backends_override.toml
[anthropic]
enabled = true
```

```toml
# ~/.pipelex/inference/routing_profiles_override.toml
active = "all_anthropic"
```

Enabling a backend and activating a profile that needs it go together: a profile whose default or routes name a backend that is not enabled is refused at boot, and the error names the backend to enable. `pipelex show backends` and `pipelex doctor` report the merged view, so what they print is what runs.

An override leaves a trace. When one was merged, the boot logs which files each document was read from, so a run on an unexpected backend says why in its own log. A file that does not parse is refused the way an invalid document is — as a setup error naming the file, in the boot, in `pipelex init` and in the doctor's Models row — and so is a value where a table was meant, such as `anthropic = false` where `[anthropic]` with `enabled = false` was intended. `pipelex init` keeps writing the base file.

### Custom deck files

Use custom deck files (prefixed with `x_`) for project-specific customizations:

**For LLMs** (`.pipelex/inference/deck/x_custom_llm_deck.toml`):

```toml
# Override default choices
[llm.choice_overrides]
for_text = "@my-custom-alias"
for_object = "@my-custom-alias"

# Add custom waterfalls - lists of models tried in order
[llm.waterfalls]
premium-llm = ["claude-4.5-opus", "gemini-3.1-pro", "gpt-5.4"]
small-llm = ["gemini-2.5-flash-lite", "gpt-4o-mini", "claude-3-haiku"]
```

**For Extract** (`.pipelex/inference/deck/x_custom_extract_deck.toml`):

```toml
[extract.waterfalls]
document_extractor = ["mistral-document-ai-2505", "pypdfium2-extract-pdf"]
```

When using waterfalls in `.mthds` files, prefix them with `~`:

```toml
model = "~premium-llm"    # Will try claude-4.5-opus, then gemini-3.1-pro, then gpt-5.4
model = "~small-llm"      # Will try gemini-2.5-flash-lite, then gpt-4o-mini, etc.
```

### Adding New Backends

To add a new backend:

1. Add backend configuration to `backends.toml`
2. Create model specification file in `backends/` directory
3. Update routing profile if needed

## Loading Process

The system loads configurations in this order:

1. **Load Backends**: Read `backends.toml`, with any `backends_override.toml` merged over it (see [Personal overrides](#personal-overrides)), to get enabled backends
2. **Load Model Specs**: For each backend, load model specifications (LLMs, OCR models, image generation models)
3. **Load Routing Profiles**: Read `routing_profiles.toml`, with any `routing_profiles_override.toml` merged over it, and identify the active profile
4. **Build Model Deck**: 
   - Apply routing rules to determine backend for each model across all AI capabilities
   - Load aliases and presets from deck files for LLMs, OCR, and image generation
   - Apply overrides
5. **Finalization**: Validate complete configuration

## Error Handling

Common error types:

- `ModelDeckNotFoundError`: Missing LLM deck configuration files
- `ModelNotFoundError`: Referenced model not found in the deck
- `LLMHandleNotFoundError`: Referenced model or alias not found
- `ModelChoiceNotFoundError`: Referenced preset/choice not found

## When you upgrade and a backend file is out of date

`pipelex init` writes the backend definitions once and never overwrites a file you already have — which is what keeps your edits, and which also means a file written by an older Pipelex stays on your machine after the model-spec format changes. When a release removes a key, your copy still carries it, and the strict model that reads it refuses.

You do not have to do anything about that at boot. Pipelex reads the migration history for the `inference/backends/` files, carries the out-of-date ones forward **in memory**, and starts with a warning line for each file, the file and what the migration history carried forward following the message as fields:

```
WARNING  A configuration file is out of date and was migrated in memory only file.path=/Users/me/.pipelex/inference/backends/openai.toml migration_steps="[\"Drop prompting_target from every backend definition\"]" has_blocked_steps=false
         → Run pipelex migrate to update it
```

Nothing has been written at that point, so the warning comes back at the next boot until you run the command:

```bash
pipelex migrate --dry-run   # show what would change in each file, and stop
pipelex migrate             # ask, then rewrite in place
```

What it touches and what it leaves alone:

- **Every `*.toml` directly in `inference/backends/`** — the files this page describes, in both the global `~/.pipelex/` and a project's `.pipelex/`.
- **Not** `inference/backends.toml`, which sits beside that directory rather than in it, and **not** the model deck under `inference/deck/`. The deck has its own `pipelex update`, which also refreshes `internal.toml` from the kit. A `backends.toml` left by an older release that still enables a backend with no model file, such as `[pipelex_gateway]`, is refused at boot and has to be edited by hand: set that backend's `enabled = false`, and point the active routing profile in `routing_profiles.toml` at a backend you have enabled.
- **Not a key you added yourself.** The history only describes keys *we* removed or renamed. An unknown key of your own — a misspelled `maxx_tokens`, an extra header that is not header-shaped — is still an error, and it names the file, the key and what to do. That is deliberate: silently dropping a key you meant to set would change which model you get.
- **Every file it rewrites is copied first**, beside itself, as `<file>.bak.<UTC timestamp>`. Running the command twice is the same as running it once — a file already up to date comes back byte for byte identical.

`pipelex doctor` shows the same thing before anything fails: its **Configuration Migrations** row names every backend file a migration would rewrite, and `pipelex doctor --fix` offers to run it for you.

See [The Migration Ledger](../../migration-ledger.md) for what the history may contain and what it guarantees, and [`pipelex migrate`](../../tools/cli/migrate.md) for the command itself.

## Best Practices

1. **Choosing Your Configuration Approach**:
   - **Starting out?** Enable the one provider you already have a key for, and route everything to it
   - **Optimizing costs/performance?** Use Mix & Match for maximum flexibility
   - You can switch between approaches at any time by changing your routing profile

2. **Backend Management**:
   - Keep API keys in environment variables (never commit them)
   - Enable only the backends you need to reduce configuration complexity
   - Document custom backend configurations for your team

3. **Model Routing**:
   - Use specific routing profiles for different environments (dev, staging, prod)
   - Test routing rules before production deployment
   - Consider cost implications when routing models (some providers are cheaper for certain models)
   - Monitor usage patterns to optimize your routing strategy

4. **Presets and Aliases**:
   - Create task-specific presets for consistency across your pipelines
   - Use kebab-case naming (e.g., `engineering-structured`, `vision-diagram`)
   - Use proper sigil prefixes: `$` for presets, `@` for aliases, `~` for waterfalls
   - Document custom presets and their use cases in your team documentation

5. **Customization**:
   - Use `x_custom_*.toml` deck files for project-specific settings
   - Keep base configurations unchanged to make upgrades easier
   - Version control your custom configurations
   - Share routing profiles and presets across your team

## Related Documentation

- [LLM Integration](../../features/llm-integration.md) - Overview of LLM provider support and capabilities
- [PipeLLM Operator](../../building-methods/pipes/pipe-operators/PipeLLM.md) - The pipe operator that uses inference backends
- [Configure AI Providers](../../get-started/configure-ai-providers.md) - Setup guide for connecting AI providers
