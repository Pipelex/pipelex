---
title: "Pipe operator model choice"
description: "Reference for the `PipeOperatorModelChoiceError` Pipelex error class."
---

<!-- pipelex:generated -->

# Pipe operator model choice

Raised by a pipe operator (``PipeLLM``, ``PipeStructure``, ``PipeImgGen``, ``PipeExtract``, ``PipeSearch``) when it is built from its blueprint and a model field names a model the model deck does not define. Bundle validation reports it as an invalid verdict whose item has the error type ``unknown_model``, and a run refuses the bundle with it before any pipe runs.

| Field | Value |
|---|---|
| `error_type` | `PipeOperatorModelChoiceError` |
| `title` | Pipe operator model choice |
| `type_uri` | `https://docs.pipelex.com/latest/errors/pipe-operator-model-choice-error/` |
| `error_domain` | `input` |
| Defined in | `pipelex.core.pipes.exceptions` |
| Parent class | [`PipelexError`](pipelex-error.md) |

[Back to Error Reference](index.md)
