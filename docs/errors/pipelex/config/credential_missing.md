---
title: "pipelex.config.credential_missing"
description: "An inference backend has no credential: what the Pipelex error code pipelex.config.credential_missing means, who must act and what to do."
---

# pipelex.config.credential_missing

**An inference backend has no credential**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.config.credential_missing` |
| Family | [`pipelex.config`](../../index.md#pipelex-config): The runtime's own configuration. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `operator`: whoever runs the runtime acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `500` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A key or a credential file that an inference backend needs is absent.

## What to do

If you run the runtime, set the backend's key in its environment or its secrets, or disable the backend. Otherwise, report the problem to whoever runs it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever runs the runtime, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `check_credentials` | Set the credential '`{variable}`' of the backend '`{backend}`', then restart the runtime. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> An inference backend of the runtime has no credential.

## Parameters

A parameter is present on every occurrence of the code unless it is marked optional, and one marked operator-only reaches only whoever runs the runtime, never a caller.

| Name | Type | Description |
|---|---|---|
| `backend` | `identifier` (operator-only) | The inference backend that lacks its credential. |
| `variable` | `identifier` (operator-only) | The variable or the file that should hold the credential. |

## See also

- [Inference Backend Plugins](../../../under-the-hood/inference-backend-plugins.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
