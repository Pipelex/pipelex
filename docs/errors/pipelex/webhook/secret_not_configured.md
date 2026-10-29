---
title: "pipelex.webhook.secret_not_configured"
description: "This runner has no secret to sign webhooks with: what the Pipelex error code pipelex.webhook.secret_not_configured means, who must act and what to do."
---

# pipelex.webhook.secret_not_configured

**This runner has no secret to sign webhooks with**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.webhook.secret_not_configured` |
| Family | [`pipelex.webhook`](../../index.md#pipelex-webhook): The webhooks a caller registers to hear about its runs. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `422` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The request registered callback URLs, and a self-hosted runner signs every call it makes to them with a secret its operator configures, so that the receiver can tell the call is genuine. This runner has none, so it refuses the request before running anything rather than send calls nobody can verify.

## What to do

Send the request without `callback_urls` and read the run's outcome from the response, or ask whoever runs the runner to set the setting `params.setting` names to a `whsec_` secret, which the receiver verifies the calls with.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Send the request without callback URLs, or ask whoever runs this runner to set '`{setting}`' to a signing secret. |
| Any other reader | `change_input` | Pass this to the caller, who asked for webhooks this runner cannot sign until '`{setting}`' holds a signing secret. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> This runner signs no webhooks, because its setting '`{setting}`' holds no signing secret.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `setting` | `identifier` | The setting that holds the runner's webhook signing secret, an environment variable of the runner. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
