---
title: "Configuration left by a former release"
description: "Reference for the `FormerReleaseConfigError` Pipelex error class."
---

<!-- pipelex:generated -->

# Configuration left by a former release

The inference configuration still carries what a former release wrote for the Pipelex Gateway.

| Field | Value |
|---|---|
| `error_type` | `FormerReleaseConfigError` |
| `title` | Configuration left by a former release |
| `type_uri` | `https://docs.pipelex.com/latest/errors/former-release-config-error/` |
| `error_domain` | _(inherited from parent)_ |
| Defined in | `pipelex.migration.exceptions` |
| Parent class | [`PipelexSetupError`](pipelex-setup-error.md) |
| `user_action` | `unknown` — Run 'pipelex migrate' to remove what the former release left; it keeps a copy of each file it changes or removes. From an agent, run 'pipelex-agent migrate --dry-run --format json' to see what the cleanup would remove (its 'former_release' key), show the user, then run 'pipelex-agent migrate --yes'. |

[Back to Error Reference](index.md)
