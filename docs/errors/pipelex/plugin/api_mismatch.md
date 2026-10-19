---
title: "pipelex.plugin.api_mismatch"
description: "A plugin targets another plugin API: what the Pipelex error code pipelex.plugin.api_mismatch means, who must act and what to do."
---

# pipelex.plugin.api_mismatch

**A plugin targets another plugin API**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.plugin.api_mismatch` |
| Family | [`pipelex.plugin`](../../index.md#pipelex-plugin): The plugins installed in the runtime. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `operator`: whoever runs the runtime acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `500` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

An installed plugin was built for another version of the plugin contract than the one this runtime implements.

## What to do

If you run the runtime, upgrade the plugin or Pipelex so that both target the same plugin API. Otherwise, report the problem to whoever runs it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever runs the runtime, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `upgrade` | Upgrade the plugin '`{plugin}`', built for the plugin API `{targets_api}`, or Pipelex, which supports the plugin API `{supported_api}`. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> An installed plugin targets a plugin API this runtime does not support.

## Parameters

A parameter is present on every occurrence of the code unless it is marked optional, and one marked operator-only reaches only whoever runs the runtime, never a caller.

| Name | Type | Description |
|---|---|---|
| `plugin` | `identifier` (operator-only) | The plugin. |
| `targets_api` | `integer` (operator-only) | The plugin API version the plugin was built for. |
| `supported_api` | `integer` (operator-only) | The plugin API version this runtime supports. |

## See also

- [Inference Backend Plugins](../../../under-the-hood/inference-backend-plugins.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
