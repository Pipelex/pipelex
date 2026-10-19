---
title: "pipelex.deployment.custom_code_requires_sandbox"
description: "Custom code needs a sandbox-hosted deployment: what the Pipelex error code pipelex.deployment.custom_code_requires_sandbox means, who must act and what to do."
---

# pipelex.deployment.custom_code_requires_sandbox

**Custom code needs a sandbox-hosted deployment**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.deployment.custom_code_requires_sandbox` |
| Family | [`pipelex.deployment`](../../index.md#pipelex-deployment): The policies of a runner deployment. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `operator`: whoever runs the runtime acts |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `501` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The method ships Python code of its own, and this deployment runs a method's own code only inside the Daytona sandbox, which it does not have.

## What to do

If you run the runtime, configure the Daytona sandbox for custom code. Otherwise, run the method on a runtime that allows its code, or ask its owner for a version without Python.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever runs the runtime, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `fix_configuration` | Configure the Daytona sandbox on this deployment, so that it can run the method's own code. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The method ships Python code in its `{origin}`, and this deployment runs none outside the Daytona sandbox.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `origin` | one of `bundle`, `package` | Where the method ships its code: in its bundle or in its package. |

## See also

- [PipeFunc Requirements](../../../under-the-hood/pipe-func-requirements.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
