---
title: "pipelex.connector.tool_not_in_toolset"
description: "The tool is not in the connector's toolset: what the Pipelex error code pipelex.connector.tool_not_in_toolset means, who must act and what to do."
---

# pipelex.connector.tool_not_in_toolset

**The tool is not in the connector's toolset**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.connector.tool_not_in_toolset` |
| Family | [`pipelex.connector`](../../index.md#pipelex-connector): The toolsets a method's connectors offer a model. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `method`: the method's author acts, by changing the method |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `422` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A model called a tool that the method's connector toolset does not hold, so the runtime refused the call.

## What to do

Compare the tool with those `params.available` lists, then add it to the toolset or steer the prompt away from it.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the method's author, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_method` | Add the tool '`{tool}`' to the method's toolset, or steer the prompt away from it, then run the method again. |
| Any other reader | `contact_owner` | Ask the method's owner to add the tool '`{tool}`' to its toolset. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> A model asked for the tool '`{tool}`', which the method's toolset does not hold.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `tool` | `identifier` | The tool the model asked for. |
| `available` | list of `identifier` | The tools the toolset holds. |

## See also

- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
