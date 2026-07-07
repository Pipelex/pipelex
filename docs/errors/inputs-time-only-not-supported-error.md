---
title: "Inputs time only not supported"
description: "Reference for the `InputsTimeOnlyNotSupportedError` Pipelex error class."
---

<!-- pipelex:generated -->

# Inputs time only not supported

Raised when a loaded inputs file carries a bare TOML time-of-day value.

| Field | Value |
|---|---|
| `error_type` | `InputsTimeOnlyNotSupportedError` |
| `title` | Inputs time only not supported |
| `type_uri` | `https://docs.pipelex.com/latest/errors/inputs-time-only-not-supported-error/` |
| `error_domain` | `input` |
| Defined in | `pipelex.cli.commands.run.exceptions` |
| Parent class | [`PipelexError`](pipelex-error.md) |
| `user_action` | `change_input` — A time of day alone has no date to attach to. Include the date (e.g. "2026-07-06T12:00:00"), or quote the value as a string |

[Back to Error Reference](index.md)
