---
title: "pipelex.catalog.deletion_failed"
description: "The saved method's deletion failed: what the Pipelex error code pipelex.catalog.deletion_failed means, who must act and what to do."
---

# pipelex.catalog.deletion_failed

**The saved method's deletion failed**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.catalog.deletion_failed` |
| Family | [`pipelex.catalog`](../../index.md#pipelex-catalog): Saved methods in an organization's catalog. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `runtime`: nobody could have acted beforehand, so whoever made the call waits, retries or reports the problem |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `yes`: repeating the operation may succeed, after `retry_after` seconds when the problem gives it |
| HTTP status | `503` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A step of the method's deletion failed. Deleting the method again resumes its deletion.

## What to do

Send the delete again. If it keeps failing, report it to whoever runs the runtime.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever made the call, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `retry` | Delete the method '`{method_id}`' again. |
| Any other reader | `retry` | Delete the method '`{method_id}`' again. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The deletion of the method '`{method_id}`' did not complete.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `method_id` | `identifier` | The catalog id of the method. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
