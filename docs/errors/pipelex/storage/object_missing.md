---
title: "pipelex.storage.object_missing"
description: "No file is stored at this link: what the Pipelex error code pipelex.storage.object_missing means, who must act and what to do."
---

# pipelex.storage.object_missing

**No file is stored at this link**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.storage.object_missing` |
| Family | [`pipelex.storage`](../../index.md#pipelex-storage): Pipelex's storage addresses and uploads. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `404` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A signed download link a self-hosted runner handed out names a storage address where its storage holds no file. Resolving an address checks only that the caller may read it, not that a file is stored there, so a link to an address nothing was stored at answers this.

## What to do

Resolve a storage address exactly as a run's results or an upload returned it, and fetch the link the answer gives before it expires.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Resolve a storage address that a run or an upload returned, then fetch the link the answer gives. |
| Any other reader | `change_input` | Pass this to the caller, whose link names a storage address where no file is stored. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> No file is stored at the storage address this link names.

## Parameters

This code declares no parameters, so its problems carry no `params`.

## See also

- [API Server](../../../api-server/index.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
