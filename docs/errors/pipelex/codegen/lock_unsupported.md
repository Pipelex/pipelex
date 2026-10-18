---
title: "pipelex.codegen.lock_unsupported"
description: "The codegen lock needs a newer Pipelex: what the Pipelex error code pipelex.codegen.lock_unsupported means, who must act and what to do."
---

# pipelex.codegen.lock_unsupported

**The codegen lock needs a newer Pipelex**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.codegen.lock_unsupported` |
| Family | [`pipelex.codegen`](../../index.md#pipelex-codegen): Code generated from a method. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `operator`: whoever runs the runtime acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `500` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The lock was written by a newer Pipelex, in a format this runtime does not read.

## What to do

If you run the runtime, upgrade Pipelex. Otherwise, report the problem to whoever runs it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever runs the runtime, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `upgrade` | Upgrade Pipelex to a version that reads the codegen lock format `{lock_version}`. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The codegen lock was written in the format version `{lock_version}`, which this Pipelex does not read.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `lock_version` | `integer` | The format version the lock was written in. |

## See also

- [Codegen Projections](../../../under-the-hood/codegen-projections.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
