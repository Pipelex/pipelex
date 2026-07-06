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

## Custom Reporting

Implement custom reporting backends via the [Reporting Delegate](advanced-customizations.md) injection point. The reporting protocol receives structured cost events during execution, allowing you to push data to your own analytics, dashboards, or billing systems.

For configuration, see [Reporting Configuration](../configuration/config-practical/reporting-config.md).
