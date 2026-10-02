---
title: "Pipeline execution"
description: "Reference for the `PipelineExecutionError` Pipelex error class."
---

<!-- pipelex:authored -->

# Pipeline execution

Wraps any failure that occurred while running a pipeline, reported as its root fault.

The runner raises it around every failure that happens once a run has started, so a host catches one class whatever went wrong. You will rarely see `PipelineExecutionError` as the `error_type` of a report, though: the report names what actually went wrong.

## What the report says

The report of a `PipelineExecutionError` is the report of its **root fault**, the innermost Pipelex error on its cause chain, located at the pipe that failed:

- `error_type`, `title` and `type_uri` are the root fault's. A run whose model was not found reports [`ModelNotFoundError`](model-not-found-error.md), and a run whose parallel branch could not be combined reports `StuffFactoryError`.
- `message` is the root fault's own message, prefixed with the failing pipe and its path from the entry pipe: `Pipe 'summarize' failed (two_steps → summarize): Model handle 'x' was not found in the model deck.` When the entry pipe itself failed, the path is left out: `Pipe 'flow' failed: …`.
- Whether the message is caller-facing is the root fault's call, so under STRICT disclosure a caller-facing root keeps its located message and any other is redacted.
- `error_category`, `retryable`, `model` and `provider` come from the cause chain. `error_domain` does too, with `runtime` as a floor. When nothing on the chain advises an action, `user_action` falls back to `The run failed in pipe '<code>': the message gives the cause.`

A pipe that raised something that is not a Pipelex error is reported as [`PipelexUnexpectedError`](pipelex-unexpected-error.md), whose message names the original exception's class.

The exception itself carries the location structurally: `pipe_code` is the pipe that failed and `pipe_stack` its path from the entry pipe. When the failure was never located, because it happened outside any pipe, or because it arrived from a remote worker as a report that already names its pipe, `pipe_code` is the entry pipe and `pipe_stack` is empty, and the report is taken as it is. A run therefore gives the same report whether it ran in process or on a remote worker.

| Field | Value |
|---|---|
| `error_type` | `PipelineExecutionError` |
| `title` | Pipeline execution |
| `type_uri` | `https://docs.pipelex.com/latest/errors/pipeline-execution-error/` |
| `error_domain` | _(inherited from parent)_ |
| Defined in | `pipelex.pipeline.exceptions` |
| Parent class | [`PipelexError`](pipelex-error.md) |

[Back to Error Reference](index.md)
