# Inference Backend Configuration

The Inference Backend Configuration System manages how Pipelex handles AI model providers, model routing, and inference settings across LLMs, OCR, and image generation. This unified system provides a flexible and scalable way to configure multiple inference backends and route different types of AI models to the appropriate providers.

## Configuration Approaches

Pipelex supports three flexible approaches for accessing AI models:

### Option A: Pipelex Inference (Optional & Free)

Get a single API key that works with all major providers (OpenAI, Anthropic, Google, Mistral, FAL, and more). This is the **recommended approach for getting started quickly**.

- ✅ Single API key for all providers
- ✅ Simplified configuration
- ✅ Automatic model routing
- ✅ Free on Discord (limited time offer)

### Option B: Bring Your Own Keys

Use your own API keys from individual providers for full control and direct billing. Ideal for production deployments with existing provider relationships.

- ✅ Direct provider relationships
- ✅ Full control over billing
- ✅ No intermediary
- ✅ Support for all provider-specific features

See [Inference Backends](#inference-backends) section below for configuration.

### Option C: Mix & Match (Custom Routing)

Configure custom routing profiles to use your own keys for some models and Pipelex Inference for others. This gives you full flexibility to optimize for cost, performance, or rate limits.

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
    ├── routing_profiles.toml   # Model routing rules
    ├── backends/               # Individual backend model specifications
    │   ├── openai.toml         # OpenAI models (LLMs, image generation)
    │   ├── anthropic.toml      # Anthropic models (LLMs)
    │   ├── bedrock.toml        # AWS Bedrock models (LLMs)
    │   ├── mistral.toml        # Mistral models (LLMs, OCR)
    │   ├── vertexai.toml       # Google Vertex AI models (LLMs)
    │   ├── fal.toml            # FAL models (image generation)
    │   ├── internal.toml       # Internal/local models (OCR)
    │   └── ...
    └── deck/                   # Model deck configurations
        ├── base_deck.toml      # Core aliases and presets
        └── overrides.toml      # Custom overrides
```

## Pipelex Inference (Optional & Free)

Pipelex Inference is a unified inference backend that provides access to all major AI providers through a single API key. This is the **recommended approach for getting started quickly** with Pipelex, and it's **completely optional**.

### Benefits

- **Single API Key**: Access OpenAI, Anthropic, Google, Mistral, FAL, and more with one key
- **Free to Get Started**: Available free on Discord (no credit card required, limited time offer)
- **Simplified Configuration**: No need to manage multiple provider credentials
- **Automatic Routing**: All AI models (LLMs, OCR, image generation) are automatically routed to their respective providers
- **Unified Interface**: Same configuration system for text generation, OCR, and image generation

### Setup

1. **Get your API key:**
   - Visit [https://go.pipelex.com/discord](https://go.pipelex.com/discord) to join our Discord
   - Request your free API key in the appropriate channel
   - No credit card required (limited time offer)

2. **Configure environment variables:**
   ```bash
   # Copy the example environment file
   cp .env.example .env
   
   # Edit .env and add your Pipelex Inference API key
   # PIPELEX_INFERENCE_API_KEY="your-api-key"
   ```

3. **Verify backend configuration:**
   
   The `pipelex_inference` backend should already be enabled in `.pipelex/inference/backends.toml`:
   
   ```toml
   [pipelex_inference]
   enabled = true
   endpoint = "https://inference.pipelex.com/v1"
   api_key = "${PIPELEX_INFERENCE_API_KEY}"
   ```
   
   The environment variable `${PIPELEX_INFERENCE_API_KEY}` will be automatically loaded from your `.env` file.

4. **Verify routing configuration:**
   
   The default routing profile in `.pipelex/inference/routing_profiles.toml` should be set to `pipelex_first`:
   
   ```toml
   active = "pipelex_first"
   
   [profiles.pipelex_first]
   description = "Use Pipelex Inference backend for all its supported models"
   default = "pipelex_inference"
   ```

### Usage

Once configured, all models are available through the unified backend. Use standard model names in your pipelines:

```plx
[pipe.example]
type = "PipeLLM"
model = { model = "claude-4.5-sonnet", temperature = 0.7 }
# Model automatically routed through Pipelex Inference
```

### Model Availability Note

While Pipelex Inference provides access to most AI models through a unified API, certain specialized models require their native backend to be enabled directly:

- **FAL image generation models** (e.g., Flux models) - Enable the FAL backend
- **OpenAI image generation** (`gpt-image-1`) - Enable the OpenAI backend (should also work via Azure OpenAI, but we haven't been able to test this - if you've successfully used it on Azure, please let us know on [Discord](https://go.pipelex.com/discord) so we can validate this configuration)
- **Mistral OCR models** - Enable the Mistral backend

These models are not proxied through Pipelex Inference and require direct configuration of their respective backends with appropriate API keys.

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
# [OPTIONAL] Free Pipelex Inference API key - Get yours on Discord: https://go.pipelex.com/discord
PIPELEX_INFERENCE_API_KEY=

OPENAI_API_KEY=

# AWS Bedrock - For accessing models via Amazon Bedrock
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
default_prompting_target = "openai"

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

## Routing Profiles

Routing profiles determine which backend handles specific models. This is where you configure the **Mix & Match approach** (Option C) to optimize your setup. Configure them in `.pipelex/inference/routing_profiles.toml`:

### Profile Examples

**All Pipelex Inference (Option A):**

Setup:
```bash
# In .env
PIPELEX_INFERENCE_API_KEY="your-pipelex-key"
```

In `.pipelex/inference/routing_profiles.toml`:
```toml
# Which profile to use
active = "pipelex_first"

[profiles.pipelex_first]
description = "Use Pipelex Inference backend for all its supported models"
default = "pipelex_inference"
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
PIPELEX_INFERENCE_API_KEY="your-pipelex-key"
OPENAI_API_KEY="your-openai-key"  # For GPT models
FAL_API_KEY="your-fal-key"        # For image generation
```

In `.pipelex/inference/routing_profiles.toml`:
```toml
active = "hybrid"

[profiles.hybrid]
description = "Use Pipelex for most models, native providers for specific ones"
default = "pipelex_inference"

[profiles.hybrid.routes]
# Use your own OpenAI key for GPT models (better rate limits)
"gpt-*" = "openai"
# Use your own FAL key for image generation (direct billing)
"flux-*" = "fal"
# All other models use Pipelex Inference (claude, gemini, mistral, etc.)
```

### Routing System Features

The routing system supports:

- **Exact matches**: `"gpt-4o-mini" = "openai"`
- **Wildcard patterns**: 
  - Prefix: `"gpt-*" = "openai"`
  - Suffix: `"*-turbo" = "openai"`
  - Contains: `"*-vision-*" = "openai"`
- **Default fallback**: `default = "pipelex_inference"`

### Use Cases for Mix & Match

Common scenarios for hybrid routing:

1. **Cost Optimization**: Use Pipelex Inference for expensive models, your own keys for cheaper ones
2. **Rate Limits**: Use your own keys for high-volume models to avoid shared rate limits
3. **Gradual Migration**: Start with Pipelex Inference, gradually move to your own keys as usage grows
4. **Provider Features**: Use native providers for models requiring specific features not proxied through Pipelex Inference

## Model Deck

The Model Deck is the unified configuration hub for all AI model-related settings, including LLMs, OCR models, and image generation models.

### Aliases

Define user-friendly names that map to model names in `.pipelex/inference/deck/base_deck.toml`:

```toml
[aliases]
# LLM aliases
base-claude = "claude-4.5-sonnet"
base-gpt = "gpt-5"
base-gemini = "gemini-2.5-flash"
base-mistral = "mistral-medium"
smart_llm = [
    "claude-4.5-sonnet",
    "claude-4.1-opus",
    "claude-4.5-sonnet",
    "gpt-5",
    "gemini-2.5-pro",
]

# Aliases can also define fallback chains
llm_to_engineer = { model = "smart_llm", temperature = 0.2 }
```

### LLM Presets

Presets combine model selection with optimized parameters for specific tasks:

```toml
[llm.presets]
# General purpose presets
cheap_llm_for_text = { model = "cheap_llm_for_text", temperature = 0.5 }
cheap_llm_for_object = { model = "cheap_llm_for_object", temperature = 0.5 }

# Task-specific presets
llm_for_creative_writing = { model = "claude-4.5-sonnet", temperature = 0.9 }
llm_to_extract_invoice = { model = "claude-4.5-sonnet", temperature = 0.1 }
llm_for_complex_reasoning = { model = "base-claude", temperature = 1 }

### OCR Presets

OCR presets combine OCR model selection with optimized parameters:

```toml
[extract.presets]
# General purpose OCR
extract_text_from_visuals = { ocr_handle = "mistral-ocr", max_nb_images = 100, image_min_size = 50 }
extract_text_from_pdf = { model = "pypdfium2-extract-text", max_nb_images = 100, image_min_size = 50 }
```

### Image Generation Presets

Image generation presets combine model selection with generation parameters:

```toml
[img_gen.presets]
# General purpose image generation
gen_image_basic = { model = "base-img-gen", quality = "medium", guidance_scale = 7.5, is_moderated = true, safety_tolerance = 3 }
gen_image_fast = { model = "fast-img-gen", nb_steps = 4, guidance_scale = 5.0, is_moderated = true, safety_tolerance = 3 }
gen_image_high_quality = { model = "best-img-gen", quality = "high", guidance_scale = 8.0, is_moderated = true, safety_tolerance = 3 }
```

### Default Choices

Set default models for different types of AI operations:

```toml
[llm.choice_defaults]
for_text = "cheap_llm_for_text"
for_object = "cheap_llm_for_object"

[extract]
choice_default = "extract_text_from_visuals"

[img_gen]
choice_default = "gen_image_basic"
```

## Customization

### Local Overrides

Use `.pipelex/inference/deck/overrides.toml` for project-specific customizations:

```toml
# Override specific presets
[llm.presets]
llm_to_extract_invoice = { model = "gpt-4o-mini", temperature = 0.2 }

[extract.presets]
my_custom_extract = { ocr_handle = "mistral-ocr", max_nb_images = 5 }

[img_gen.presets]
my_custom_img_gen = { model = "flux-dev", quality = "medium" }

# Add custom aliases
[aliases]
my_custom_llm = "claude-3-sonnet"
my_custom_extract = "pypdfium2-extract-text"
my_custom_img_gen = "base-img-gen"
```

### Adding New Backends

To add a new backend:

1. Add backend configuration to `backends.toml`
2. Create model specification file in `backends/` directory
3. Update routing profile if needed

## Loading Process

The system loads configurations in this order:

1. **Load Backends**: Read `backends.toml` to get enabled backends
2. **Load Model Specs**: For each backend, load model specifications (LLMs, OCR models, image generation models)
3. **Load Routing Profiles**: Read routing rules and identify active profile
4. **Build Model Deck**: 
   - Apply routing rules to determine backend for each model across all AI capabilities
   - Load aliases and presets from deck files for LLMs, OCR, and image generation
   - Apply overrides
5. **Finalization**: Validate complete configuration

## Error Handling

Common error types:

- `ModelDeckNotFoundError`: Missing LLM deck configuration files
- `ModelsManagerError`: Issues with model management
- `LLMHandleNotFoundError`: Referenced model or alias not found
- `LLMPresetNotFoundError`: Referenced preset not found

## Best Practices

1. **Choosing Your Configuration Approach**:
   - **Starting out?** Use Pipelex Inference (Option A) to get running quickly
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
   - Use meaningful alias names that describe the use case (e.g., `llm_to_extract_invoice`)
   - Document custom presets and their use cases in your team documentation

5. **Customization**:
   - Use `overrides.toml` for project-specific settings
   - Keep base configurations unchanged to make upgrades easier
   - Version control your custom configurations
   - Share routing profiles and presets across your team
