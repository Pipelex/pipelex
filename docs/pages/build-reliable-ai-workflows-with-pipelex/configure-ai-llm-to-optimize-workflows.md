# LLM Settings Guide

## Overview

Pipelex provides a flexible way to configure and manage your LLM (Large Language Model) integrations through three main concepts:

- LLM Handles
- LLM Presets
- LLM Deck

Those configuration are present in the `pipelex_libraries/llm_deck` directory.

## LLM Handles

An LLM handle is a unique identifier that maps to a specific LLM configuration. It defines:

- The LLM name (e.g., `gpt-4o-mini`, `claude-4-sonnet`, `mistral-large`, `gemini-2.5-flash`)
- The model version
- The platform-specific settings (OpenAI, Anthropic, etc...)

### Example Handle Configurations

```toml
[llm_handles]
gpt-4o-2024-11-20 = { llm_name = "gpt-4o", llm_version = "2024-11-20" }
```

There's a much simpler syntax if you want a handle to the latest version and default platform:

```toml
[llm_handles]
best-claude = "claude-4-opus"
```

💡 Defining a llm_handle is alway meant to describe what model it is. Never define a llm_handle to describe what it is for or what it's good at. LLM Settings are for that.

## LLM Settings & LLM Presets

LLM Settings combine an LLM handle with specific parameters optimized for particular tasks. They help maintain consistency across similar operations and make it easier to switch between different configurations.

An LLM Preset is simply a name for a LLM Settings that you have predefined in order to use it in various places.

### Example LLM Preset definitions

```toml
[llm_presets]

llm_to_reason = { 
    llm_handle = "gpt-4-turbo", 
    temperature = 0.7, 
    max_tokens = "auto" 
}

llm_to_extract = { 
    llm_handle = "claude-4-sonnet", 
    temperature = 0.1, 
    max_tokens = "auto" 
}
```

### Using LLM Settings in Pipelines

Here's how to use these configurations in your pipelines:

```plx
[pipe.generate_response]
type = "PipeLLM"
definition = "Generate a creative response"
inputs = { question = "Question" }
output = "Response"
llm = {
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
definition = "Extract structured weather data from text"
inputs = { text = "Text" }
output = "WeatherData"
llm = "llm_to_extract"  # Using a preset
prompt = """
Extract the weather data from this text:

@text
"""
```

## LLM Deck

The LLM deck is your central configuration hub for all LLM-related settings. It's stored in the `pipelex_libraries/llm_deck` directory and consists of:

- `base_llm_deck.toml`: Core LLM configurations
- `overrides.toml`: Custom overrides for specific use cases

### Directory Structure

```bash
pipelex_libraries/
└── llm_deck/
    ├── base_llm_deck.toml
    └── overrides.toml
```


## Best Practices

1. **Consistent Naming**: Use clear, descriptive names for handles and presets
1. **Task-Specific Presets**: Create presets optimized for specific skills and tasks
1. **Cost Management**: Consider using different models based on task complexity and cost requirements
