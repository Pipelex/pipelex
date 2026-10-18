---
title: "pipelex.catalog.not_published"
description: "The saved method has no published version: what the Pipelex error code pipelex.catalog.not_published means, who must act and what to do."
---

# pipelex.catalog.not_published

**The saved method has no published version**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.catalog.not_published` |
| Family | [`pipelex.catalog`](../../index.md#pipelex-catalog): Saved methods in an organization's catalog. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `409` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A bare catalog id names the method's latest published version, and the method has only a draft.

## What to do

Publish the method, or name its draft with the `@draft` suffix.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Publish a version of the method '`{method_id}`', or name its draft as '`{method_id}`@draft', then send the request again. |
| Any other reader | `change_input` | Pass this to the caller, who names the latest published version of the method '`{method_id}`', which has none. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The method '`{method_id}`' has no published version.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `method_id` | `identifier` | The catalog id of the method. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
