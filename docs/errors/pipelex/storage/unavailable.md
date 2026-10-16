---
title: "pipelex.storage.unavailable"
description: "Storage is unavailable: what the Pipelex error code pipelex.storage.unavailable means, who must act and what to do."
---

# pipelex.storage.unavailable

**Storage is unavailable**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.storage.unavailable` |
| Family | [`pipelex.storage`](../../index.md#pipelex-storage): Pipelex's storage addresses and uploads. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `runtime`: nobody could have acted beforehand, so whoever made the call waits, retries or reports the problem |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `yes`: repeating the operation may succeed, after `retry_after` seconds when the problem gives it |
| HTTP status | `503` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The storage backend failed a read or a write, which may succeed later.

## What to do

Send the request again after `retry_after` seconds when the problem gives it. If storage keeps failing, report it to whoever runs the runtime.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever made the call, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `retry` | Send the request again after a while. |
| Any other reader | `wait` | Wait, then send the request again. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The `{scheme}` storage failed a read or a write.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `scheme` | one of `local`, `s3`, `gcs`, `memory` | The kind of storage that failed. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
