---
title: "Pipeline input unreachable"
description: "Reference for the `PipelineInputUnreachableError` Pipelex error class."
---

<!-- pipelex:generated -->

# Pipeline input unreachable

An Image/Document input carries an http(s) url the submission-time probe found dead.

| Field | Value |
|---|---|
| `error_type` | `PipelineInputUnreachableError` |
| `title` | Pipeline input unreachable |
| `type_uri` | `https://docs.pipelex.com/latest/errors/pipeline-input-unreachable-error/` |
| `error_domain` | _(inherited from parent)_ |
| Defined in | `pipelex.pipeline.exceptions` |
| Parent class | [`PipelineInputContentError`](pipeline-input-content-error.md) |
| `user_action` | `change_input` — Provide a URL that resolves and serves the resource; the run was refused before it started. |

[Back to Error Reference](index.md)
