# Inference Backend Configuration

The Inference Backend Configuration System manages how Pipelex handles AI model providers, model routing, and inference settings across LLMs, OCR, and image generation. This unified system provides a flexible and scalable way to configure multiple inference backends and route different types of AI models to the appropriate providers.

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

## Pipelex Inference

Pipelex Inference is a unified inference backend that provides access to all major LLM providers through a single API key. This is the recommended approach for getting started quickly with Pipelex.

### Benefits

- **Single API Key**: Access OpenAI, Anthropic, Google, Mistral, FAL, and more with one key
- **Simplified Configuration**: No need to manage multiple provider credentials
- **Automatic Routing**: All AI models (LLMs, OCR, image generation) are automatically routed to their respective providers
- **Unified Interface**: Same configuration system for text generation, OCR, and image generation

### Setup

1. Join our Discord community to get your free Pipelex Inference API key (no credit card required, limited time offer):
   - Visit [https://go.pipelex.com/discord](https://go.pipelex.com/discord) to join
   - Request your API key in the appropriate channel once you're in
2. Set the environment variable:
   ```bash
   export PIPELEX_INFERENCE_API_KEY="your-api-key"
   ```
3. Configure in `.pipelex/inference/backends.toml`:
   ```toml
   [pipelex_inference]
   enabled = true
   api_key = "${PIPELEX_INFERENCE_API_KEY}"
   ```

### Usage

Once configured, all models are available through the unified backend. Use standard model names in your pipelines:

```plx
[pipe.example]
type = "PipeLLM"
llm = { llm_handle = "claude-4-sonnet", temperature = 0.7 }
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

Configure backends in `.pipelex/inference/backends.toml`:

```toml
[openai]
enabled = true
api_key = "${OPENAI_API_KEY}"

[anthropic]
enabled = true
api_key = "${ANTHROPIC_API_KEY}"

[mistral]
enabled = true
api_key = "${MISTRAL_API_KEY}"

[fal]
enabled = true
api_key = "${FAL_KEY}"

[internal]
enabled = true
# No API key needed for internal/local processing
```

Set `enabled` to `true` to activate a backend, or `false` to disable it. When a backend is enabled, you must set its corresponding API key as an environment variable.

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

Routing profiles determine which backend handles specific models. Configure them in `.pipelex/inference/routing_profiles.toml`:

```toml
# Which profile to use
active = "all_pipelex"

[profiles.all_pipelex]
description = "Use Pipelex Inference backend for all models"
default = "pipelex_inference"

[profiles.mixed]
description = "Route models to their native providers"
default = "openai"

[profiles.mixed.routes]
"claude-*" = "anthropic"
"gemini-*" = "vertexai"
"mistral-*" = "mistral"
"gpt-*" = "openai"
"gpt-image-*" = "openai"
"flux-*" = "fal"
```

The routing system supports:
- Exact matches
- Wildcard patterns (prefix: `pattern*`, suffix: `*pattern`, contains: `*pattern*`)
- Default fallback

## Model Deck

The Model Deck is the unified configuration hub for all AI model-related settings, including LLMs, OCR models, and image generation models.

### Aliases

Define user-friendly names that map to model names in `.pipelex/inference/deck/base_deck.toml`:

```toml
[aliases]
# LLM aliases
base-claude = "claude-4-sonnet"
base-gpt = "gpt-5"
base-gemini = "gemini-2.5-flash"
base-mistral = "mistral-medium"
smart_llm = [
    "claude-4.5-sonnet",
    "claude-4.1-opus",
    "claude-4-sonnet",
    "gpt-5",
    "gemini-2.5-pro",
]

# OCR aliases
best-ocr = "mistral-ocr"
local-ocr = "pypdfium2-extract-text"

# Image generation aliases
base-img-gen = "flux-pro/v1.1"
best-img-gen = "flux-pro/v1.1-ultra"
fast-img-gen = "fast-lightning-sdxl"

# Aliases can also define fallback chains
llm_to_engineer = { llm_handle = "smart_llm", temperature = 0.2 }
```

### LLM Presets

Presets combine model selection with optimized parameters for specific tasks:

```toml
[llm.presets]
# General purpose presets
cheap_llm_for_text = { llm_handle = "cheap_llm_for_text", temperature = 0.5 }
cheap_llm_for_object = { llm_handle = "cheap_llm_for_object", temperature = 0.5 }

# Task-specific presets
llm_for_creative_writing = { llm_handle = "claude-4-sonnet", temperature = 0.9 }
llm_to_extract_invoice = { llm_handle = "claude-4-sonnet", temperature = 0.1 }
llm_to_reason = { llm_handle = "base-claude", temperature = 1 }

### OCR Presets

OCR presets combine OCR model selection with optimized parameters:

```toml
[ocr.presets]
# General purpose OCR
base_ocr_mistral = { ocr_handle = "mistral-ocr", max_nb_images = 100, image_min_size = 50 }
base_ocr_pypdfium2 = { ocr_handle = "pypdfium2-extract-text", max_nb_images = 100, image_min_size = 50 }
```

### Image Generation Presets

Image generation presets combine model selection with generation parameters:

```toml
[img_gen.presets]
# General purpose image generation
base_img_gen = { img_gen_handle = "base-img-gen", quality = "medium", guidance_scale = 7.5, is_moderated = true, safety_tolerance = 3 }
fast_img_gen = { img_gen_handle = "fast-img-gen", nb_steps = 4, guidance_scale = 5.0, is_moderated = true, safety_tolerance = 3 }
high_quality_img_gen = { img_gen_handle = "best-img-gen", quality = "high", guidance_scale = 8.0, is_moderated = true, safety_tolerance = 3 }
```

### Default Choices

Set default models for different types of AI operations:

```toml
[llm.choice_defaults]
for_text = "cheap_llm_for_text"
for_object = "cheap_llm_for_object"

[ocr]
choice_default = "base_ocr_mistral"

[img_gen]
choice_default = "base_img_gen"
```

## Customization

### Local Overrides

Use `.pipelex/inference/deck/overrides.toml` for project-specific customizations:

```toml
# Override specific presets
[llm.presets]
llm_to_extract_invoice = { llm_handle = "gpt-4o-mini", temperature = 0.2 }

[ocr.presets]
my_custom_ocr = { ocr_handle = "mistral-ocr", max_nb_images = 5 }

[img_gen.presets]
my_custom_img_gen = { img_gen_handle = "flux-dev", quality = "medium" }

# Add custom aliases
[aliases]
my_custom_llm = "claude-3-sonnet"
my_custom_ocr = "pypdfium2-extract-text"
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

1. **Backend Management**:
   - Keep API keys in environment variables
   - Enable only the backends you need
   - Document custom backend configurations

2. **Model Routing**:
   - Use specific routing profiles for different environments
   - Test routing rules before production deployment
   - Consider cost implications when routing models

3. **Presets and Aliases**:
   - Create task-specific presets for consistency
   - Use meaningful alias names
   - Document custom presets and their use cases

4. **Customization**:
   - Use `overrides.toml` for project-specific settings
   - Keep base configurations unchanged
   - Version control your custom configurations

## Validation

Validate your inference configuration:

```bash
# Validate all configurations
pipelex validate all

# Check specific configuration
pipelex validate inference
```

The validation checks:
- Backend connectivity
- Model availability
- Routing consistency
- Preset validity
- Alias resolution
