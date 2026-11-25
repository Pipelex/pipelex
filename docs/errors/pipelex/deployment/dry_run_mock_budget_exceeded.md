---
title: "pipelex.deployment.dry_run_mock_budget_exceeded"
description: "A dry run of the method would build more mock items than this runtime allows: what the Pipelex error code pipelex.deployment.dry_run_mock_budget_exceeded means, who must act and what to do."
---

# pipelex.deployment.dry_run_mock_budget_exceeded

**A dry run of the method would build more mock items than this runtime allows**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.deployment.dry_run_mock_budget_exceeded` |
| Family | [`pipelex.deployment`](../../index.md#pipelex-deployment): The policies of a runner deployment. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `method`: the method's author acts, by changing the method |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `422` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

A validation dry-runs the method, building one mock item for every item a slot holds. Each slot is bounded by the maximum declared item count, and their sum by a budget: many inputs each declaring the maximum, or a batch over a list whose every branch builds another list, multiply what one dry run builds. The method is valid, but this runtime refuses to finish its dry run once the mock items it built would pass the budget. The budget covers one in-process validation or dry run, its mock inputs and its pipes together; a distributed dry run counts each of its worker activities against a budget of its own.

## What to do

Declare fewer items across the method: smaller fixed counts, variable lists `Concept[]` in place of fixed counts, or fewer lists nested in batches. On your own runtime, the budget is `max_dry_run_mock_items` under `[interpreter.method_limits]` in `.pipelex/pipelex.toml`.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, the method's author, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `change_method` | Declare fewer items across the method, such as smaller fixed counts or fewer lists nested in batches, so that a dry run builds at most `{budget}` mock items, then run it again. |
| Any other reader | `contact_owner` | Ask the method's owner to declare fewer items across the method, so that a dry run builds at most `{budget}` mock items. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> A dry run of the method would build more than `{budget}` mock items in all, the most this runtime builds for one dry run, when it reached `{slot}`.

## Parameters

Every parameter is present on every occurrence of the code.

| Name | Type | Description |
|---|---|---|
| `slot` | `caller_text` | What the dry run was about to build when it passed the budget, such as the mock input 'items'. |
| `budget` | `integer` | The most mock items this runtime builds for one dry run. |

## See also

- [Library Configuration](../../../configuration/config-technical/library-config.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
