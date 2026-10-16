---
title: "pipelex.catalog.update_conflict"
description: "The saved method changed since it was read: what the Pipelex error code pipelex.catalog.update_conflict means, who must act and what to do."
---

# pipelex.catalog.update_conflict

**The saved method changed since it was read**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.catalog.update_conflict` |
| Family | [`pipelex.catalog`](../../index.md#pipelex-catalog): Saved methods in an organization's catalog. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `409` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

Another write changed the method or its draft between the read the update started from and the update itself, so the update stopped rather than overwrite that change.

## What to do

Read the method again, apply the change to what it holds now, and send the update again.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `refresh` | Read the method '`{method_id}`' again, then apply the change to its current content. |
| Any other reader | `refresh` | Read the method '`{method_id}`' again, then apply the change to its current content. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The method '`{method_id}`' changed after it was read, so the update was not applied.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `method_id` | `identifier` | The catalog id of the method. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
