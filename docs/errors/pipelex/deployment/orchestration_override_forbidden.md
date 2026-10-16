---
title: "pipelex.deployment.orchestration_override_forbidden"
description: "This deployment does not allow choosing the orchestration mode: what the Pipelex error code pipelex.deployment.orchestration_override_forbidden means, who must act and what to do."
---

# pipelex.deployment.orchestration_override_forbidden

**This deployment does not allow choosing the orchestration mode**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.deployment.orchestration_override_forbidden` |
| Family | [`pipelex.deployment`](../../index.md#pipelex-deployment): The policies of a runner deployment. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `input`: the caller acts, by changing the request or its inputs |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `422` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The deployment's policy fixes the orchestration mode, so a request may not choose one.

## What to do

Leave the orchestration mode out of the request, and let the deployment run it in its own mode.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the caller, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_input` | Send the request without choosing an orchestration mode. |
| Any other reader | `change_input` | Pass this to the caller, whose request chooses an orchestration mode this deployment fixes. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> This deployment does not let a request choose its orchestration mode, and this one asks for '`{requested_mode}`'.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `requested_mode` | `identifier` | The orchestration mode the request asks for. |

## See also

- [Orchestrator Plugins](../../../under-the-hood/orchestrator-plugins.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
