---
title: "Pipe load refusal"
description: "Reference for the `PipeLoadRefusalError` Pipelex error class."
---

<!-- pipelex:generated -->

# Pipe load refusal

Raised by the library load when building one pipe of a bundle raises a refusal of the caller's input that carries no locator of its own. It names the pipe and its file, and bundle validation reports it as an invalid verdict.

| Field | Value |
|---|---|
| `error_type` | `PipeLoadRefusalError` |
| `title` | Pipe load refusal |
| `type_uri` | `https://docs.pipelex.com/latest/errors/pipe-load-refusal-error/` |
| `error_domain` | `input` |
| Defined in | `pipelex.core.pipes.exceptions` |
| Parent class | [`PipelexError`](pipelex-error.md) |

[Back to Error Reference](index.md)
