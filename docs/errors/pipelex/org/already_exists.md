---
title: "pipelex.org.already_exists"
description: "The organization's resource already exists: what the Pipelex error code pipelex.org.already_exists means, who must act and what to do."
---

# pipelex.org.already_exists

**The organization's resource already exists**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.org.already_exists` |
| Family | [`pipelex.org`](../../index.md#pipelex-org): Organizations, their members, their API keys and their promo codes. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `409` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A member, an invitation, a promo code and an API key's name are each unique, and the one the request gives is taken.

## What to do

Use the one that exists, or choose another name, code or address.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Use the `{resource}` that exists, or choose another, then send the request again. |
| Any other reader | `change_input` | Pass this to the caller, whose `{resource}` already exists. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The `{resource}` the request would create already exists.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `resource` | one of `member`, `invitation`, `promo_code`, `api_key_label` | The kind of resource that already exists. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
