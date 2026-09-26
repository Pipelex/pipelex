---
title: "Pipe router"
description: "Reference for the `PipeRouterError` Pipelex error class."
---

<!-- pipelex:authored -->

# Pipe router

A pipe failed while running: the failure, located at the pipe where it happened.

The pipe router raises it around every failure of the pipe it runs, chained to that failure, with the pipe's code (`pipe_code`) and a snapshot of its path from the entry pipe (`pipe_stack`). A failure that already carries one rises untouched through the routers of the pipe controllers above it, so the location is always the innermost one. An exception that is not a Pipelex error is first turned into a [`PipelexUnexpectedError`](pipelex-unexpected-error.md) whose message names its class.

Like [`PipelineExecutionError`](pipeline-execution-error.md), which wraps it when the run fails, it reports its **root fault** rather than itself: the `error_type`, `title`, `type_uri` and caller-facing flag are the root fault's, and the message is the root fault's own, prefixed with `Pipe '<code>' failed (<path>): `. The classification comes from the cause chain. See [the error model](../under-the-hood/error-model.md#run-failures-the-root-fault-located) for the full rules.

| Field | Value |
|---|---|
| `error_type` | `PipeRouterError` |
| `title` | Pipe router |
| `type_uri` | `https://docs.pipelex.com/latest/errors/pipe-router-error/` |
| `error_domain` | _(inherited from parent)_ |
| Defined in | `pipelex.pipe_run.exceptions` |
| Parent class | [`PipelexError`](pipelex-error.md) |

[Back to Error Reference](index.md)
