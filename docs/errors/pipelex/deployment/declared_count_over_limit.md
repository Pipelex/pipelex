---
title: "pipelex.deployment.declared_count_over_limit"
description: "The method declares more items than this runtime allows: what the Pipelex error code pipelex.deployment.declared_count_over_limit means, who must act and what to do."
---

# pipelex.deployment.declared_count_over_limit

**The method declares more items than this runtime allows**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.deployment.declared_count_over_limit` |
| Family | [`pipelex.deployment`](../../index.md#pipelex-deployment): The policies of a runner deployment. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `method`: the method's author acts, by changing the method |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `422` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A method declares a fixed number of items with `Concept[N]` on an input or an output, or with `nb_output` on a controller step, and a dry run builds one mock item per declared item. Each runtime bounds that number: a local runtime by its configuration, the hosted plane by the caller's plan. The method is valid, but this runtime refuses to load it for a validation or a run while one of its counts passes that bound.

## What to do

Declare fewer items for the slot `params.slot` names, such as a variable list `Concept[]` in place of a fixed count, or raise the limit: on the hosted plane by moving to a plan that allows more, on your own runtime with `max_declared_item_count` under `[interpreter.method_limits]` in `.pipelex/pipelex.toml`.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the method's author, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_method` | Declare at most `{limit}` items for `{slot}`, or run the method under a plan or a configuration that allows more, then run it again. |
| Any other reader | `contact_owner` | Ask the method's owner to declare at most `{limit}` items for `{slot}`, or the account's owner to move to a plan that allows more. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The method declares `{count}` items for `{slot}`, and this runtime allows at most `{limit}` items for one slot.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `slot` | `caller_text` | Where the method declares the count, such as the input 'items' of the pipe 'summarize'. |
| `count` | `integer` | The number of items the method declares there. |
| `limit` | `integer` | The most items this runtime allows for one slot. |

## See also

- [Library Configuration](../../../configuration/config-technical/library-config.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
