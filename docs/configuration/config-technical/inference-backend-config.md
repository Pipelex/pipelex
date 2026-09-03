---
description: "Set up AI model providers, routing profiles, and inference backends — use Pipelex Gateway, direct API keys, or custom configurations."
---

# Inference Backend Configuration

The Inference Backend Configuration System manages how Pipelex handles AI model providers, model routing, and inference settings across LLMs, OCR, and image generation. This unified system provides a flexible and scalable way to configure multiple inference backends and route different types of AI models to the appropriate providers.

## Configuration Approaches

Pipelex supports three flexible approaches for accessing AI models:

### Option A: Pipelex Gateway (Optional & Free)

Get a single API key that works with all major providers (OpenAI, Anthropic, Google, Mistral, FAL, and more). This is the **recommended approach for getting started quickly**.

- ✅ Single API key for all providers
- ✅ Simplified configuration
- ✅ Automatic model routing
- ✅ Free on Discord (limited time offer)

!!! note "Terms of Service"
    Using Pipelex Gateway requires accepting our terms of service. When you run `pipelex init`, you'll be prompted to review and accept the terms. Gateway usage enables identified telemetry (tied to your hashed API key) for service monitoring. See our [Privacy Policy](https://go.pipelex.com/privacy-policy) for details.

### Option B: Bring Your Own Keys

Use your own API keys from individual providers for full control and direct billing. Ideal for production deployments with existing provider relationships.

- ✅ Direct provider relationships
- ✅ Full control over billing
- ✅ No intermediary
- ✅ Support for all provider-specific features

See [Inference Backends](#inference-backends) section below for configuration.

### Option C: Mix & Match (Custom Routing)

Configure custom routing profiles to use your own keys for some models and Pipelex Gateway for others. This gives you full flexibility to optimize for cost, performance, or rate limits.

- ✅ Hybrid approach
- ✅ Cost optimization
- ✅ Performance tuning
- ✅ Gradual migration between approaches

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
    │   ├── internal.toml       # Internal/local models (OCR)
    │   └── ...
    └── deck/                   # Model deck configurations
        ├── 1_llm_deck.toml           # LLM aliases & presets
        ├── 2_img_gen_deck.toml       # Image generation config
        ├── 3_extract_deck.toml       # Document extraction config
        ├── 4_search_deck.toml        # Web search config
        ├── x_custom_llm_deck.toml    # Custom LLM waterfalls/overrides
        └── x_custom_extract_deck.toml # Custom extract waterfalls
```

Deck files are loaded in order by their numeric prefix (`1_`, `2_`, `3_`), with custom/override files (`x_` prefix) loaded last.

!!! tip "Numbered files are pipelex-managed; overrides go in `x_custom_*.toml`"
    The numbered deck files (`1_llm_deck.toml`...`4_search_deck.toml`) are refreshed by `pipelex update` when a new release ships an updated deck. Local edits to those files are preserved with a timestamped `.bak` backup but will not survive future updates.

    To customize aliases, presets, or default choices without conflict, edit (or create) any file in this directory whose name starts with `x_custom_` — Pipelex never tracks or overwrites those. See [`pipelex update`](../../tools/cli/update.md) for the full workflow.

## Pipelex Gateway (Optional & Free)

Pipelex Gateway is a unified inference backend that provides access to all major AI providers through a single API key. This is the **recommended approach for getting started quickly** with Pipelex and **unlocking its full power**—with many models already available and new ones being added constantly. Using Pipelex Gateway is **completely optional**.

### Benefits

- **Single API Key**: Access OpenAI, Anthropic, Google, Mistral, FAL, and more with one key
- **Free to Get Started**: Available free on [app.pipelex.com](https://app.pipelex.com/) (no credit card required, limited time offer)
- **Simplified Configuration**: No need to manage multiple provider credentials
- **Automatic Routing**: All AI models (LLMs, OCR, image generation) are automatically routed to their respective providers
- **Unified Interface**: Same configuration system for text generation, OCR, and image generation

### Terms of Service & Telemetry

Using Pipelex Gateway requires accepting our terms of service. When you enable Gateway and run `pipelex init`, you'll be prompted with a terms panel explaining:

- **What we collect**: Model names, token counts, latency, error rates (technical data only)
- **What we do NOT collect**: Your prompts, completions, pipe codes, or business data
- **Why**: To monitor service quality, enforce fair usage, and provide better support
- **Your choice**: If you decline, Gateway is disabled and you can use direct provider backends instead

Your API key is hashed for security. Gateway telemetry operates independently from your `telemetry.toml` settings. See our [Privacy Policy](https://go.pipelex.com/privacy-policy) for details.

### Setup

1. **Get your API key:**

    - Visit [https://go.pipelex.com/discord](https://go.pipelex.com/discord) to join our Discord
    - Request your free API key in the appropriate channel
    - No credit card required (limited time offer)

2. **Configure environment variables:**

    ```bash
    # Copy the example environment file
    cp .env.example .env
    
    # Edit .env and add your Pipelex Gateway API key
    PIPELEX_GATEWAY_API_KEY="your-api-key"
    ```

3. **Accept terms and verify configuration:**

    ```bash
    pipelex init
    ```
    
    When prompted, review and accept the Gateway terms of service.

4. **Verify backend configuration:**
   
   The `pipelex_gateway` backend should be enabled in `.pipelex/inference/backends.toml`:
   
   ```toml
   [pipelex_gateway]
   display_name = "⭐ Pipelex Gateway"
   enabled = true
   api_key = "${PIPELEX_GATEWAY_API_KEY}"
   ```
   
   The environment variable `${PIPELEX_GATEWAY_API_KEY}` will be automatically loaded from your environment.

4. **Verify routing configuration:**

   The default routing profile in `.pipelex/inference/routing_profiles.toml` should be set to `all_pipelex_gateway`:

   ```toml
   active = "all_pipelex_gateway"

   [profiles.all_pipelex_gateway]
   description = "Use Pipelex Gateway for all its supported models"
   default = "pipelex_gateway"
   ```

### Usage

Once configured, all models are available through the unified backend. Use standard model names in your pipelines:

```toml
[pipe.example]
type = "PipeLLM"
model = { model = "claude-4.5-sonnet", temperature = 0.7 }
# Model automatically routed through Pipelex Gateway
```

### Gateway Model Overrides

!!! warning "Advanced Feature - Use at Your Own Risk"
    The Pipelex Gateway model configuration is fetched remotely from Pipelex servers. Any local override may cause unexpected behavior or failures, as the remote configuration may change at any time.

If you need to customize how a specific model behaves through the Gateway, you can add per-model overrides in `.pipelex/inference/backends/pipelex_gateway.toml`. However, only two keys are supported:

- `sdk`: The SDK to use for the model (e.g., `gateway_completions`)
- `structure_method`: The method for structured output (e.g., `instructor/openai_tools`)

All other keys will be ignored.

```toml
# .pipelex/inference/backends/pipelex_gateway.toml

# Per-model overrides example:
[gpt-4o]
sdk = "gateway_completions"
structure_method = "instructor/openai_tools"
```

!!! tip "Prefer Direct Backends for Custom Configurations"
    If you need custom configurations beyond `sdk` and `structure_method`, consider using your own API keys with direct provider backends (openai, anthropic, etc.) instead of Gateway overrides.

### Model Availability Note

While Pipelex Gateway provides access to most AI models through a unified API, certain specialized models require their native backend to be enabled directly:

- **FAL image generation models** (e.g., Flux models) - Enable the FAL backend
- **OpenAI image generation** (`gpt-image-1`) - Enable the OpenAI backend (should also work via Azure OpenAI, but we haven't been able to test this - if you've successfully used it on Azure, please let us know on [Discord](https://go.pipelex.com/discord) so we can validate this configuration)
- **Mistral OCR models** - Enable the Mistral backend

These models are not proxied through Pipelex Gateway and require direct configuration of their respective backends with appropriate API keys.

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
# [OPTIONAL] Free Pipelex Gateway API key - Get yours on Discord: https://go.pipelex.com/discord
PIPELEX_GATEWAY_API_KEY=

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

[internal]
enabled = true
# No API key needed for internal/local processing
```

The `${VARIABLE_NAME}` syntax automatically loads values from your `.env` file. Set `enabled = true` to activate a backend, or `false` to disable it.

### Model Specifications

Each backend has its own model specification file in `.pipelex/inference/backends/`:

```toml
# openai.toml
default_sdk = "openai"

[gpt-4o-mini]
model_id = "gpt-4o-mini"
inputs = ["text", "images"]
outputs = ["text", "structured"]
costs = { input = 0.15, output = 0.6 }

[gpt-4-turbo]
model_id = "gpt-4-turbo"
inputs = ["text"]
outputs = ["text", "structured"]
costs = { input = 10.0, output = 30.0 }

[gpt-image-1]
model_id = "gpt-image-1"
inputs = ["text"]
outputs = ["image"]
costs = { input = 0.04, output = 0.0 }
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

The Pipelex Gateway's model specs are fetched from Pipelex servers rather than read from a local file, and there the same rule is applied leniently: a header-shaped key whose name and value the wire can carry becomes a header, and any other unknown key — including a header-shaped one whose value is not a string, or whose name or value HTTP would refuse — is dropped instead of failing the boot, since a served config can legitimately be newer or older than the client reading it.

`endpoint_path` is a declared model-spec field, not a header: it names the provider-side route for models that are called by raw path (the Gateway's image models), and is never sent on the wire.

## Routing Profiles

Routing profiles determine which backend handles specific models. This is where you configure the **Mix & Match approach** (Option C) to optimize your setup. Configure them in `.pipelex/inference/routing_profiles.toml`:

### Profile Examples

**All Pipelex Gateway (Option A):**

Setup:
```bash
# In .env
PIPELEX_GATEWAY_API_KEY="your-pipelex-key"
```

In `.pipelex/inference/routing_profiles.toml`:
```toml
# Which profile to use
active = "all_pipelex_gateway"

[profiles.all_pipelex_gateway]
description = "Use Pipelex Gateway for all its supported models"
default = "pipelex_gateway"
```

**Native Providers Only (Option B):**

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

**Mix & Match (Option C):**

Setup:
```bash
# In .env - combine Pipelex with specific provider keys
PIPELEX_GATEWAY_API_KEY="your-pipelex-key"
OPENAI_API_KEY="your-openai-key"  # For GPT models
FAL_API_KEY="your-fal-key"        # For image generation
```

In `.pipelex/inference/routing_profiles.toml`:
```toml
active = "hybrid"

[profiles.hybrid]
description = "Use Pipelex Gateway for most models, native providers for specific ones"
default = "pipelex_gateway"

[profiles.hybrid.routes]
# Use your own OpenAI key for GPT models (better rate limits)
"gpt-*" = "openai"
# Use your own FAL key for image generation (direct billing)
"flux-*" = "fal"
# All other models use Pipelex Gateway (claude, gemini, mistral, etc.)
```

### Routing System Features

The routing system supports:

- **Exact matches**: `"gpt-4o-mini" = "openai"`
- **Wildcard patterns**: 
  - Prefix: `"gpt-*" = "openai"`
  - Suffix: `"*-turbo" = "openai"`
  - Contains: `"*-vision-*" = "openai"`
- **Default fallback**: `default = "pipelex_gateway"`

### Use Cases for Mix & Match

Common scenarios for hybrid routing:

1. **Cost Optimization**: Use Pipelex Gateway for expensive models, your own keys for cheaper ones
2. **Rate Limits**: Use your own keys for high-volume models to avoid shared rate limits
3. **Gradual Migration**: Start with Pipelex Gateway, gradually move to your own keys as usage grows
4. **Provider Features**: Use native providers for models requiring specific features not proxied through Pipelex Gateway

### Internal Backend (Always Available)

The **internal backend** is a special backend containing software-only models that run locally without requiring AI services. These include models for PDF text extraction, local document parsing, and other processing tasks that don't need external API calls.

Unlike other backends, internal backend models are **always available** regardless of which routing profile you select. This means you can use these models even when your routing profile is focused on a specific AI provider (e.g., `all_pipelex_gateway` or `all_openai`).

This behavior is automatic and requires no additional configuration. To see which models are available from the internal backend, check `.pipelex/inference/backends/internal.toml`.

## Model Deck

The Model Deck is the unified configuration hub for all AI model-related settings, including LLMs, OCR models, and image generation models.

### Aliases

Define user-friendly names that map to model names. Aliases are defined in the deck files (e.g., `.pipelex/inference/deck/1_llm_deck.toml`):

```toml
[llm.aliases]
# Simple aliases map to a single model
best-claude = "claude-4.8-opus"
best-gpt = "gpt-5.5"
best-gemini = "gemini-pro-latest"

# Default aliases (used in presets)
default-general = "claude-4.6-sonnet"
default-premium = "claude-4.8-opus"
default-large-context-text = "gemini-flash-latest"
default-small = "gpt-4o-mini"
```

When using aliases in `.mthds` files or other configurations, prefix them with `@`:

```toml
model = "@best-claude"           # References the best-claude alias
model = "@default-general"       # References the default-general alias
```

### LLM Presets

Presets combine model selection with optimized parameters for specific tasks. Defined in `.pipelex/inference/deck/1_llm_deck.toml`:

```toml
[llm.presets]
# Writing presets
writing-factual = { model = "@default-premium", temperature = 0.1 }
writing-creative = { model = "@default-premium", temperature = 0.9 }

# Retrieval
retrieval = { model = "@default-large-context-text", temperature = 0.1 }

# Engineering
engineering-structured = { model = "@default-premium-structured", temperature = 0.2 }
engineering-code = { model = "@default-premium", temperature = 0.1 }

# Vision
vision = { model = "@default-premium-vision", temperature = 0.5 }
vision-cheap = { model = "@default-small-vision", temperature = 0.5 }
vision-diagram = { model = "@default-premium-vision", temperature = 0.3 }
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
2. `~/.pipelex/inference/<file>_override.toml` — the global override, applied in every project on the machine
3. `{project}/.pipelex/inference/<file>_override.toml` — the project override, which wins

The global override reaches a project that carries its own tracked base, which is the point: one edit under `~/.pipelex/inference/` and every project follows. Deleting the override files restores the shipped default.

A developer who wants a whole machine off the gateway and on Anthropic writes two files once:

```toml
# ~/.pipelex/inference/backends_override.toml
[pipelex_gateway]
enabled = false
```

```toml
# ~/.pipelex/inference/routing_profiles_override.toml
active = "all_anthropic"
```

Enabling a backend and activating a profile that needs it go together: a profile whose default or routes name a backend that is not enabled is refused at boot, and the error names the backend to enable. `pipelex show backends` and `pipelex doctor` report the merged view, so what they print is what runs.

An override leaves a trace. When one was merged, the boot logs which files each document was read from, so a run on an unexpected backend says why in its own log. A file that does not parse is refused the way an invalid document is — as a setup error naming the file, in the boot, in `pipelex init` and in the doctor's Models row — and so is a value where a table was meant, such as `anthropic = false` where `[anthropic]` with `enabled = false` was intended. `pipelex init` keeps writing the base file, but it decides whether the gateway is enabled on the merged document, so a gateway switched on only by an override still gets the terms prompt; and when declining the terms disables the gateway in the base while an override still pins it on, the command says so and names the file to edit.

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
premium-llm = ["claude-4.5-opus", "gemini-3.1-pro", "gpt-5.2"]
small-llm = ["gemini-2.5-flash-lite", "gpt-4o-mini", "claude-3-haiku"]
```

**For Extract** (`.pipelex/inference/deck/x_custom_extract_deck.toml`):

```toml
[extract.waterfalls]
document_extractor = ["azure-document-intelligence", "mistral-document-ai-2505"]
```

When using waterfalls in `.mthds` files, prefix them with `~`:

```toml
model = "~premium-llm"    # Will try claude-4.5-opus, then gemini-3.1-pro, then gpt-5.2
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

You do not have to do anything about that at boot. Pipelex reads the migration history for the `inference/backends/` files, carries the out-of-date ones forward **in memory**, and starts with a warning naming each file:

```
Your configuration is out of date, and pipelex read it as if it had been migrated:
'~/.pipelex/inference/backends/openai.toml'. What the ledger carried forward: Drop
prompting_target from every backend definition. Nothing was written. Run
`pipelex migrate` to bring the files up to date.
```

Nothing has been written at that point, so the warning comes back at the next boot until you run the command:

```bash
pipelex migrate --dry-run   # show what would change in each file, and stop
pipelex migrate             # ask, then rewrite in place
```

What it touches and what it leaves alone:

- **Every `*.toml` directly in `inference/backends/`** — the files this page describes, in both the global `~/.pipelex/` and a project's `.pipelex/`.
- **Not** `inference/backends.toml`, which sits beside that directory rather than in it, and **not** the model deck under `inference/deck/`. The deck has its own `pipelex update`.
- **Not a key you added yourself.** The history only describes keys *we* removed or renamed. An unknown key of your own — a misspelled `maxx_tokens`, an extra header that is not header-shaped — is still an error, and it names the file, the key and what to do. That is deliberate: silently dropping a key you meant to set would change which model you get.
- **Every file it rewrites is copied first**, beside itself, as `<file>.bak.<UTC timestamp>`. Running the command twice is the same as running it once — a file already up to date comes back byte for byte identical.

`pipelex doctor` shows the same thing before anything fails: its **Configuration Migrations** row names every backend file a migration would rewrite, and `pipelex doctor --fix` offers to run it for you.

See [The Migration Ledger](../../migration-ledger.md) for what the history may contain and what it guarantees, and [`pipelex migrate`](../../tools/cli/migrate.md) for the command itself.

## Best Practices

1. **Choosing Your Configuration Approach**:
   - **Starting out?** Use Pipelex Gateway (Option A) to get running quickly
   - **Production deployment?** Consider bringing your own keys (Option B) for direct billing control
   - **Optimizing costs/performance?** Use Mix & Match (Option C) for maximum flexibility
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
