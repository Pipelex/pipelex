---
title: Cost Tracking & Reporting
---

# Cost Tracking & Reporting

Automatic cost tracking for every AI operation in your methods.

## Overview

Pipelex automatically tracks token usage and calculates costs for every LLM call, extraction operation, and image generation. Stay informed about your AI spend at the method, pipe, and operation level.

## Console Reporting

Real-time cost information displayed in the console during pipeline execution. Each inference call reports its token usage and estimated cost, with a summary total at the end of the run.

## CSV Export

Export detailed cost reports as CSV files for analysis, billing, and audit trails. Each row captures the pipe, model, token counts (input/output), and cost for a single operation.

## Custom Reporting

Implement custom reporting backends via the [Reporting Delegate](advanced-customizations.md) injection point. The reporting protocol receives structured cost events during execution, allowing you to push data to your own analytics, dashboards, or billing systems.

For configuration, see [Reporting Configuration](../configuration/config-practical/reporting-config.md).
