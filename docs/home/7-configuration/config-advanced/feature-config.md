# Feature Configuration

The `FeatureConfig` class controls which features are enabled in Pipelex.

## Configuration Options

```python
class FeatureConfig(ConfigModel):
    is_pipeline_tracking_enabled: bool
    is_reporting_enabled: bool
```

### Fields

- `is_pipeline_tracking_enabled`: When true, enables pipeline tracking functionality
- `is_reporting_enabled`: When true, enables the reporting system

## Impact on Dependency Injection

The feature flags directly affect which implementation is used for certain components:

| Feature Flag | When True | When False |
|--------------|-----------|------------|
| `is_pipeline_tracking_enabled` | `PipelineTracker` | `PipelineTrackerNoOp` |
| `is_reporting_enabled` | `ReportingManager` | `ReportingNoOp` |

## Feature Details

### Pipeline Tracking

```toml
is_pipeline_tracking_enabled = true
```

- Controls whether pipeline execution tracking is enabled
- When enabled, tracks the flow and execution of pipelines using by default mermaid chart:
  - View and edit charts at [Mermaid Live Editor](https://mermaid.live)
- Useful for debugging and monitoring pipeline behavior
- Default: `true`

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

# Enable reporting for cost monitoring
is_reporting_enabled = true
```
