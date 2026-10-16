---
title: "pipelex.erasure.incomplete"
description: "The erasure left data behind: what the Pipelex error code pipelex.erasure.incomplete means, who must act and what to do."
---

# pipelex.erasure.incomplete

**The erasure left data behind**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.erasure.incomplete` |
| Family | [`pipelex.erasure`](../../index.md#pipelex-erasure): The erasure of runs and methods. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `runtime`: nobody could have acted beforehand, so whoever made the call waits, retries or reports the problem |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `yes`: repeating the operation may succeed, after `retry_after` seconds when the problem gives it |
| HTTP status | `503` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A purge of a run, a method, a method's version or a workflow's history did not complete, so part of its data remains. Requesting the erasure again resumes it.

## What to do

Request the erasure again. If it keeps failing, report it to whoever runs the runtime, since data that should be gone remains.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever made the call, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `retry` | Request the erasure of the `{resource}` '`{id}`' again. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The erasure of the `{resource}` '`{id}`' did not complete, and some of its data remains.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `resource` | one of `run`, `method`, `method_version`, `workflow` | What was being erased: a run, a method, a method's version or a workflow's history. |
| `id` | `identifier` | The id of what was being erased. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
