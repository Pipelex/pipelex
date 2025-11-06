# LLM Settings Guide

## Overview

Pipelex provides a flexible way to configure and manage your LLM (Large Language Model) integrations through the inference backend configuration system. 

The system provides three main concepts for LLM configuration:

- LLM Handles (Aliases)
- LLM Presets  
- Model Deck

For complete details about the inference backend configuration system, see the [Inference Backend Configuration](../../home/7-configuration/config-technical/inference-backend-config.md) documentation.

## LLM Handles (Aliases)

An LLM handle can be either:

1. **A direct model name** (like "gpt-4o-mini", "claude-3-sonnet") - automatically available for all models loaded by the inference backend system
2. **An alias** - user-defined shortcuts that map to model names, defined in the `[aliases]` section:

### Example Alias Configurations

```toml
[aliases]
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
[llm_presets]

llm_for_complex_reasoning = { 
    llm_handle = "gpt-4-turbo", 
    temperature = 0.7, 
    max_tokens = "auto" 
}

llm_to_extract = { 
    llm_handle = "claude-4.5-sonnet", 
    temperature = 0.1, 
    max_tokens = "auto" 
}
```

### Using LLM Settings in Pipelines

Here's how to use these configurations in your pipelines:

```plx
[pipe.generate_response]
type = "PipeLLM"
description = "Generate a creative response"
inputs = { question = "Question" }
output = "Response"
model = {
    llm_handle = "gpt-4-turbo",  # Using inline LLM settings
    temperature = 0.8,
    max_tokens = "auto",
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
model = "llm_to_extract"  # Using a preset
prompt = """
Extract the weather data from this text:

@text
"""
```

## Model Deck

The Model Deck is your central configuration hub for all LLM-related settings. It's stored in the `.pipelex/inference/deck/` directory and consists of:

- `base_deck.toml`: Core LLM configurations including aliases and presets
- `overrides.toml`: Custom overrides for specific use cases

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
        ├── base_deck.toml         # Aliases and presets
        └── overrides.toml         # Custom overrides
```



## Best Practices

1. **Consistent Naming**: Use clear, descriptive names for handles and presets
1. **Task-Specific Presets**: Create presets optimized for specific skills and tasks
1. **Cost Management**: Consider using different models based on task complexity and cost requirements
