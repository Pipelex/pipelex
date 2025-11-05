# Pipelex Logging System

## Overview

Pipelex provides a sophisticated logging system that extends Python's standard logging with additional features like emoji support, rich formatting, and custom log levels.

## Log Levels

In addition to standard Python log levels, Pipelex introduces custom levels:

| Level | Value | Description |
|-------|-------|-------------|
| VERBOSE | 5 | Most detailed logging, below DEBUG |
| DEBUG | 10 | Standard debug information |
| DEV | 15 | Development-specific logging (between DEBUG and INFO) |
| INFO | 20 | General informational messages |
| WARNING | 30 | Warning messages |
| ERROR | 40 | Error messages |
| CRITICAL | 50 | Critical errors |
| OFF | 999 | Disable logging |

## Logging Features

### 1. Rich Formatting

- Beautiful console output with color coding
- Syntax highlighting for JSON and other data structures
- Support for clickable file paths
- Word wrapping for better readability

### 2. Emoji Support

Built-in emoji indicators for different components:

- 🧠 Pipelex core messages
- ⚪️ OpenAI-related logs
- 🌀 Google-related logs
- ⚡️ Network connections
- *️⃣ JSON processing
- 🧿 Sandbox operations

### 3. Caller Information

Optional inclusion of caller information in logs:

- File name and line number
- Function name
- Module name
- Customizable format templates

### 4. Structured Data Logging

Intelligent handling of different data types:

- Pretty-printing for dictionaries and lists
- JSON formatting with customizable indentation
- Special handling for None values
- Exception traceback integration

### 5. Log Dispatch System

Smart routing of log messages:

- Automatic detection of log origin
- Separate handlers for different logging needs
- Sandbox-aware logging behavior
- Support for poor loggers (simplified logging)

## Using the Logger

```python
from pipelex import log

# Basic logging
log.info("Simple message")

# Logging with title
log.info("Detailed message", title="Process Status")

# Logging with inline title
log.info("Quick update", inline="Status")

# Logging structured data
data = {"key": "value", "nested": {"data": True}}
log.verbose(data, title="Configuration")

# Warning with problem ID
log.warning("API rate limit approaching", problem_id="rate_limit_warning")

# Error with exception traceback
log.error("Failed to process", include_exception=True)

# Development logging
log.verbose("Testing new feature")

# Verbose logging
log.verbose("Detailed debug information")
```

## Best Practices

1. **Log Level Selection**:

    - Use VERBOSE for detailed debugging
    - Use DEBUG for general debugging
    - Use DEV for development-specific logging
    - Use INFO for general progress
    - Use WARNING for potential issues
    - Use ERROR for actual errors
    - Use CRITICAL for system-critical issues

2. **Structured Data**:

    - Log complex data structures directly
    - Use titles for context
    - Include problem IDs for trackable issues

3. **Exception Handling**:

    - Use `include_exception=True` for error context
    - Include relevant data in error logs
    - Use appropriate log levels for exceptions
