---
title: "pipelex.plugin.not_found"
description: "No plugin provides the configured choice: what the Pipelex error code pipelex.plugin.not_found means, who must act and what to do."
---

# pipelex.plugin.not_found

**No plugin provides the configured choice**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.plugin.not_found` |
| Family | [`pipelex.plugin`](../../index.md#pipelex-plugin): The plugins installed in the runtime. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `operator`: whoever runs the runtime acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `500` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A setting names a storage, a secrets provider, a log sink, an execution mode, an orchestrator or a validator that no installed plugin registers.

## What to do

If you run the runtime, install the plugin that provides the choice, or choose one of those its logs list as available. Otherwise, report the problem to whoever runs it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever runs the runtime, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `fix_configuration` | Install a plugin that provides '`{value}`' for the setting '`{setting}`', or choose a value an installed plugin provides. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> No installed plugin provides a choice the runtime's configuration makes.

## Parameters

A parameter is present on every occurrence of the code unless it is marked optional, and one marked operator-only reaches only whoever runs the runtime, never a caller.

| Name | Type | Description |
|---|---|---|
| `setting` | `identifier` (operator-only) | The setting that makes the choice. |
| `value` | `identifier` (operator-only) | The choice no installed plugin provides. |
| `available` | list of `identifier` (operator-only) | The choices the installed plugins provide. |

## See also

- [Inference Backend Plugins](../../../under-the-hood/inference-backend-plugins.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
