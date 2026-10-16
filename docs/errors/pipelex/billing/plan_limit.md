---
title: "pipelex.billing.plan_limit"
description: "The account's plan does not allow this: what the Pipelex error code pipelex.billing.plan_limit means, who must act and what to do."
---

# pipelex.billing.plan_limit

**The account's plan does not allow this**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.billing.plan_limit` |
| Family | [`pipelex.billing`](../../index.md#pipelex-billing): Credit and subscriptions: what an organization's plan and balance allow. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `account`: the account's owner acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `409` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The account's plan caps a resource, such as its API keys, and the account already holds as many as the plan allows.

## What to do

Remove something the limit counts, such as an API key no longer in use, or move the account to a plan with a higher limit.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the account's owner, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `check_account` | Check the account's plan, then free some of '`{limit}`' or move to a plan that allows more. |
| Any other reader | `contact_owner` | Ask the account's owner to move to a plan that allows more than `{value}` for '`{limit}`'. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The account's plan allows at most `{value}` for '`{limit}`', and the account already holds that many.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `limit` | `identifier` | What the plan caps, such as the account's API keys. |
| `value` | `integer` | The most the account's plan allows. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
