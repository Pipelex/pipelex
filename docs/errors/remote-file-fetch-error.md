---
title: "Remote file could not be fetched"
description: "Reference for the `RemoteFileFetchError` Pipelex error class."
---

<!-- pipelex:generated -->

# Remote file could not be fetched

A remote file an input or a pipe referenced could not be fetched.

| Field | Value |
|---|---|
| `error_type` | `RemoteFileFetchError` |
| `title` | Remote file could not be fetched |
| `type_uri` | `https://docs.pipelex.com/latest/errors/remote-file-fetch-error/` |
| `error_domain` | `input` |
| Defined in | `pipelex.tools.misc.exceptions` |
| Parent class | [`ToolError`](tool-error.md) |
| `user_action` | `change_input` — Check that the URL serves the file to a plain HTTP client, or upload the file and reference it instead. |

[Back to Error Reference](index.md)
