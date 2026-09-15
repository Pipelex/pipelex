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

## Remote Input Reachability

Before a live run starts, every `Document` or `Image` input that carries an http(s) URL is probed once, in parallel, in the process that accepted the request. The probe is a `HEAD` request, or a one-byte ranged `GET` where the host rejects `HEAD`; it never downloads the resource, and it never runs inside an orchestrator's workflow code.

The probe is deliberately cautious, because it cannot tell a blocked page from a dead one. It refuses the run, with a `PipelineInputUnreachableError` naming the input and the URL, only on an unambiguous signal: the host does not resolve or refuses the connection, or the server answers `404` or `410`. Any other answer, a bot wall's `401`/`403`/`429`, a slow host, or a server error, lets the run proceed with a warning, and the operator that consumes the input fetches it and reports a real failure if there is one. Values a pipe produces mid-run are never probed. A dry run fetches nothing, so it is not probed either.

```toml
[interpreter.pipeline_execution.input_reachability]
is_enabled = true
timeout_seconds = 5.0
```

- `is_enabled`: Set to `false` to skip the probe entirely
- `timeout_seconds`: The budget for each probe; a host that does not answer within it is treated as unknown, not as dead

## Best Practices

- Set a reasonable stack limit based on your pipeline complexity
- Monitor stack usage in complex pipelines

## Related Documentation

- [Executing Pipelines](../../building-methods/pipes/executing-pipelines.md) - How to run pipes and pipelines
- [Pipeline Orchestration](../../features/pipeline-orchestration.md) - Orchestrating complex multi-step pipelines
