---
title: "Pipeline input url invalid"
description: "Reference for the `PipelineInputUrlInvalidError` Pipelex error class."
---

<!-- pipelex:generated -->

# Pipeline input url invalid

An Image/Document input carries an http(s) url that does not parse as one.

| Field | Value |
|---|---|
| `error_type` | `PipelineInputUrlInvalidError` |
| `title` | Pipeline input url invalid |
| `type_uri` | `https://docs.pipelex.com/latest/errors/pipeline-input-url-invalid-error/` |
| `error_domain` | _(inherited from parent)_ |
| Defined in | `pipelex.pipeline.exceptions` |
| Parent class | [`PipelineInputContentError`](pipeline-input-content-error.md) |
| `user_action` | `change_input` — Provide a well-formed http(s) URL: a scheme, a host, and no whitespace. |

[Back to Error Reference](index.md)
