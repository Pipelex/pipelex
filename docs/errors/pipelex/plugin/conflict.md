---
title: "pipelex.plugin.conflict"
description: "Two plugins claim the same slot: what the Pipelex error code pipelex.plugin.conflict means, who must act and what to do."
---

# pipelex.plugin.conflict

**Two plugins claim the same slot**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.plugin.conflict` |
| Family | [`pipelex.plugin`](../../index.md#pipelex-plugin): The plugins installed in the runtime. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `operator`: whoever runs the runtime acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `500` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

Two installed plugins register the same name, or claim the same process-wide slot.

## What to do

If you run the runtime, keep only one of the two plugins. Otherwise, report the problem to whoever runs it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever runs the runtime, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `fix_configuration` | Uninstall '`{plugin}`' or '`{other_plugin}`', which both claim '`{slot}`', then restart the runtime. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> Two installed plugins claim the same slot.

## Parameters

A parameter is present on every occurrence of the code unless it is marked optional, and one marked operator-only reaches only whoever runs the runtime, never a caller.

| Name | Type | Description |
|---|---|---|
| `plugin` | `identifier` (operator-only) | One of the two plugins. |
| `other_plugin` | `identifier` (operator-only) | The other plugin. |
| `slot` | `identifier` (operator-only) | The name or the process-wide slot both claim. |

## See also

- [Inference Backend Plugins](../../../under-the-hood/inference-backend-plugins.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
