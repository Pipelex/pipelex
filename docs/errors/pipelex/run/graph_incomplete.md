---
title: "pipelex.run.graph_incomplete"
description: "The run's graph left usage unattributed: what the Pipelex error code pipelex.run.graph_incomplete means, who must act and what to do."
---

# pipelex.run.graph_incomplete

**The run's graph left usage unattributed**

| | |
|---|---|
| Type | `https://docs.pipelex.com/errors/pipelex.run.graph_incomplete` |
| Family | [`pipelex.run`](../../index.md#pipelex-run): Pipelex's extensions to runs. |
| [Domain](https://mthds.ai/latest/spec/protocol/#domain-who-must-act) | `runtime`: nobody could have acted beforehand, so whoever made the call waits, retries or reports the problem |
| [Retry](https://mthds.ai/latest/spec/protocol/#retry) | `no`: repeating the operation fails the same way |
| HTTP status | `500` |
| Raised as | a problem document, sent as the body of an HTTP response or kept in a run's record |

## What it means

The run itself went on, but its record is incomplete. Every inference call names the graph node it was made for, and some of those nodes never appeared in the run's trace, because their start events were lost. The graph assembled from the trace therefore shows fewer steps, and a smaller cost under each step, than the run spent; the usage of those nodes is counted in the run's total, in its `unattributed` bucket. The runtime reports this to the error trackers of whoever runs it, carrying no content of the run, for a run that reports its failures there: never a dry run, nor a run a validation makes.

## What to do

If you run the runtime, look in the run's trace events, with its `pipeline_run_id`, for the start events of the nodes `params.node_ids` names, and report the run to the maintainers of the Pipelex runtime. The run's outputs and its total cost are not affected.

## Next steps

A problem carries the [step](https://mthds.ai/latest/spec/protocol/#next-steps) aimed at whoever reads it: the first when its reader is the domain's actor, whoever made the call, and the second for any other reader.

| Reader | Kind | Detail |
|---|---|---|
| The domain's actor | `report` | Look in the run's trace events for the start events of the `{node_count}` nodes that never started, then report the run to the maintainers of the Pipelex runtime. |
| Any other reader | `report` | Report this to whoever runs the runtime. |

## Detail

The problem's `detail` is written from this template, filled with the occurrence's parameters:

> The run's graph is incomplete: `{node_count}` of its nodes reported inference usage but never started in its trace, so `{inference_calls}` inference calls were left unattributed.

## Parameters

A parameter is present on every occurrence of the code unless it is marked optional, and one marked operator-only reaches only whoever runs the runtime, never a caller.

| Name | Type | Description |
|---|---|---|
| `node_ids` | list of `identifier` | The ids of the nodes that reported usage but never started in the trace, sorted, at most twenty of them. |
| `node_count` | `integer` | How many nodes reported usage but never started in the trace. |
| `inference_calls` | `integer` | The inference calls those nodes made, which the graph left unattributed. |
| `cost_micro_usd` | `integer` (optional) | The cost of those calls in millionths of a US dollar, rounded, absent when none of them was priced. |

## See also

- [Per-node Usage Attribution](../../../under-the-hood/per-node-usage-attribution.md)
- [The MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/), which describes the members of this page
- [Error Codes](../../index.md), every Pipelex code
