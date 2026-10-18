---
title: "pipelex.codegen.lock_not_found"
description: "No codegen lock in this directory: what the Pipelex error code pipelex.codegen.lock_not_found means, who must act and what to do."
---

# pipelex.codegen.lock_not_found

**No codegen lock in this directory**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.codegen.lock_not_found` |
| Family | [`pipelex.codegen`](../../index.md#pipelex-codegen): Code generated from a method. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `404` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The directory checked has no `codegen.lock`, so it holds no code generated from a method.

## What to do

Run the check on the directory codegen wrote, or generate the code first.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Check the directory codegen wrote, or generate the code into '`{path}`' first. |
| Any other reader | `change_input` | Pass this to the caller, whose directory '`{path}`' holds no codegen lock. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The directory '`{path}`' holds no codegen lock.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `path` | `identifier` | The directory checked. |

## See also

- [Codegen Projections](../../../under-the-hood/codegen-projections.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
