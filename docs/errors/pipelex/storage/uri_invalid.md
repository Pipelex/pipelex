---
title: "pipelex.storage.uri_invalid"
description: "The storage address is malformed: what the Pipelex error code pipelex.storage.uri_invalid means, who must act and what to do."
---

# pipelex.storage.uri_invalid

**The storage address is malformed**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.storage.uri_invalid` |
| Family | [`pipelex.storage`](../../index.md#pipelex-storage): Pipelex's storage addresses and uploads. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `422` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A `pipelex-storage://` address does not parse, or the storage provider refuses it as a key.

## What to do

Use the storage address exactly as an upload or a run's results returned it, without editing it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Send the storage address exactly as storage returned it, then send the request again. |
| Any other reader | `change_input` | Pass this to the caller, whose request holds a storage address that cannot be parsed. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> A storage address in the request cannot be parsed.

## Parameters

This code declares no parameters, so its problems carry no `params`.

## See also

- [Cloud Storage](../../../features/cloud-storage.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
