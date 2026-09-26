---
title: "Validate bundle"
description: "Reference for the `ValidateBundleError` Pipelex error class."
---

<!-- pipelex:generated -->

# Validate bundle

Raised when a bundle is refused while it is loaded or validated: the invalid verdict, carrying one structured item per refusal in ``validation_errors``. Every refusal of the bundle itself becomes one — every parser error, categorized or not, the factory and pipe-validation errors, one ``dry_run`` item per pipe whose dry run failed, an unknown model (``unknown_model``) and any other refusal of the caller's input — each keeping the locators its raise site had, such as a TOML syntax error's ``line`` and ``column`` and an unresolved concept's ``declared_concepts``, while a failure of the tool or its environment propagates as a no-verdict fault instead.

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
