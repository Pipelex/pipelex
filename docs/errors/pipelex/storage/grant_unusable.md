---
title: "pipelex.storage.grant_unusable"
description: "The upload grant is spent or expired: what the Pipelex error code pipelex.storage.grant_unusable means, who must act and what to do."
---

# pipelex.storage.grant_unusable

**The upload grant is spent or expired**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.storage.grant_unusable` |
| Family | [`pipelex.storage`](../../index.md#pipelex-storage): Pipelex's storage addresses and uploads. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `runtime`: nobody could have acted beforehand, so whoever made the call waits, retries or reports the problem |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `yes`: repeating the operation may succeed, after `retry_after` seconds when the problem gives it |
| HTTP status | `403` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

An upload grant writes one file, once, before it expires. This one has expired or has already written its file, and a new grant succeeds.

## What to do

Request a new upload grant, and upload the file with it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever made the call, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `retry` | Ask for a new upload grant, then upload the file with it. |
| Any other reader | `retry` | Ask for a new upload grant, then upload the file with it. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The upload grant has expired, or has already written its file.

## Parameters

This code declares no parameters, so its problems carry no `params`.

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
