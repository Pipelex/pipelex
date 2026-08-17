---
description: "Set execution parameters for pipes, including stack depth limits and runtime behavior for nested pipe calls in your Pipelex project."
---

# Pipe Run Configuration

The `PipeRunConfig` class controls execution parameters for pipes in Pipelex.

## Configuration Options

```python
class PipeRunConfig(ConfigModel):
    pipe_stack_limit: int
```

### Fields

- `pipe_stack_limit`: Maximum depth of nested pipe executions allowed

## Example Configuration

```toml
[interpreter.pipe_run]
pipe_stack_limit = 20
```

## Stack Limit

The `pipe_stack_limit` prevents infinite recursion in pipe execution by:

- Limiting the depth of nested pipe calls
- Throwing an exception when the limit is exceeded
- Protecting against accidental circular dependencies

## Best Practices

- Set a reasonable stack limit based on your pipeline complexity
- Monitor stack usage in complex pipelines

## Related Documentation

- [Executing Pipelines](../../building-methods/pipes/executing-pipelines.md) - How to run pipes and pipelines
- [Pipeline Orchestration](../../features/pipeline-orchestration.md) - Orchestrating complex multi-step pipelines
