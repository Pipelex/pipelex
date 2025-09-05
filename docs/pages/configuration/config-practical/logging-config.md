# Logging Configuration

Configuration section: `[pipelex.log_config]`

## Overview

The logging configuration controls how Pipelex handles log messages, their formatting, and their display. The configuration is split into general logging settings and Rich console output settings.

## General Settings

### Log Levels

```toml
default_log_level = "INFO"
```

- Sets the default logging level for all loggers
- Valid values: `"VERBOSE"`, `"DEBUG"`, `"DEV"`, `"INFO"`, `"WARNING"`, `"ERROR"`, `"CRITICAL"`, `"OFF"`

### Package-Specific Log Levels

```toml
[pipelex.log_config.package_log_levels]
anthropic = "INFO"
asyncio = "INFO"
botocore = "INFO"
openai = "INFO"
pipelex = "INFO"
```

- Override log levels for specific packages
- Use `-` instead of `.` in package names (e.g., `urllib3-connectionpool`)

### Console Output

```toml
is_console_logging_enabled = true
```

- Enable/disable console logging
- Default: `true`

### JSON Formatting

```toml
json_logs_indent = 4
presentation_line_width = 120
```

- `json_logs_indent`: Indentation for JSON log output
- `presentation_line_width`: Maximum line width for formatted output

### Caller Information

```toml
is_caller_info_enabled = false
caller_info_template = "file_line"
```

Available templates:

- `"file_line"`: "file.py:123"
- `"file_line_func"`: "file.py:123 function_name"
- `"func"`: "function_name"
- `"file_func"`: "file.py function_name"
- `"func_line"`: "function_name 123"
- `"func_module"`: "function_name module"
- `"func_module_line"`: "function_name module 123"

### Problem Silencing

```toml
silenced_problem_ids = ["azure_openai_no_stream_options"]
```

- List of problem IDs to silence
- Prevents specific warnings from being logged

### Poor Loggers

```toml
generic_poor_logger = "#poor-log"
poor_loggers = [
    "kajson.decoder.sandbox",
    "kajson.encoder.sandbox",
    "class_registry.sandbox"
]
```

- Loggers that use simplified formatting without fancy features
- Useful for sandbox environments or when simple logging is needed

## Rich Console Configuration

Configuration section: `[pipelex.log_config.rich_log_config]`

### Display Options

```toml
is_show_time = false
is_show_level = true
is_link_path_enabled = true
```

- `is_show_time`: Show timestamp in logs
- `is_show_level`: Show log level
- `is_link_path_enabled`: Make file paths clickable

### Syntax Highlighting

```toml
highlighter_name = "json"  # or "repr"
is_markup_enabled = false
```

- `highlighter_name`: Choose between JSON or repr highlighting
- `is_markup_enabled`: Enable Rich markup syntax in log messages

### Traceback Settings

```toml
is_rich_tracebacks = true
is_tracebacks_word_wrap = true
is_tracebacks_show_locals = false
tracebacks_suppress = []
```

- Control how Python tracebacks are displayed
- Enable/disable word wrapping and local variable display
- Suppress specific traceback patterns

### Keyword Highlighting

```toml
keywords_to_hilight = []
```

- List of keywords to highlight in log messages
- Useful for emphasizing important terms

## Example Configuration

```toml
[pipelex.log_config]
default_log_level = "INFO"
log_mode = "rich"
is_console_logging_enabled = true
json_logs_indent = 4
presentation_line_width = 120
is_caller_info_enabled = true
caller_info_template = "file_line_func"

silenced_problem_ids = []
generic_poor_logger = "#poor-log"
poor_loggers = []

[pipelex.log_config.package_log_levels]
pipelex = "INFO"
openai = "WARNING"
anthropic = "INFO"

[pipelex.log_config.rich_log_config]
is_show_time = false
is_show_level = true
is_link_path_enabled = true
highlighter_name = "json"
is_markup_enabled = false
is_rich_tracebacks = true
is_tracebacks_word_wrap = true
is_tracebacks_show_locals = false
tracebacks_suppress = []
keywords_to_hilight = ["error", "warning", "failed"]
```

## Best Practices

1. **Development Environment**:

    - Enable caller info for better debugging
    - Use verbose logging levels
    - Enable local variables in tracebacks

2. **Production Environment**:

    - Disable caller info for performance
    - Use INFO or higher log levels
    - Disable local variables in tracebacks

3. **Package Log Levels**:

    - Set noisy third-party packages to WARNING
    - Keep pipelex at INFO for important updates
    - Use VERBOSE only when debugging specific issues
