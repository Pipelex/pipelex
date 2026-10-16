---
title: "pipelex.catalog.link_conflict"
description: "The directory is linked to another method: what the Pipelex error code pipelex.catalog.link_conflict means, who must act and what to do."
---

# pipelex.catalog.link_conflict

**The directory is linked to another method**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.catalog.link_conflict` |
| Family | [`pipelex.catalog`](../../index.md#pipelex-catalog): Saved methods in an organization's catalog. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | none (client) |
| Raised as | an error a client detects itself, never received from a runner |

## What it means

A local directory records, in its method link, which saved method its files belong to. The link names another method than the one the save targets, cannot be read, or records a sync that did not finish, so the client refuses to save over a draft that is not this directory's.

## What to do

Check which method the directory is linked to, then save to that method or move the files to a directory of their own. Repair or remove a link that cannot be read.

## Next steps

A client that detects this error offers the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Save the directory to the method its link names, or save these files from a directory of their own. |
| Any other reader | `change_input` | Pass this to the caller, whose directory '`{path}`' is linked in a way that stops this save. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The method link of the directory '`{path}`' stops this save to the method '`{method_id}`'.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `method_id` | `identifier` | The catalog id of the method the save targets. |
| `path` | `caller_text` | The local directory whose link stops the save. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
