---
title: "pipelex.codegen.lock_invalid"
description: "The codegen lock is unreadable: what the Pipelex error code pipelex.codegen.lock_invalid means, who must act and what to do."
---

# pipelex.codegen.lock_invalid

**The codegen lock is unreadable**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.codegen.lock_invalid` |
| Family | [`pipelex.codegen`](../../index.md#pipelex-codegen): Code generated from a method. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `422` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The `codegen.lock` file is malformed, or records a tree that is not safe to write.

## What to do

Restore the lock from version control, or generate the code again, which rewrites it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Restore the lock '`{file}`' from version control, or generate the code again to rewrite it. |
| Any other reader | `change_input` | Pass this to the caller, whose codegen lock '`{file}`' cannot be read. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The codegen lock '`{file}`' cannot be read.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `file` | `identifier` | The lock file. |

## See also

- [Codegen Projections](../../../under-the-hood/codegen-projections.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
