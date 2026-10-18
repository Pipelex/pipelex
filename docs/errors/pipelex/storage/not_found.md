---
title: "pipelex.storage.not_found"
description: "A stored file is gone: what the Pipelex error code pipelex.storage.not_found means, who must act and what to do."
---

# pipelex.storage.not_found

**A stored file is gone**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.storage.not_found` |
| Family | [`pipelex.storage`](../../index.md#pipelex-storage): Pipelex's storage addresses and uploads. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `runtime`: nobody could have acted beforehand, so whoever made the call waits, retries or reports the problem |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `500` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A file the run wrote, or that the runtime handed out, is no longer in storage. A caller's own reference to something that does not exist is `input.reference_not_found` instead.

## What to do

Report the problem to whoever runs the runtime, with the run's `pipeline_run_id` when it has one.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever made the call, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `report` | Report this to whoever runs the runtime. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> A file the runtime stored is no longer in its `{scheme}` storage.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `scheme` | one of `local`, `s3`, `gcs`, `memory` | The kind of storage that no longer holds the file. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
