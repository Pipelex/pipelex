---
title: "pipelex.deployment.declared_count_over_limit"
description: "More items are asked for one slot than this runtime allows: what the Pipelex error code pipelex.deployment.declared_count_over_limit means, who must act and what to do."
---

# pipelex.deployment.declared_count_over_limit

**More items are asked for one slot than this runtime allows**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.deployment.declared_count_over_limit` |
| Family | [`pipelex.deployment`](../../index.md#pipelex-deployment): The policies of a runner deployment. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `method`: the method's author acts, by changing the method |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `422` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A method declares a fixed number of items with `Concept[N]` on an input or an output, or with `nb_output` on a controller step, and a run may ask for one with `output_multiplicity`. A dry run builds one mock item per item asked for, and a live run asks a model for each. Each runtime bounds that number: a local runtime by its configuration, the hosted plane by the caller's plan. The method is valid, but this runtime refuses to load it for a validation or a run while one of its counts passes that bound, and refuses a run whose `output_multiplicity` passes it.

## What to do

Ask for fewer items for the slot `params.slot` names, such as a variable list `Concept[]` in place of a fixed count, or a smaller `output_multiplicity`, or raise the limit: on the hosted plane by moving to a plan that allows more, on your own runtime with `max_declared_item_count` under `[interpreter.method_limits]` in `.pipelex/pipelex.toml`.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the method's author, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_method` | Ask for at most `{limit}` items for `{slot}`, in the method or in the request, or run it under a plan or a configuration that allows more, then run it again. |
| Any other reader | `contact_owner` | Ask the method's owner to ask for at most `{limit}` items for `{slot}`, or the account's owner to move to a plan that allows more. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> `{count}` items are asked for `{slot}`, more than the `{limit}` this runtime allows for one slot.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `slot` | `caller_text` | Where the count is asked for, such as the input 'items' of the pipe 'summarize'. |
| `count` | `integer` | The number of items asked for there. |
| `limit` | `integer` | The most items this runtime allows for one slot. |

## See also

- [Library Configuration](../../../configuration/config-technical/library-config.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
