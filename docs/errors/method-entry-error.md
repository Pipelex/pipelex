---
title: "Method entry"
description: "Reference for the `MethodEntryError` Pipelex error class."
---

<!-- pipelex:generated -->

# Method entry

Raised when a method has no single pipe to start at, or no single bundle defining the pipe named.

| Field | Value |
|---|---|
| `error_type` | `MethodEntryError` |
| `title` | Method entry |
| `type_uri` | `https://docs.pipelex.com/latest/errors/method-entry-error/` |
| `error_domain` | `input` |
| Defined in | `pipelex.pipeline.exceptions` |
| Parent class | [`PipelexError`](pipelex-error.md) |
| `retryable` | `false` |
| `user_action` | `change_input` — Name the pipe, or declare the method's one main_pipe: in its METHODS.toml, or in one of its bundles |

[Back to Error Reference](index.md)
