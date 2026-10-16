---
title: "Method entry"
description: "Reference for the `MethodEntryError` Pipelex error class."
---

<!-- pipelex:generated -->

# Method entry

Raised when a method run with no pipe named has no single pipe to start at.

| Field | Value |
|---|---|
| `error_type` | `MethodEntryError` |
| `title` | Method entry |
| `type_uri` | `https://docs.pipelex.com/latest/errors/method-entry-error/` |
| `error_domain` | `input` |
| Defined in | `pipelex.pipeline.exceptions` |
| Parent class | [`PipelexError`](pipelex-error.md) |
| `retryable` | `false` |
| `user_action` | `change_input` — Name the pipe to run, or declare the method's one main_pipe: in its METHODS.toml, or in one of its bundles |

[Back to Error Reference](index.md)
