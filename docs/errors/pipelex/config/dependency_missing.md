---
title: "pipelex.config.dependency_missing"
description: "An optional dependency is not installed: what the Pipelex error code pipelex.config.dependency_missing means, who must act and what to do."
---

# pipelex.config.dependency_missing

**An optional dependency is not installed**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.config.dependency_missing` |
| Family | [`pipelex.config`](../../index.md#pipelex-config): The runtime's own configuration. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `operator`: whoever runs the runtime acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `500` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A Python extra, an SDK or a program such as `plxt` that the configuration needs is not installed.

## What to do

If you run the runtime, install Pipelex with the extra its logs name. Otherwise, report the problem to whoever runs it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever runs the runtime, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `fix_configuration` | Install '`{dependency}`', which the extra '`{extra}`' provides, then restart the runtime. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> An optional dependency that the runtime's configuration needs is not installed.

## Parameters

A parameter is present on every occurrence of the code unless it is marked optional, and one marked operator-only reaches only whoever runs the runtime, never a caller.

| Name | Type | Description |
|---|---|---|
| `dependency` | `identifier` (operator-only) | The package, the SDK or the program that is missing. |
| `extra` | `identifier` (operator-only) | The Pipelex extra that provides it. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
