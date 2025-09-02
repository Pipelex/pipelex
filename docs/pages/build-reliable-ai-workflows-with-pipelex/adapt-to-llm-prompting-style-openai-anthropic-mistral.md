# Prompting Configuration

The `PromptingConfig` class controls how Pipelex handles prompting styles for different LLM targets.

## Configuration Options

```python
class PromptingConfig(ConfigModel):
    default_prompting_style: PromptingStyle
    prompting_styles: Dict[str, PromptingStyle]
```

### Fields

- `default_prompting_style`: The default prompting style to use when none is specified
- `prompting_styles`: Dictionary mapping LLM targets to their specific prompting styles

## Prompting Styles

Each prompting style defines how prompts are formatted and presented to the LLM. The style can be customized per LLM target to optimize performance and ensure compatibility.

## Example Configuration

```plx
[pipelex.prompting_config]
default_prompting_style = "chat"

[pipelex.prompting_config.prompting_styles]
gpt4 = "chat"
claude = "instruction"
llama = "completion"
```

## Usage

The configuration provides a method to get the appropriate prompting style:

```python
def get_prompting_style(self, prompting_target: Optional[LLMPromptingTarget] = None) -> Optional[PromptingStyle]:
    if prompting_target:
        return self.prompting_styles.get(prompting_target, self.default_prompting_style)
    else:
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
