---
title: "pipelex.webhook.delivery_failed"
description: "A webhook was not delivered: what the Pipelex error code pipelex.webhook.delivery_failed means, who must act and what to do."
---

# pipelex.webhook.delivery_failed

**A webhook was not delivered**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.webhook.delivery_failed` |
| Family | [`pipelex.webhook`](../../index.md#pipelex-webhook): The webhooks a caller registers to hear about its runs. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `yes`: repeating the operation may succeed, after `retry_after` seconds when the problem gives it |
| HTTP status | `502` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A caller's webhook receiver answered with an error status, or could not be reached. The failure is recorded on the delivery, never on the run, and the platform repeats the delivery on its own.

## What to do

Fix the receiver so that it answers with a `2xx` status. The platform repeats the delivery, so nothing needs to be sent again.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Check that the webhook's receiver is reachable and answers with a success status. |
| Any other reader | `change_input` | Pass this to the caller, whose webhook receiver refused the delivery or could not be reached. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The webhook was not delivered to its receiver (reason: `{reason}`).

## Parameters

A parameter is present on every occurrence of the code unless it is marked optional, and one marked operator-only reaches only whoever runs the runtime, never a caller.

| Name | Type | Description |
|---|---|---|
| `reason` | one of `http_status`, `unreachable` | Why the delivery failed: the receiver answered with an error status, or could not be reached. |
| `receiver_status` | `integer` (optional) | The HTTP status the receiver answered with, when it answered. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
