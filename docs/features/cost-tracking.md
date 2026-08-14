---
title: Cost Tracking & Reporting
description: "Track inference costs across your Pipelex pipelines. Monitor spending per model, per step, and per run with built-in console reporting and CSV export."
---

# Cost Tracking & Reporting

Automatic cost tracking for every AI operation in your methods.

## Overview

Pipelex automatically tracks token usage and calculates costs for every LLM call, extraction operation, and image generation. Stay informed about your AI spend at the method, pipe, and operation level.

## Console Reporting

Real-time cost information displayed in the console during pipeline execution. Each inference call reports its token usage and estimated cost, with a summary total at the end of the run.

## CSV Export

Export detailed cost reports as CSV files for analysis, billing, and audit trails. Each row captures the pipe, model, token counts (input/output), and cost for a single operation.

## Rendering Reports When Embedding

Cost is part of the run result: a finished run carries its assembled usage on `pipe_output.tokens_usages`. If you embed Pipelex and want the same end-of-run console table / CSV that the CLI prints, render it in one call from the output:

```python
from pipelex.reporting.cost_report_renderer import render_cost_report_for_output

render_cost_report_for_output(pipe_output)
```

The `--costs` gate is read off the output itself — `tokens_usages` is `None` exactly when cost reporting was off for the run — so you never re-read global config to reconstruct whether costs were on.

## Per-node Attribution in the Run Graph

The same usage stream also lands on the run graph: every node of `pipe_output.graph_spec` carries a `usage` object with its own inference calls, tokens and cost, plus a `subtree_*` rollup covering it and everything below it — so a controller shows what its whole branch spent. The graph's `usage.total` is the run-level rollup.

Cost there is deliberately three-valued: `null` means *unrated* (no rate table — own-GPU models, dry and mock runs), never `0.00`. See [Per-node Usage Attribution](../under-the-hood/per-node-usage-attribution.md) for the invariants a consumer must branch on.

## Custom Reporting

Implement custom reporting backends via the [Reporting Delegate](advanced-customizations.md) injection point. The reporting protocol receives structured cost events during execution, allowing you to push data to your own analytics, dashboards, or billing systems.

For configuration, see [Reporting Configuration](../configuration/config-practical/reporting-config.md).

## Usage on the API Wire

API clients (the `/execute` response and the durable `tokens_usages.json` result artifact) receive token usage in a trimmed, client-facing record shape with a computed per-call `cost` (`null` for unrated models) — not the full internal usage models this page describes. See [TokensUsage Wire Records](../under-the-hood/tokens-usage-wire-records.md).
