---
title: "Inputs datetime not supported"
description: "Reference for the `InputsDatetimeNotSupportedError` Pipelex error class."
---

<!-- pipelex:generated -->

# Inputs datetime not supported

Raised when a loaded inputs file carries a TOML datetime/date/time value.

| Field | Value |
|---|---|
| `error_type` | `InputsDatetimeNotSupportedError` |
| `title` | Inputs datetime not supported |
| `type_uri` | `https://docs.pipelex.com/latest/errors/inputs-datetime-not-supported-error/` |
| `error_domain` | `input` |
| Defined in | `pipelex.cli.commands.run.exceptions` |
| Parent class | [`PipelexError`](pipelex-error.md) |
| `user_action` | `change_input` — Quote the datetime as a string in the inputs file (e.g. "2026-07-06"); native TOML datetime inputs are not supported yet |

[Back to Error Reference](index.md)
