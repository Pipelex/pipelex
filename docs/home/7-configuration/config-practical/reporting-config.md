# Reporting Configuration

Configuration section: `[pipelex.reporting_config]`

## Overview

The reporting configuration controls how Pipelex generates and manages cost reports for various operations (LLM usage, OCR processing, etc.). This configuration allows you to customize where and how cost reports are generated.

## Configuration Options

### Console Logging

```toml
is_log_costs_to_console = false
```

- Controls whether costs are logged to the console in **real-time**
- When enabled, displays token cost reports after each LLM operation (and other operations with costs)
- Default: `false`

### Cost Report File Generation

```toml
is_generate_cost_report_file_enabled = true
```

- Controls whether cost report files are generated after the execution of the pipeline
- When enabled, creates detailed reports in CSV format in the directory `reports/` by default.
- Default: `true`

### Report File Location

```toml
cost_report_dir_path = "reports"
```

- Directory where cost report files will be saved
- Path is relative to your project root
- Directory will be created if it doesn't exist.
- Default: `"reports"`

### Report File Naming

```toml
cost_report_base_name = "cost_report"
cost_report_extension = "csv"
```

- Base name for report files
- File extension for report files (e.g., "csv" for CSV files)
- Final filename will include an incremental number (e.g., `cost_report_1.csv`, `cost_report_2.csv`)
- Default: Base name = `"cost_report"`, Extension = `"csv"`

### Cost Unit Scaling

```toml
cost_report_unit_scale = 1.0
```

- Scaling factor applied to cost values in reports
- Use 1.0 for actual costs
- Use different values to scale costs (e.g., 1000.0 for thousands)
- The currency is in USD.
- Default: `1.0`

## Example Configuration

```toml
[pipelex.reporting_config]
# Enable console logging for development
is_log_costs_to_console = true

# Generate report files
is_generate_cost_report_file_enabled = true

# Store reports in a custom directory
cost_report_dir_path = "analytics/cost_reports"

# Customize report file naming
cost_report_base_name = "llm_costs"
cost_report_extension = "csv"

# Show costs in thousands
cost_report_unit_scale = 1000.0
```

## Best Practices

!!! warning "Under Construction"
    This section is currently under development.
