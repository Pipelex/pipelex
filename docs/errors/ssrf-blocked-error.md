---
title: "Outbound request blocked (SSRF guard)"
description: "Reference for the `SsrfBlockedError` Pipelex error class."
---

<!-- pipelex:generated -->

# Outbound request blocked (SSRF guard)

Raised when an outbound request is refused because the destination host resolved to a disallowed (private / loopback / link-local / metadata) address.

| Field | Value |
|---|---|
| `error_type` | `SsrfBlockedError` |
| `title` | Outbound request blocked (SSRF guard) |
| `type_uri` | `https://docs.pipelex.com/latest/errors/ssrf-blocked-error/` |
| `error_domain` | `input` |
| Defined in | `pipelex.tools.network.exceptions` |
| Parent class | [`SecurityError`](security-error.md) |

[Back to Error Reference](index.md)
