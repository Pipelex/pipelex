---
title: "Failure Classification"
description: "How Pipelex classifies every inference failure into a category that drives retry decisions and reaches you in the error output."
---

# Failure Classification

Whichever path runs, every inference failure is classified the moment it happens. The classification is what Tier 2 acts on, and it is what reaches you in the error output.

| Category | Meaning | Retried by Temporal? |
|----------|---------|----------------------|
| `transient` | A brief, self-correcting failure (rate limit, 5xx, connection/timeout) | ✅ Yes |
| `configuration` | The setup is wrong (bad API key, missing backend) | ❌ No |
| `content` | The input or prompt is wrong (content-policy violation) | ❌ No |
| `capacity` | Account quota or billing exhausted | ❌ No |
| `ambiguous` | Outcome unknown — the call may have committed | ❌ No |
| `unknown` | Could not classify | ❌ No |

Only `transient` failures are worth retrying — re-running a call that failed because your API key is wrong just wastes time and money. On the [durable path](durable-execution.md), the activity retry policy uses exactly this signal: a `transient` failure retries, every other category fails fast.

For the full mechanics of how errors are classified, carried, and reported, see [Error Model](../under-the-hood/error-model.md).
