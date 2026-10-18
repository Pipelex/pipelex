---
title: "pipelex.storage.grant_mismatch"
description: "The upload differs from its grant: what the Pipelex error code pipelex.storage.grant_mismatch means, who must act and what to do."
---

# pipelex.storage.grant_mismatch

**The upload differs from its grant**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.storage.grant_mismatch` |
| Family | [`pipelex.storage`](../../index.md#pipelex-storage): Pipelex's storage addresses and uploads. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `runtime`: nobody could have acted beforehand, so whoever made the call waits, retries or reports the problem |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `403` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The upload's size, type, metadata or headers differ from what the grant signed. A client that uploads with the grant exactly as it was handed out never meets this.

## What to do

Report the problem to whoever runs the runtime. If you wrote the client that uploads, send the headers the grant lists, unchanged.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever made the call, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `report` | Report this to whoever runs the runtime. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The upload differs from what its grant signed, so storage refused it.

## Parameters

This code declares no parameters, so its problems carry no `params`.

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
