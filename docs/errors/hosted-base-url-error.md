---
title: "Hosted base url"
description: "Reference for the `HostedBaseUrlError` Pipelex error class."
---

<!-- pipelex:generated -->

# Hosted base url

The base URL of the hosted API is not an origin: it carries a path, a query, credentials, or a scheme other than http or https.

| Field | Value |
|---|---|
| `error_type` | `HostedBaseUrlError` |
| `title` | Hosted base url |
| `type_uri` | `https://docs.pipelex.com/latest/errors/hosted-base-url-error/` |
| `error_domain` | `input` |
| Defined in | `pipelex.hosted.exceptions` |
| Parent class | [`HostedRunError`](hosted-run-error.md) |
| `user_action` | `change_input` — Give the hosted API's origin as scheme://host[:port], such as https://api.pipelex.com, in --base-url or PIPELEX_BASE_URL |

[Back to Error Reference](index.md)
