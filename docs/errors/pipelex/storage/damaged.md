---
title: "pipelex.storage.damaged"
description: "A stored file is damaged: what the Pipelex error code pipelex.storage.damaged means, who must act and what to do."
---

# pipelex.storage.damaged

**A stored file is damaged**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.storage.damaged` |
| Family | [`pipelex.storage`](../../index.md#pipelex-storage): Pipelex's storage addresses and uploads. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `runtime`: nobody could have acted beforehand, so whoever made the call waits, retries or reports the problem |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `500` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

Storage still holds an object under the file's key, but its bytes are not the ones the runtime stored: they do not hash to the key the file is stored under, or they are not the size storage holds them at. A retry reads the same damaged object, and no upload writes over it, so it stays until whoever runs the runtime removes it.

## What to do

Report the problem to whoever runs the runtime, with the `request_id`. Once they have removed the damaged object, upload the file again.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever made the call, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `report` | Report this to whoever runs the runtime. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> A file the runtime stored in its `{scheme}` storage no longer holds the bytes it was stored with.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `scheme` | one of `local`, `s3`, `gcs`, `memory` | The kind of storage that holds the damaged file. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
