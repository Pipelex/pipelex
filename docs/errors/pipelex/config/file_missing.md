---
title: "pipelex.config.file_missing"
description: "A configuration file is missing: what the Pipelex error code pipelex.config.file_missing means, who must act and what to do."
---

# pipelex.config.file_missing

**A configuration file is missing**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.config.file_missing` |
| Family | [`pipelex.config`](../../index.md#pipelex-config): The runtime's own configuration. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `operator`: whoever runs the runtime acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `500` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A configuration file, or a key file, that the runtime needs is absent or cannot be loaded.

## What to do

If you run the runtime, restore the file its logs name, or write the default configuration with `pipelex init`. Otherwise, report the problem to whoever runs it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever runs the runtime, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `fix_configuration` | Create or restore the file '`{file}`' of the `{surface}` configuration, then restart the runtime. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> A configuration file the runtime needs is missing.

## Parameters

A parameter is present on every occurrence of the code unless it is marked optional, and one marked operator-only reaches only whoever runs the runtime, never a caller.

| Name | Type | Description |
|---|---|---|
| `surface` | `identifier` (operator-only) | The part of the configuration the file belongs to. |
| `file` | `identifier` (operator-only) | The file that is missing. |

## See also

- [Init Commands](../../../tools/cli/init.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
