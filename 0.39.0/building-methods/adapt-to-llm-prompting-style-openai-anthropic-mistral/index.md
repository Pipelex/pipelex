# LLM Prompting Style Configuration

The `PromptingConfig` class controls how Pipelex handles prompting styles for different LLM targets.

## Configuration Options

```python
class PromptingConfig(ConfigModel):
    default_prompting_style: TemplatingStyle
    prompting_styles: dict[str, TemplatingStyle]
```

### Fields

- `default_prompting_style`: The default prompting style to use when none is specified
- `prompting_styles`: Dictionary mapping LLM targets to their specific prompting styles

## Prompting Styles

Each prompting style defines how prompts are formatted and presented to the LLM. The style can be customized per LLM target to optimize performance and ensure compatibility.

## Example Configuration

```toml
[pipelex.prompting_config]
default_prompting_style = { tag_style = "xml" }

[pipelex.prompting_config.prompting_styles]
openai = { tag_style = "ticks" }
anthropic = { tag_style = "xml" }
mistral = { tag_style = "square_brackets" }
gemini = { tag_style = "xml" }
```

## Usage

The configuration provides a method to get the appropriate prompting style:

```python
def get_prompting_style(self, prompting_target: PromptingTarget | None = None) -> TemplatingStyle | None:
    if prompting_target:
        return self.prompting_styles.get(prompting_target, self.default_prompting_style)
    return None
```

This allows for:

- Target-specific prompting styles
- Fallback to default style when no specific style is defined
- Optional prompting when no target is specified

## Best Practices

- Define a sensible default prompting style
- Configure specific styles for LLMs with unique requirements
- Test prompting styles with each LLM target
- Document any special formatting requirements

## Related Documentation

- [PipeLLM › Structuring Method](./pipes/pipe-operators/PipeLLM.md#structuring-method-preliminary-text) - Two-step text-then-structure via `structuring_method = "preliminary_text"`
- [PipeStructure](./pipes/pipe-operators/PipeStructure.md) - Standalone operator that turns text into a structured concept
- [PipeLLM](./pipes/pipe-operators/PipeLLM.md) - Pipe-level prompting and output controls
- [LLM Integration](../features/llm-integration.md) - High-level LLM capability overview
