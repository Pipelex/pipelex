---
title: "pipelex.catalog.being_deleted"
description: "The saved method is being deleted: what the Pipelex error code pipelex.catalog.being_deleted means, who must act and what to do."
---

# pipelex.catalog.being_deleted

**The saved method is being deleted**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.catalog.being_deleted` |
| Family | [`pipelex.catalog`](../../index.md#pipelex-catalog): Saved methods in an organization's catalog. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `409` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The method's deletion is in flight, so it can no longer be run, changed or published.

## What to do

Use another method, or save the method again under a new id if it is still wanted.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Use another method, since the method '`{method_id}`' is being deleted. |
| Any other reader | `change_input` | Pass this to the caller, whose request names the method '`{method_id}`', which is being deleted. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The method '`{method_id}`' is being deleted.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `method_id` | `identifier` | The catalog id of the method. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
