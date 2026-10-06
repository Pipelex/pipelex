---
title: "Pipe run inputs"
description: "Reference for the `PipeRunInputsError` Pipelex error class."
---

<!-- pipelex:authored -->

# Pipe run inputs

A pipe could not get the inputs it needs to run.

When a pipe starts without a required input, the caller's request or the caller's method left it out: `Live run of PipeSequence 'flow': missing required inputs: topic.` That error is in the `input` domain, so an HTTP surface answers 422, its message survives STRICT disclosure, and its next step names the inputs to provide.

An input whose resource the pipe cannot use (a local file that does not exist) raises it too, but that message names the path as resolved on the host running the method, so it carries no domain and is redacted under STRICT disclosure, as it is when raised from any other place.

| Field | Value |
|---|---|
| `error_type` | `PipeRunInputsError` |
| `title` | Pipe run inputs |
| `type_uri` | `https://docs.pipelex.com/latest/errors/pipe-run-inputs-error/` |
| `error_domain` | _(inherited from parent)_ |
| Defined in | `pipelex.core.pipes.inputs.exceptions` |
| Parent class | [`PipeRunError`](pipe-run-error.md) |

[Back to Error Reference](index.md)
