---
title: "pipelex.org.promo_credit_pending"
description: "The promo credit is pending: what the Pipelex error code pipelex.org.promo_credit_pending means, who must act and what to do."
---

# pipelex.org.promo_credit_pending

**The promo credit is pending**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.org.promo_credit_pending` |
| Family | [`pipelex.org`](../../index.md#pipelex-org): Organizations, their members, their API keys and their promo codes. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `runtime`: nobody could have acted beforehand, so whoever made the call waits, retries or reports the problem |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `502` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The redemption is recorded, but applying its credit failed. A repair sweep applies it later, so redeeming the code again is neither needed nor possible.

## What to do

Wait, then check the organization's credit. If the credit has not arrived after a day, report it to whoever runs the runtime.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever made the call, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `wait` | Wait for the credit to reach the organization, without redeeming the code again. |
| Any other reader | `wait` | Wait for the credit to reach the organization, without redeeming the code again. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The promo code was redeemed, and its credit has not been applied yet.

## Parameters

This code declares no parameters, so its problems carry no `params`.

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
