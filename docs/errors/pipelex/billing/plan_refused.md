---
title: "pipelex.billing.plan_refused"
description: "The plan's rules refuse this change: what the Pipelex error code pipelex.billing.plan_refused means, who must act and what to do."
---

# pipelex.billing.plan_refused

**The plan's rules refuse this change**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.billing.plan_refused` |
| Family | [`pipelex.billing`](../../index.md#pipelex-billing): Credit and subscriptions: what an organization's plan and balance allow. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `409` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

An administrator's change to an organization's plan that the plan's kind does not allow.

## What to do

Read `params.reason`, then choose another plan, or make the change on a plan that allows it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Request a change the organization's plan allows, then send the request again. |
| Any other reader | `change_input` | Pass this to the caller, whose plan change the plan's rules refuse. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The rules of the organization's plan refuse this change (reason: `{reason}`).

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `reason` | one of `enterprise_is_paid_only`, `plan_not_editable`, `plan_not_enterprise` | Why the change is refused: an enterprise plan is only ever paid, the plan cannot be edited, or the change applies only to an enterprise plan and this one is not. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
