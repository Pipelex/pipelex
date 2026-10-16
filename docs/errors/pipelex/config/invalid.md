---
title: "pipelex.config.invalid"
description: "The runtime's configuration is invalid: what the Pipelex error code pipelex.config.invalid means, who must act and what to do."
---

# pipelex.config.invalid

**The runtime's configuration is invalid**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.config.invalid` |
| Family | [`pipelex.config`](../../index.md#pipelex-config): The runtime's own configuration. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `operator`: whoever runs the runtime acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `500` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A configuration file or setting parsed, but does not validate.

## What to do

If you run the runtime, read its logs for the file and the setting, and correct them; `pipelex doctor` checks the configuration. Otherwise, report the problem to whoever runs it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever runs the runtime, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `fix_configuration` | Correct the setting '`{setting}`' in the file '`{file}`' of the `{surface}` configuration, then restart the runtime. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The runtime's configuration is invalid, so it cannot serve this request.

## Parameters

A parameter is present on every occurrence of the code unless it is marked optional, and one marked operator-only reaches only whoever runs the runtime, never a caller.

| Name | Type | Description |
|---|---|---|
| `surface` | `identifier` (operator-only) | The part of the configuration at fault, such as the backends, the model deck, the routing, the plugins, the storage, the telemetry, the log sinks, the libraries or the API server's settings. |
| `file` | `identifier` (operator-only) | The configuration file that holds the setting. |
| `setting` | `identifier` (operator-only) | The setting that does not validate. |

## See also

- [Configuration](../../../configuration/index.md)
- [Doctor Command](../../../tools/cli/doctor.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
