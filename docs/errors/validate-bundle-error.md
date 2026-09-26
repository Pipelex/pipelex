---
title: "Validate bundle"
description: "Reference for the `ValidateBundleError` Pipelex error class."
---

<!-- pipelex:generated -->

# Validate bundle

Raised when a bundle is refused while it is loaded or validated: the invalid verdict, carrying one structured item per refusal in ``validation_errors``. Every refusal of the bundle itself becomes one — the parser, factory and pipe-validation errors, a failing dry run, an unknown model (``unknown_model``) and any other refusal of the caller's input — while a failure of the tool or its environment propagates as a no-verdict fault instead.

| Field | Value |
|---|---|
| `error_type` | `ValidateBundleError` |
| `title` | Validate bundle |
| `type_uri` | `https://docs.pipelex.com/latest/errors/validate-bundle-error/` |
| `error_domain` | `input` |
| Defined in | `pipelex.pipeline.exceptions` |
| Parent class | [`PipelexError`](pipelex-error.md) |
| `user_action` | `change_input` — Check the validation_errors array for specific issues |

[Back to Error Reference](index.md)
