---
title: "Hosted run outcome unknown"
description: "Reference for the `HostedRunOutcomeUnknownError` Pipelex error class."
---

<!-- pipelex:generated -->

# Hosted run outcome unknown

The request that runs the method was sent, and the connection failed before its answer came back.

| Field | Value |
|---|---|
| `error_type` | `HostedRunOutcomeUnknownError` |
| `title` | Hosted run outcome unknown |
| `type_uri` | `https://docs.pipelex.com/latest/errors/hosted-run-outcome-unknown-error/` |
| `error_domain` | `runtime` |
| Defined in | `pipelex.hosted.exceptions` |
| Parent class | [`HostedRunError`](hosted-run-error.md) |
| `user_action` | `unknown` — A run may have started on the hosted API before the connection failed: check the run history on app.pipelex.com before running again, since running again starts a new, paid run |

[Back to Error Reference](index.md)
