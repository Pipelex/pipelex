---
title: "pipelex.codegen.drifted"
description: "The generated code has drifted from its method: what the Pipelex error code pipelex.codegen.drifted means, who must act and what to do."
---

# pipelex.codegen.drifted

**The generated code has drifted from its method**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.codegen.drifted` |
| Family | [`pipelex.codegen`](../../index.md#pipelex-codegen): Code generated from a method. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `409` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The artifacts the check read no longer match the method they were generated from.

## What to do

Generate the code again from the current method, and commit what it writes.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Generate the code again from the method, then check it again. |
| Any other reader | `change_input` | Pass this to the caller, whose generated code no longer matches its method. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The generated code no longer matches its method.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `artifacts` | list of `identifier` | The generated artifacts that no longer match. |

## See also

- [Codegen Projections](../../../under-the-hood/codegen-projections.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
