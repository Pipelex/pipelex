# LLM Configuration Guide

## Overview

Pipelex provides a flexible way to configure and manage your LLM (Large Language Model) integrations through three main concepts:
- LLM Handles
- LLM Presets
- LLM Deck

Those configuration are present in the `pipelex_libraries/llm_deck` directory. Those configuration are usable only if in the directory `pipelex_libraries/llm_deck/overrides.toml` you have the following configuration.

## LLM Handles

An LLM handle is a unique identifier that maps to a specific LLM configuration. It defines:
- The LLM name (e.g., `gpt-4o-mini`, `claude-3-sonnet`)
- The model version
- The platform-specific settings (OpenAI, Anthropic, etc...)

### Example Handle Configuration

```toml
[cogt.llm_config.llm_deck.llm_handle_to_llm_engine_blueprint.gpt-4-turbo]
llm_name = "gpt-4-turbo"
llm_version = "latest"
llm_platform_choice = "openai"
```

For simpler cases where you're using the latest version and default platform:

```toml
claude-3-sonnet = "claude-3-sonnet"
```

## LLM Presets

Presets combine an LLM handle with specific parameters optimized for particular tasks. They help maintain consistency across similar operations and make it easier to switch between different configurations.

### Example Preset Configuration

```toml
# Preset for reasoning tasks
llm_to_reason = { 
    llm_handle = "gpt-4-turbo", 
    temperature = 0.7, 
    max_tokens = "auto" 
}

# Preset for data extraction
llm_to_extract = { 
    llm_handle = "claude-3-sonnet", 
    temperature = 0.1, 
    max_tokens = "auto" 
}
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

### Using LLM Configurations in Pipelines

Here's how to use these configurations in your pipelines:

```toml
[pipe.extract_data]
PipeLLM = "Extract structured data from text"
input = "Text"
output = "Data"
llm = "llm_to_extract"  # Using a preset
prompt = """
Extract the following information...
"""

[pipe.generate_response]
PipeLLM = "Generate a creative response"
input = "Prompt"
output = "Response"
llm = { llm_handle = "gpt-4-turbo", temperature = 0.8, max_tokens = "auto" }  # Direct configuration
prompt = """
Generate a creative response...
"""
```

## Best Practices

1. **Consistent Naming**: Use clear, descriptive names for handles and presets
2. **Task-Specific Presets**: Create presets optimized for specific types of tasks
3. **Version Control**: Keep track of which model versions work best for your use cases
4. **Cost Management**: Consider using different models based on task complexity and cost requirements

---

"Pipelex" is a trademark of Evotis S.A.S.

© 2025 Evotis S.A.S.
