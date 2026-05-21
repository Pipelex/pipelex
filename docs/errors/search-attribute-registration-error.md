---
title: "Search attribute registration"
description: "Reference for the `SearchAttributeRegistrationError` Pipelex error class."
---

<!-- gstack:generated -->

# Search attribute registration

Raised at worker boot when the namespace is reachable but missing a configured custom search attribute. The error message includes both the ``pipelex setup-temporal-namespace`` invocation and the equivalent raw ``temporal operator search-attribute create`` command so operators on either side of the fence can fix the gap.

| Field | Value |
|---|---|
| `error_type` | `SearchAttributeRegistrationError` |
| `title` | Search attribute registration |
| `type_uri` | `https://docs.pipelex.com/latest/errors/search-attribute-registration-error/` |
| `error_domain` | _(inherited from parent)_ |
| Defined in | `pipelex.temporal.exceptions` |
| Parent class | [`TemporalConfigError`](temporal-config-error.md) |

[Back to Error Model overview](../under-the-hood/error-model.md)
