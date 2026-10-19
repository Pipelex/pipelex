---
title: "pipelex.plugin.broken"
description: "A plugin failed to load: what the Pipelex error code pipelex.plugin.broken means, who must act and what to do."
---

# pipelex.plugin.broken

**A plugin failed to load**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.plugin.broken` |
| Family | [`pipelex.plugin`](../../index.md#pipelex-plugin): The plugins installed in the runtime. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `operator`: whoever runs the runtime acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `500` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

An installed plugin raised while it was loading or registering, or breaks the rules a plugin's package follows.

## What to do

If you run the runtime, read its logs for the plugin, then upgrade, fix or uninstall it. Otherwise, report the problem to whoever runs it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever runs the runtime, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `fix_configuration` | Fix or uninstall the plugin '`{plugin}`' (`{reason}`), then restart the runtime. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> An installed plugin failed to load.

## Parameters

A parameter is present on every occurrence of the code unless it is marked optional, and one marked operator-only reaches only whoever runs the runtime, never a caller.

| Name | Type | Description |
|---|---|---|
| `plugin` | `identifier` (operator-only) | The plugin that failed. |
| `reason` | `identifier` (operator-only) | What failed: its loading, its registration, or a rule its package breaks. |

## See also

- [Inference Backend Plugins](../../../under-the-hood/inference-backend-plugins.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
