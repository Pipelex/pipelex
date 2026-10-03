---
title: "Pipeline input format unsupported"
description: "Reference for the `PipelineInputFormatUnsupportedError` Pipelex error class."
---

<!-- pipelex:generated -->

# Pipeline input format unsupported

A file input is certain to reach a pipe whose model cannot read its format.

| Field | Value |
|---|---|
| `error_type` | `PipelineInputFormatUnsupportedError` |
| `title` | Pipeline input format unsupported |
| `type_uri` | `https://docs.pipelex.com/latest/errors/pipeline-input-format-unsupported-error/` |
| `error_domain` | _(inherited from parent)_ |
| Defined in | `pipelex.pipeline.exceptions` |
| Parent class | [`PipelineInputFormatError`](pipeline-input-format-error.md) |
| `user_action` | `change_input` — Give each file input in a format the model of the pipe that consumes it reads. |

[Back to Error Reference](index.md)
