# Feature Configuration

The `FeatureConfig` class controls which features are enabled in Pipelex.

## Configuration Options

```python
class FeatureConfig(ConfigModel):
    is_pipeline_tracking_enabled: bool
    is_activity_tracking_enabled: bool
    is_reporting_enabled: bool
```

### Fields

- `is_pipeline_tracking_enabled`: When true, enables pipeline tracking functionality
- `is_activity_tracking_enabled`: When true, enables activity tracking functionality
- `is_reporting_enabled`: When true, enables the reporting system

## Impact on Dependency Injection

The feature flags directly affect which implementation is used for certain components:

| Feature Flag | When True | When False |
|--------------|-----------|------------|
| `is_pipeline_tracking_enabled` | `PipelineTracker` | `PipelineTrackerNoOp` |
| `is_activity_tracking_enabled` | `ActivityManager` | `ActivityManagerNoOp` |
| `is_reporting_enabled` | `ReportingManager` | `ReportingNoOp` |

## Example Configuration

```toml
[pipelex.feature_config]
is_pipeline_tracking_enabled = true
is_activity_tracking_enabled = true
is_reporting_enabled = true
```

## Related Topics

- [Pipeline Tracking](../Pipeline/pipeline-tracking.md)
- [Activity Tracking](../Pipeline/activity-tracking.md)
- [Reporting System](../Reporting/reporting.md)
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