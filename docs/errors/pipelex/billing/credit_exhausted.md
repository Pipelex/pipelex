---
title: "pipelex.billing.credit_exhausted"
description: "The organization is out of credit: what the Pipelex error code pipelex.billing.credit_exhausted means, who must act and what to do."
---

# pipelex.billing.credit_exhausted

**The organization is out of credit**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.billing.credit_exhausted` |
| Family | [`pipelex.billing`](../../index.md#pipelex-billing): Credit and subscriptions: what an organization's plan and balance allow. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `account`: the account's owner acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `402` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The organization's credit is spent. The platform refuses a run before queueing it, and a model call made once the credit has run out is refused as well.

## What to do

Add credit to the organization, or move it to a plan that includes more, then start the run again.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the account's owner, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `check_account` | Add credit to the organization, or move it to a plan that includes more, then try again. |
| Any other reader | `contact_owner` | Ask the account's owner to add credit to the organization. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The organization has no credit left, so the operation was refused.

## Parameters

This code declares no parameters, so its problems carry no `params`.

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
