# LLM Settings Guide

## Overview

Pipelex provides a flexible way to configure and manage your LLM (Large Language Model) integrations through the inference backend configuration system. 

The system provides three main concepts for LLM configuration:

- LLM Handles (Aliases)
- LLM Presets  
- Model Deck

For complete details about the inference backend configuration system, see the [Inference Backend Configuration](../configuration/config-technical/inference-backend-config.md) documentation.

## LLM Handles (Aliases)

An LLM handle can be either:

1. **A direct model name** (like "gpt-4o-mini", "claude-3-sonnet") - automatically available for all models loaded by the inference backend system
2. **An alias** - user-defined shortcuts that map to model names, defined in the `[llm.aliases]` section:

### Example Alias Configurations

```toml
[llm.aliases]
best-claude = "claude-4.1-opus"
best-gemini = "gemini-2.5-pro"
best-mistral = "mistral-large"
base-gpt = "gpt-5"
```

The system first looks for direct model names, then checks aliases if no direct match is found. The system handles model routing through backends automatically.

!!! tip "Alias Naming Convention"
    Defining an alias is always meant to describe what model it is. Never define an alias to describe what it is for or what it's good at. LLM Presets are for that.

## LLM Settings & LLM Presets

LLM Settings combine an LLM handle with specific parameters optimized for particular tasks. They help maintain consistency across similar operations and make it easier to switch between different configurations.

An LLM Preset is simply a name for a LLM Settings that you have predefined in order to use it in various places.

### Example LLM Preset definitions

```toml
[llm.presets]

engineering-structured = {
    model = "@default-premium-structured",
    temperature = 0.2
}

retrieval = {
    model = "@default-large-context-text",
    temperature = 0.1
}
```

### Reasoning Presets

LLM Settings support `reasoning_effort` and `reasoning_budget` parameters for enabling extended reasoning (chain-of-thought / thinking). Here are the built-in reasoning presets:

```toml
[llm.presets]
deep-analysis = { model = "@default-premium", temperature = 0.1, reasoning_effort = "high", description = "Deep reasoning and analysis" }
quick-reasoning = { model = "@default-premium", temperature = 0.3, reasoning_effort = "low", description = "Quick reasoning for simple tasks" }
```

`reasoning_effort` accepts values from `"none"` to `"max"`. For an explicit token budget, use `reasoning_budget` instead (mutually exclusive with `reasoning_effort`). For provider-specific behavior and model examples, see [Reasoning Controls](../under-the-hood/reasoning-controls.md).

### Using LLM Settings in Pipelines

Here's how to use these configurations in your pipelines:

```toml
[pipe.generate_response]
type = "PipeLLM"
description = "Generate a creative response"
inputs = { question = "Question" }
output = "Response"
model = {
    model = "gpt-4-turbo",  # Using inline LLM settings
    temperature = 0.8,
}
prompt = """
Generate a creative response to this question:

@question
"""

[pipe.extract_weather_data]
type = "PipeLLM"
description = "Extract structured weather data from text"
inputs = { text = "Text" }
output = "WeatherData"
model = "$retrieval"  # Using a preset with $ prefix
prompt = """
Extract the weather data from this text:

@text
"""
```

## Model Deck

The Model Deck is your central configuration hub for all LLM-related settings. It's stored in the `.pipelex/inference/deck/` directory and consists of numbered deck files loaded in order:

- `1_llm_deck.toml`: LLM aliases and presets
- `2_img_gen_deck.toml`: Image generation configuration
- `3_extract_deck.toml`: Document extraction configuration
- `4_search_deck.toml`: Search configuration
- `x_custom_extract_deck.toml`: Custom extraction waterfalls/overrides (loaded last)
- `x_custom_llm_deck.toml`: Custom LLM waterfalls/overrides (loaded last)

### Directory Structure

```bash
.pipelex/
└── inference/
    ├── backends.toml              # Backend configurations
    ├── routing_profiles.toml      # Model routing rules
    ├── backends/                  # Individual backend model specs
    │   ├── openai.toml
    │   ├── anthropic.toml
    │   └── ...
    └── deck/                      # Model deck configurations
        ├── 1_llm_deck.toml            # LLM aliases & presets
        ├── 2_img_gen_deck.toml        # Image generation config
        ├── 3_extract_deck.toml        # Document extraction config
        ├── 4_search_deck.toml         # Search config
        ├── x_custom_extract_deck.toml # Custom extraction waterfalls/overrides
        └── x_custom_llm_deck.toml     # Custom LLM waterfalls/overrides
```



## Best Practices

1. **Consistent Naming**: Use clear, descriptive names for handles and presets
1. **Task-Specific Presets**: Create presets optimized for specific skills and tasks
1. **Cost Management**: Consider using different models based on task complexity and cost requirements
