---
title: "pipelex.storage.upload_refused"
description: "Storage refused the upload: what the Pipelex error code pipelex.storage.upload_refused means, who must act and what to do."
---

# pipelex.storage.upload_refused

**Storage refused the upload**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.storage.upload_refused` |
| Family | [`pipelex.storage`](../../index.md#pipelex-storage): Pipelex's storage addresses and uploads. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `runtime`: nobody could have acted beforehand, so whoever made the call waits, retries or reports the problem |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `403` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

Storage refused an upload for a reason it does not name.

## What to do

Report the problem to whoever runs the runtime, with the status storage answered.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever made the call, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `report` | Report this to whoever runs the runtime. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> Storage refused the upload with the status `{status}`.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `status` | `integer` | The HTTP status storage answered the upload with. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
