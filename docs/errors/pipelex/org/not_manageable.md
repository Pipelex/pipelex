---
title: "pipelex.org.not_manageable"
description: "The resource cannot be changed this way in its state: what the Pipelex error code pipelex.org.not_manageable means, who must act and what to do."
---

# pipelex.org.not_manageable

**The resource cannot be changed this way in its state**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.org.not_manageable` |
| Family | [`pipelex.org`](../../index.md#pipelex-org): Organizations, their members, their API keys and their promo codes. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `409` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The resource's state refuses the change: a personal or an internal organization, the last administrator of an organization, a subject with no directory identity, or a promo code's cap set below the redemptions it already has.

## What to do

Read `params.reason`, then change the request, for instance by naming another administrator before removing the last one.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Change the resource another way, or bring it into a state that allows this change first. |
| Any other reader | `change_input` | Pass this to the caller, whose change the resource's state does not allow. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The resource cannot be changed this way in its current state (reason: `{reason}`).

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `reason` | `identifier` | What about the resource's state refuses the change. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
