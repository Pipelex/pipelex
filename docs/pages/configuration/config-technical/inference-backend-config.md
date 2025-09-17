# Inference Backend Configuration

The Inference Backend Configuration System manages how Pipelex handles LLM providers, model routing, and inference settings. This system provides a flexible and scalable way to configure multiple inference backends and route models to the appropriate providers.

## Overview

The inference backend system is built around four key concepts:

1. **Inference Backends**: Providers of LLM services (OpenAI, Anthropic, Google Vertex AI, etc.)
2. **Model Specs**: Detailed information about specific models available through backends
3. **Routing Profiles**: Rules for selecting which backend should handle specific models
4. **Model Deck**: Unified collection of configured models, aliases, and presets

## Directory Structure

All inference backend configurations are stored in the `.pipelex/inference/` directory:

```
.pipelex/
└── inference/
    ├── backends.toml           # Backend provider configurations
    ├── routing_profiles.toml   # Model routing rules
    ├── backends/               # Individual backend model specifications
    │   ├── openai.toml
    │   ├── anthropic.toml
    │   ├── bedrock.toml
    │   ├── mistral.toml
    │   ├── vertexai.toml
    │   └── ...
    └── deck/                   # Model deck configurations
        ├── base_deck.toml      # Core aliases and presets
        └── overrides.toml      # Custom overrides
```

## Pipelex Inference

Pipelex Inference is a unified inference backend that provides access to all major LLM providers through a single API key. This is the recommended approach for getting started quickly with Pipelex.

### Benefits

- **Single API Key**: Access OpenAI, Anthropic, Google, Mistral, and more with one key
- **Simplified Configuration**: No need to manage multiple provider credentials
- **Automatic Routing**: Models are automatically routed to their respective providers

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

## Inference Backends

Backends represent LLM service providers. Each backend is configured with its endpoint and authentication details.

### Backend Configuration

Configure backends in `.pipelex/inference/backends.toml`:

```toml
[openai]
enabled = true
api_key = "${OPENAI_API_KEY}"

[anthropic]
enabled = true
api_key = "${ANTHROPIC_API_KEY}"

[azure_openai]
enabled = true
endpoint = "${AZURE_API_BASE}"
api_key = "${AZURE_API_KEY}"
api_version = "${AZURE_API_VERSION}"
```

### Model Specifications

Each backend has its own model specification file in `.pipelex/inference/backends/`:

```toml
# openai.toml
[models.gpt-4o-mini]
model_id = "gpt-4o-mini"
sdk = "openai"
inputs = ["text", "images"]
outputs = ["text", "structured"]
costs = { input = 0.00015, output = 0.0006 }
max_tokens = 128000
max_prompt_images = 100

[models.gpt-4-turbo]
model_id = "gpt-4-turbo"
sdk = "openai"
inputs = ["text", "images"]
outputs = ["text", "structured"]
costs = { input = 0.01, output = 0.03 }
max_tokens = 128000
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
```

The routing system supports:
- Exact matches
- Wildcard patterns (prefix: `pattern*`, suffix: `*pattern`, contains: `*pattern*`)
- Default fallback

## Model Deck

The Model Deck is the unified configuration hub for all LLM-related settings.

### Aliases

Define user-friendly names that map to model names in `.pipelex/inference/deck/base_deck.toml`:

```toml
[aliases]
best-claude = "claude-4.1-opus"
best-gemini = "gemini-2.5-pro"
best-mistral = "mistral-large"
base-gpt = "gpt-5"

# Aliases can also define fallback chains
llm_to_engineer = ["claude-4.1-opus", "gemini-2.5-pro"]
```

### LLM Presets

Presets combine model selection with optimized parameters for specific tasks:

```toml
[llm_presets]
# General purpose presets
cheap_llm_for_text = { llm_handle = "gpt-4o-mini", temperature = 0.5 }
cheap_llm_for_object = { llm_handle = "gpt-4o-mini", temperature = 0.5 }

# Task-specific presets
llm_for_creative_writing = { llm_handle = "claude-4-sonnet", temperature = 0.9 }
llm_to_extract = { llm_handle = "claude-4-sonnet", temperature = 0.1 }
llm_to_reason = { llm_handle = "o4-mini", temperature = 1, max_tokens = "auto" }
```

### Default Choices

Set default models for different types of generation:

```toml
[llm_choice_defaults]
for_text = "cheap_llm_for_text"
for_object = "cheap_llm_for_object"
```

## Customization

### Local Overrides

Use `.pipelex/inference/deck/overrides.toml` for project-specific customizations:

```toml
# Override specific presets
[llm_presets]
llm_to_extract = { llm_handle = "gpt-4o-mini", temperature = 0.2 }

# Add custom aliases
[aliases]
my_custom_model = "claude-3-sonnet"
```

### Adding New Backends

To add a new backend:

1. Add backend configuration to `backends.toml`
2. Create model specification file in `backends/` directory
3. Update routing profile if needed

## Loading Process

The system loads configurations in this order:

1. **Load Backends**: Read `backends.toml` to get enabled backends
2. **Load Model Specs**: For each backend, load model specifications
3. **Load Routing Profiles**: Read routing rules and identify active profile
4. **Build Model Deck**: 
   - Apply routing rules to determine backend for each model
   - Load aliases and presets from deck files
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
