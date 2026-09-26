---
title: "Dry run"
description: "Reference for the `DryRunError` Pipelex error class."
---

<!-- pipelex:generated -->

# Dry run

Raised when a dry run fails. The validation sweep raises it with one failure per pipe whose dry run failed, located at the innermost failing pipe that is not allowed to fail, so a controller that failed because a pipe it runs failed is reported once, at that pipe. Bundle validation reports each failure as its own ``dry_run`` item, with the error type ``DryRunError``, the pipe's code, domain and source, and a message that keeps the failure's own text only when that text is caller-facing and otherwise names the failure's title.

| Field | Value |
|---|---|
| `error_type` | `DryRunError` |
| `title` | Dry run |
| `type_uri` | `https://docs.pipelex.com/latest/errors/dry-run-error/` |
| `error_domain` | _(inherited from parent)_ |
| Defined in | `pipelex.pipe_run.exceptions` |
| Parent class | [`PipelexError`](pipelex-error.md) |

[Back to Error Reference](index.md)
