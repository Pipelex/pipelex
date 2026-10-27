---
title: "Failure Classification"
description: "How Pipelex classifies every inference failure into a category that drives retry decisions and reaches you in the error output."
---

# Failure Classification

Whichever path runs, every inference failure is classified the moment it happens. The classification is what Tier 2 acts on, and it is what reaches you in the error output.

| Category | Meaning | Retried by Temporal? |
|----------|---------|----------------------|
| `transient` | A brief, self-correcting failure (rate limit, 5xx, connection/timeout, transport errors) | ✅ Yes |
| `configuration` | The setup is wrong (bad API key, missing backend) | ❌ No |
| `content` | The input or prompt is wrong (content-policy violation) | ❌ No |
| `capacity` | Account quota or billing exhausted | ❌ No |
| `ambiguous` | Outcome unknown — the call may have committed | ❌ No |
| `unknown` | Could not classify | ❌ No |

Only `transient` failures are worth retrying — re-running a call that failed because your API key is wrong just wastes time and money. On the [durable path](durable-execution.md), the activity retry policy uses exactly this signal: a `transient` failure retries, every other category fails fast.

## A spent quota or a rate limit

A spent quota and a rate limit both refuse the call, often with the same HTTP status, and they differ only in what cures them: time cures a rate limit, while only a person, adding credit or raising a quota, cures a spent quota. Pipelex tells them apart from what the provider says structurally, its status and its error code, and never from the words of its message. A gateway relays every provider's prose, and a throttle's message may well mention a quota: Azure OpenAI's, for one, links to its quota-increase page.

Through a gateway, a `402` is a spent quota, whatever its code says. A `429` is a spent quota only when it carries an error code its provider documents as a spent quota, such as OpenAI's `insufficient_quota`, which Azure OpenAI and the OpenAI-compatible providers relay. Every other `429`, including one with no code at all, is a rate limit: it is `transient`, so it is retried, and if it still fails it reaches you as `provider.rate_limited`, with the delay the provider asked for when it gave one.

When the structure says nothing either way, Pipelex reads a `429` as a rate limit on purpose, because the two mistakes do not cost the same. A spent quota read as a rate limit costs a few refused calls, which are not billed, and some waiting before the run fails with the provider's code in its diagnostics. A rate limit read as a spent quota fails the run at once and sends you to add credit that cannot help. Each provider Pipelex calls directly, with your own keys, has a rule of its own, and some of those still read the provider's wording.

For the full mechanics of how errors are classified, carried, and reported, see [Error Model](../under-the-hood/error-model.md).
