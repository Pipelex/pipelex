# Configuration

## Overview

The `pipelex.toml` configuration file is created at the root of your project when you run `pipelex init-config`. This file contains all the necessary settings to customize your Pipelex environment.

## Configuration Structure

The configuration file is organized into several sections:

### Feature Flags

```toml
[feature_flags]
enable_cost_reporting = true
enable_detailed_logging = false
```

These flags control various optional features in Pipelex.

### Logging

```toml
[logging]
level = "INFO"
output_dir = "logs/"
format = "json"
```

Configure how Pipelex logs information about pipeline execution and system status.

### Cost Reporting

```toml
[cost_reporting]
currency = "USD"
output_format = "csv"
report_frequency = "daily"
```

Settings for tracking and reporting LLM API usage costs.

### API Configuration

```toml
[api]
timeout = 30
max_retries = 3
```

General API behavior settings.

## Customizing Your Configuration

You can modify any of these settings by editing the `pipelex.toml` file directly. The file is well-documented with comments explaining each option.

### Example Configuration

Here's a complete example of a `pipelex.toml` file:

```toml
# Feature flags section
[feature_flags]
enable_cost_reporting = true
enable_detailed_logging = false

# Logging configuration
[logging]
level = "INFO"
output_dir = "logs/"
format = "json"

# Cost reporting settings
[cost_reporting]
currency = "USD"
output_format = "csv"
report_frequency = "daily"

# API configuration
[api]
timeout = 30
max_retries = 3
```

## Best Practices

1. **Version Control**: Always include your `pipelex.toml` in version control
2. **Environment Specific**: Use different configurations for development and production
3. **Documentation**: Comment any custom settings for team reference

## Related Topics

- [Libraries documentation](../Libraries/libraries.md)
- [Quick Start Guide](../Quick-start/Quick-start.md)

---

"Pipelex" is a trademark of Evotis S.A.S.

© 2025 Evotis S.A.S. 