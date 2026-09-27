---
title: "Model choice not found"
description: "Reference for the `ModelChoiceNotFoundError` Pipelex error class."
---

<!-- pipelex:generated -->

# Model choice not found

Raised when a model reference names a handle, alias, preset or waterfall the model deck does not define: by the deck check a pipe runs when it is built, and by the deck when a run resolves a reference. When a pipe is built, the pipe operator raises it again as a ``PipeOperatorModelChoiceError`` located on the pipe and the field, so a bundle naming an unknown model is an invalid validation verdict (error type ``unknown_model``), never a failure of the validator.

| Field | Value |
|---|---|
| `error_type` | `ModelChoiceNotFoundError` |
| `title` | Model choice not found |
| `type_uri` | `https://docs.pipelex.com/latest/errors/model-choice-not-found-error/` |
| `error_domain` | `input` |
| Defined in | `pipelex.cogt.exceptions` |
| Parent class | [`CogtError`](cogt-error.md) |

[Back to Error Reference](index.md)
