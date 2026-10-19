---
title: "pipelex.billing.subscription_conflict"
description: "The subscription's state does not allow this: what the Pipelex error code pipelex.billing.subscription_conflict means, who must act and what to do."
---

# pipelex.billing.subscription_conflict

**The subscription's state does not allow this**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.billing.subscription_conflict` |
| Family | [`pipelex.billing`](../../index.md#pipelex-billing): Credit and subscriptions: what an organization's plan and balance allow. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `account`: the account's owner acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `409` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A billing action needs an active subscription and the organization has none, or forbids one and the organization already has one.

## What to do

Read the organization's subscription in its billing settings, then subscribe first, or manage the subscription it already has.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the account's owner, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `check_account` | Check the organization's subscription, then take the billing action its state allows. |
| Any other reader | `contact_owner` | Ask the account's owner to check the organization's subscription. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> This billing action is not possible while the organization's subscription is '`{subscription}`'.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `subscription` | one of `none`, `active` | The organization's subscription: it has none, or it has an active one. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
