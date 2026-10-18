---
title: "pipelex.org.mismatch"
description: "The reference belongs to another organization: what the Pipelex error code pipelex.org.mismatch means, who must act and what to do."
---

# pipelex.org.mismatch

**The reference belongs to another organization**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.org.mismatch` |
| Family | [`pipelex.org`](../../index.md#pipelex-org): Organizations, their members, their API keys and their promo codes. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `403` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A well-formed reference names an organization other than the one the caller acts for.

## What to do

Check which organization the request acts for, and use a reference that belongs to it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Use a `{reference}` of the organization the request acts for, then send the request again. |
| Any other reader | `change_input` | Pass this to the caller, whose `{reference}` belongs to another organization. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The request's `{reference}` belongs to an organization other than the caller's.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `reference` | one of `organization_id`, `storage_uri` | The kind of reference that names another organization: an organization's id or a storage address. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
