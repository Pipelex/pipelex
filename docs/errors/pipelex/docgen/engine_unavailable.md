---
title: "pipelex.docgen.engine_unavailable"
description: "No document engine prints this here: what the Pipelex error code pipelex.docgen.engine_unavailable means, who must act and what to do."
---

# pipelex.docgen.engine_unavailable

**No document engine prints this here**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.docgen.engine_unavailable` |
| Family | [`pipelex.docgen`](../../index.md#pipelex-docgen): The document engines that print a PipeDocGen step's documents. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `operator`: whoever runs the runtime acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `501` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The engine that prints a PipeDocGen step's format, or a system library it needs, is not installed, declared or enabled in this runtime.

## What to do

If you run the runtime, install and enable the engine. Otherwise, report the problem to whoever runs it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever runs the runtime, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `fix_configuration` | Install or enable the engine '`{engine}`' (`{gap}`), then restart the runtime. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> No document engine prints the format '`{format}`' in this runtime.

## Parameters

A parameter is present on every occurrence of the code unless it is marked optional, and one marked operator-only reaches only whoever runs the runtime, never a caller.

| Name | Type | Description |
|---|---|---|
| `engine` | `identifier` (operator-only) | The document engine the step needs. |
| `format` | one of `pdf`, `xlsx`, `docx`, `pptx` | The format the step prints. |
| `gap` | `identifier` (operator-only) | What is missing: the engine, a system library it needs, its declaration or its enablement. |

## See also

- [Document Engine Plugins](../../../under-the-hood/document-engine-plugins.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
