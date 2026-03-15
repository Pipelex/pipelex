---
description: "Toggle Pipelex feature flags — enable or disable the reporting system and other optional capabilities through TOML configuration."
---

# Feature Configuration

The `FeatureConfig` class controls which features are enabled in Pipelex.

## Configuration Options

```python
class FeatureConfig(ConfigModel):
    is_reporting_enabled: bool
```

### Fields

- `is_reporting_enabled`: When true, enables the reporting system

## Impact on Dependency Injection

The feature flags directly affect which implementation is used for certain components:

| Feature Flag | When True | When False |
|--------------|-----------|------------|
| `is_reporting_enabled` | `ReportingManager` | `ReportingNoOp` |

## Feature Details

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
# Enable reporting for cost monitoring
is_reporting_enabled = true
```

## Related Documentation

- [Cost Tracking](../../features/cost-tracking.md) - Track and monitor AI usage costs
- [Reporting Config](../config-practical/reporting-config.md) - Detailed reporting configuration options
