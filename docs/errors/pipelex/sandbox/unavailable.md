---
title: "pipelex.sandbox.unavailable"
description: "The Daytona sandbox could not be started: what the Pipelex error code pipelex.sandbox.unavailable means, who must act and what to do."
---

# pipelex.sandbox.unavailable

**The Daytona sandbox could not be started**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.sandbox.unavailable` |
| Family | [`pipelex.sandbox`](../../index.md#pipelex-sandbox): The Daytona sandbox that runs a method's own code. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `runtime`: nobody could have acted beforehand, so whoever made the call waits, retries or reports the problem |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `yes`: repeating the operation may succeed, after `retry_after` seconds when the problem gives it |
| HTTP status | `503` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A Daytona sandbox, or the local subprocess that stands in for it, could not be provisioned or reached. The method's own code never ran, so running the method again is safe.

## What to do

Run the method again after a while. If the Daytona sandbox keeps failing, report it to whoever runs the runtime.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever made the call, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `retry` | Run the method again after a while. |
| Any other reader | `retry` | Run the method again after a while. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The sandbox that runs the method's code could not be started (backend: `{backend}`), so the code never ran.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `backend` | one of `daytona`, `subprocess` | What could not be started: a Daytona sandbox, or the local subprocess that stands in for it. |

## See also

- [PipeFunc Requirements](../../../under-the-hood/pipe-func-requirements.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
