---
title: "pipelex.org.not_found"
description: "The organization's resource does not exist: what the Pipelex error code pipelex.org.not_found means, who must act and what to do."
---

# pipelex.org.not_found

**The organization's resource does not exist**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.org.not_found` |
| Family | [`pipelex.org`](../../index.md#pipelex-org): Organizations, their members, their API keys and their promo codes. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `404` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The organization, member, invitation, API key, user or promo record the request names does not exist.

## What to do

Check the identifier the request gives, and list what the organization holds to find the right one.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Name a `{resource}` that exists, then send the request again. |
| Any other reader | `change_input` | Pass this to the caller, whose request names a `{resource}` that does not exist. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The `{resource}` the request names does not exist.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `resource` | one of `organization`, `member`, `invitation`, `api_key`, `user`, `promo_code`, `promo_redemption`, `flag_target` | The kind of resource the request names. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
