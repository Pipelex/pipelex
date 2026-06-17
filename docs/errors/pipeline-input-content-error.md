---
title: "Pipeline input content"
description: "Reference for the `PipelineInputContentError` Pipelex error class."
---

<!-- pipelex:generated -->

# Pipeline input content

A pipeline input's content reference (url) is unusable.

| Field | Value |
|---|---|
| `error_type` | `PipelineInputContentError` |
| `title` | Pipeline input content |
| `type_uri` | `https://docs.pipelex.com/latest/errors/pipeline-input-content-error/` |
| `error_domain` | `input` |
| Defined in | `pipelex.pipeline.exceptions` |
| Parent class | [`PipelexError`](pipelex-error.md) |
| `user_action` | `change_input` — Provide a valid url on every Image/Document input (https://, data:, pipelex-storage://, or an existing local file when running locally). |

[Back to Error Reference](index.md)
