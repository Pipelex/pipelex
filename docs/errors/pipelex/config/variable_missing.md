---
title: "pipelex.config.variable_missing"
description: "A configuration variable is not set: what the Pipelex error code pipelex.config.variable_missing means, who must act and what to do."
---

# pipelex.config.variable_missing

**A configuration variable is not set**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.config.variable_missing` |
| Family | [`pipelex.config`](../../index.md#pipelex-config): The runtime's own configuration. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `operator`: whoever runs the runtime acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `500` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

An environment variable or a secret that the configuration refers to did not resolve.

## What to do

If you run the runtime, set the variable in its environment or in its secrets provider. Otherwise, report the problem to whoever runs it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever runs the runtime, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `fix_configuration` | Set the `{source}` variable '`{variable}`', then restart the runtime. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> A variable the runtime's configuration refers to is not set.

## Parameters

A parameter is present on every occurrence of the code unless it is marked optional, and one marked operator-only reaches only whoever runs the runtime, never a caller.

| Name | Type | Description |
|---|---|---|
| `variable` | `identifier` (operator-only) | The variable that is not set. |
| `source` | one of `env`, `secret` (operator-only) | Where the configuration reads the variable from: the environment or a secret. |

## See also

- [Secrets Provider Plugins](../../../under-the-hood/secrets-provider-plugins.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
