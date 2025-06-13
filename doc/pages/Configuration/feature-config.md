# Feature Configuration

Configuration section: `[pipelex.feature_config]`

## Overview

The feature configuration controls various optional features in Pipelex. These flags allow you to enable or disable specific functionality as needed.

## Available Flags

### Pipeline Tracking
```toml
is_pipeline_tracking_enabled = false
```
- Controls whether pipeline execution tracking is enabled
- When enabled, tracks the flow and execution of pipelines using by default mermaid chart:
  - View and edit charts at [Mermaid Live Editor](https://mermaid.live)
- Useful for debugging and monitoring pipeline behavior
- Default: `false`

### Activity Tracking
```toml
is_activity_tracking_enabled = false
```
- Controls whether activity tracking is enabled
- When enabled, tracks detailed information about system activities
- Default: `false`

### Reporting
```toml
is_reporting_enabled = true
```
- Controls whether reporting functionality is enabled
- When enabled, generates the cost report of the pipelex execution (LLM costs, OCR costs, etc...)
- Default: `true`

## Example Configuration

```toml
[pipelex.feature_config]
# Enable pipeline tracking for debugging
is_pipeline_tracking_enabled = true

# Disable activity tracking for performance
is_activity_tracking_enabled = false

# Enable reporting for cost monitoring
is_reporting_enabled = true
```

## Best Practices

## Related Topics

- [Pipeline Documentation](../Pipelines/pipelines.md)
- [Reporting Configuration](./reporting-config.md)
- [Monitoring Guide](../Monitoring/monitoring.md)

---

"Pipelex" is a trademark of Evotis S.A.S.

© 2025 Evotis S.A.S. 