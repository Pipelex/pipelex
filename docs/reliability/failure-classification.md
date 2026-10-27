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

A spent quota and a rate limit both refuse the call, often with the same HTTP status, and they differ only in what cures them: time cures a rate limit, while only a person, adding credit or raising a quota, cures a spent quota. For a failure a gateway relays, Pipelex tells them apart from what the provider says structurally, its status and its error code, and never from the words of its message: a gateway relays every provider's prose, and a throttle's message may well mention a quota, as Azure OpenAI's does by linking to its quota-increase page.

Through a gateway, a `402` is a spent quota, whatever its code says. A `429` is a spent quota only when it carries an error code its provider documents as a spent quota: OpenAI's broad `insufficient_quota`, or one of the billing codes OpenAI's error-code guide names in `error.code`, `credit_balance_exhausted`, `organization_spend_limit_exceeded`, `project_spend_limit_exceeded` and `organization_usage_limit_exceeded`, all of which Azure OpenAI and the OpenAI-compatible providers relay. Every other `429`, including one with no code at all, is a rate limit: it is `transient`, so it is retried, and if it still fails it reaches you as `provider.rate_limited`, with the delay the provider asked for when it gave one.

When the structure says nothing either way, Pipelex reads a `429` as a rate limit on purpose, because the two mistakes do not cost the same. A spent quota read as a rate limit costs a few refused calls, which are not billed, and some waiting before the run fails with the provider's code in its diagnostics. A rate limit read as a spent quota fails the run at once and sends you to add credit that cannot help.

A provider Pipelex calls directly, with your own keys, is read the same way, from the status and the codes that provider documents, and every `429` none of them marks as a spent quota is a rate limit:

- **OpenAI, and every backend reached through the OpenAI SDK**, OpenRouter included: a `402` is a spent quota, and a `429` is one only when its `code` or its `type` is one of the OpenAI codes above. OpenRouter documents one `402` as a wait rather than a spent quota, the one it sends with a `Retry-After` header when the requests already running would overspend a key's budget, and Pipelex reads that one as a rate limit, carrying the delay it asks for.
- **Anthropic**: a `402`, or an error whose type is `billing_error`, is a spent quota, and so is a `429` whose details carry the code `enforced_spend_limit_reached`, the spend cap of an organization or a workspace. Anthropic answers a credit balance too low, or a usage limit you set yourself, with a `400` `invalid_request_error` and no code of its own, so for those alone Pipelex reads the message, and only how it begins: "Your credit balance is too low", "You have reached your specified API usage limits" or "You have reached your specified workspace API usage limits".
- **Google Gemini**: a `402` is a spent quota and every `429` is a rate limit, whatever quota its message names. Gemini gives the delay it wants in the `RetryInfo` detail of its error rather than in a `Retry-After` header, and Pipelex carries that delay just as it would the header.
- **Mistral**: a `402` is a spent quota and every `429` is a rate limit.
- **Amazon Bedrock**: no failure is a spent quota, because Bedrock bills your AWS account and keeps no balance to run out. A `ThrottlingException` is a rate limit, and so is a `ServiceQuotaExceededException`, which arrives as a `400` but which AWS documents as a request to send again later.
- **Every other provider**, Azure OpenAI included, reports no spent quota: its `429` is a rate limit.

For the full mechanics of how errors are classified, carried, and reported, see [Error Model](../under-the-hood/error-model.md).
