---
title: "pipelex.codegen.output_conflict"
description: "Codegen will not write there: what the Pipelex error code pipelex.codegen.output_conflict means, who must act and what to do."
---

# pipelex.codegen.output_conflict

**Codegen will not write there**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.codegen.output_conflict` |
| Family | [`pipelex.codegen`](../../index.md#pipelex-codegen): Code generated from a method. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `409` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A file codegen does not own sits at the target, or the target lies outside the output root, is not a file, or is a symbolic link.

## What to do

Point codegen at a directory of its own, or remove what sits at the path, then generate again.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Generate into a directory codegen owns, or move what sits at '`{path}`' out of the way. |
| Any other reader | `change_input` | Pass this to the caller, whose codegen target '`{path}`' holds something codegen will not overwrite. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> Codegen will not write to '`{path}`' (reason: `{reason}`).

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `path` | `identifier` | The path codegen would write. |
| `reason` | one of `unowned_file`, `escapes_root`, `not_a_file`, `symlink` | Why codegen will not write there: a file it does not own sits there, the path lies outside the output root, is not a file, or is a symbolic link. |

## See also

- [Codegen Projections](../../../under-the-hood/codegen-projections.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
