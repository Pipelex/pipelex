---
title: "Logging"
description: "Explore Pipelex logging: named fields, the run-scoped context, module-named loggers, custom log levels, Rich console formatting and structured data logging."
---

# Pipelex Logging System

## Overview

Pipelex logs through one facade, `from pipelex import log`, built on Python's standard `logging`. A call takes a message, optional named fields and the usual presentation options; the run-scoped identifiers are bound once at a process entry and stamped onto every record emitted in scope. Fields and identifiers ride the stdlib `LogRecord` as attributes, never spliced into the message text, so a structured sink renders them as fields while the console keeps a narrative line.

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

## Using the Logger

```python
from pipelex import log

# Basic logging
log.info("Simple message")

# Named fields ride the record as attributes; the message stays narrative
log.info("Scanned the inputs", fields={"files": 7, "bytes": 12_288})

# Logging with title
log.info("Detailed message", title="Process Status")

# Logging with inline title
log.info("Quick update", inline="Status")

# Logging structured data: rendered as JSON for the console, carried as `data` for a structured sink
data = {"key": "value", "nested": {"data": True}}
log.verbose(data, title="Configuration")

# Warning with problem ID
log.warning("API rate limit approaching", problem_id="rate_limit_warning")

# Error with exception traceback
log.error("Failed to process", include_exception=True)

# Development logging
log.dev("Testing new feature")

# Verbose logging
log.verbose("Detailed debug information")
```

Every one of the seven methods (`verbose`, `debug`, `dev`, `info`, `warning`, `error`, `critical`) takes the same keyword-only `fields`. `title`, `inline`, `problem_id` and `include_exception` keep their meaning beside it.

## Fields

`fields` is a mapping of named values. Each entry becomes an attribute of the emitted `LogRecord`, which is where a formatter or a sink reads it: `record.files` for the example above, or `%(files)s` in a stdlib format string. Nothing from `fields` is written into the message, so `record.getMessage()` is exactly the text you passed.

A value can be anything; the console ignores it and a structured sink serializes it, so prefer plain JSON-ready values (strings, numbers, booleans, lists and dictionaries of those) for anything meant to leave the process.

### Naming convention

- A field name is a `snake_case` identifier, spelled the way the value is spelled where it comes from: a field carrying a payload's `pipeline_run_id` is `pipeline_run_id`, not `pipelineRunId` or `run`.
- Where the [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/general/logs/) define a key for the concept, use that key verbatim, dots included (`http.response.status_code`, `code.function.name`), so an OTLP sink emits it without translation. The three run identifiers have no such key and keep their payload names.
- `request_id`, `pipeline_run_id` and `pipe_run_id` are reserved for the [run-scoped context](#the-run-scoped-context), and `data` is reserved for [structured content](#structured-content). A field of one of those names is accepted and takes precedence as described below, but nothing else should use them.

### Names the stdlib owns

The stdlib refuses an `extra` key that would overwrite one of the record's own attributes (`name`, `message`, `lineno`, `module`, `args`, `asctime` and the rest), and a library's log call never raises. A field of such a name is therefore carried under the prefix `field_`: `fields={"name": "alpha"}` lands as `record.field_name`. The full set is `pipelex.tools.log.log_fields.STDLIB_LOG_RECORD_ATTRIBUTES`, read off a fresh record at import so a new Python version cannot silently add one.

## The run-scoped context

The identifiers that correlate a record with the run it belongs to are bound once and stamped onto every record emitted while the binding holds:

```python
with log.context(request_id="req-7f3a", pipeline_run_id="plr-01"):
    log.info("Loading the bundle")  # carries request_id and pipeline_run_id
    with log.context(pipe_run_id="pr-9c"):
        log.info("Running the pipe")  # carries all three
    log.info("Delivering")  # pipe_run_id is gone again
log.info("Outside")  # carries none of them
```

The context is a `LogContext` with three optional identifiers, `request_id`, `pipeline_run_id` and `pipe_run_id`. The rules:

- **Absent means absent.** An identifier that is not bound is not on the record; it is never the string `"None"`.
- **Nested bindings merge, the inner overriding the outer** for the identifiers it gives. Passing `None` inherits the outer value rather than clearing it.
- **Exit restores the previous binding**, whether the block returns or raises.
- **The binding is task-local.** It lives in a `contextvars.ContextVar`, so concurrent asyncio tasks each keep their own and a task started inside the block inherits it.
- **A field overrides the context for its own record**: `log.info("...", fields={"request_id": "other"})` inside a bound context stamps `other`, for a call site that speaks about a request it is not running under.

`pipelex.tools.log.log_context.get_log_context()` returns the current `LogContext`, or `None` outside any binding.

### Where the context is bound

The identifiers travel in the payload, and the contextvar is in-process plumbing bound after deserialization and nothing else; it never crosses a process boundary. Each process entry binds from the payload it received:

- **A direct-mode run**: `PipeRun.run` binds `request_id`, `pipeline_run_id` and `pipe_run_id` from the job's `JobMetadata` for the whole run, delivery included, and releases the binding when the run returns.
- **An API request**: the runner's request middleware is where `request_id` is bound from the inbound request, for the request's duration.
- **A durable-execution activity or workflow**: the entry is where the identifiers are bound from the payload the orchestrator handed it.

The last two are the runner's and the orchestration plugin's to bind, beside the payload they read; the runtime only provides `log.context`.

## Structured content

When the content is not a string, it is rendered as JSON for the console, indented by `json_logs_indent`, and the JSON-ready form is carried as the record's `data` attribute for a structured sink:

- a `dict` is carried as a dictionary,
- a `list` is carried as a list,
- any other object, a pydantic model for instance, is carried as the dictionary or list its serialization produces,
- `None` is rendered as the word `None` and carries no `data`.

Structured content owns `data` outright: a `data` entry in `fields` beside a non-string content is overridden.

## Logger names and levels

Every record is emitted on the stdlib logger named after the module that made the call: a line from `pipelex/pipe_operators/pipe_llm.py` goes to `pipelex.pipe_operators.pipe_llm`, a line from your own `myapp.jobs.nightly` module goes to `myapp.jobs.nightly`. The module is read from one frame lookup at a fixed depth, so a log line costs a dictionary and a frame lookup; nothing walks the stack.

Because the stdlib logger hierarchy inherits levels, a `package_log_levels` key at any depth works, with `-` standing for `.`:

```toml
[runtime.log.package_log_levels]
pipelex = "INFO"
pipelex-pipe_operators-pipe_llm = "DEBUG"
httpx = "WARNING"
```

The record's `pathname`, `lineno` and `funcName` point at the calling line, which is what the Rich handler links to and what the caller-info templates render when `is_caller_info_enabled` is on; all of it comes from that same frame, with no source file read.

## Before configuration

`log.configure` runs at boot, and a call before it never raises: the record goes to the stdlib's default handling at the stdlib's default level, so an `INFO` is dropped and a warning reaches stderr through `logging.lastResort`. No handler is installed as a side effect, and nothing is swallowed. A library that logs before Pipelex boots, and the boot itself while it configures, are both safe.

## Console rendering

### Rich Formatting

- Color coding and syntax highlighting for JSON and other data structures
- Clickable file paths pointing at the calling line
- Word wrapping for better readability

### Emoji Support

Built-in emoji indicators for different components, keyed on the logger name's prefix:

- 🧠 Pipelex core messages
- ⚪️ OpenAI-related logs
- 🌀 Google-related logs
- ⚡️ Network connections
- *️⃣ JSON processing
- 🧿 Poor-log channel (`#poor-log`, the simplified fallback logger)

### Caller Information

Optional inclusion of caller information in logs, prefixed to the console line:

- File name and line number
- Function name
- Module name
- Customizable format templates

## Best Practices

1. **Log Level Selection**:

    - Use VERBOSE for detailed debugging
    - Use DEBUG for general debugging
    - Use DEV for development-specific logging
    - Use INFO for general progress
    - Use WARNING for potential issues
    - Use ERROR for actual errors
    - Use CRITICAL for system-critical issues

2. **Fields over interpolation**:

    - Put a value a reader might filter or aggregate on in `fields`, and keep the message a sentence
    - Name a field after the thing it carries, in `snake_case`, or after its OpenTelemetry key when one exists
    - Leave the run identifiers to the context; bind them at the process entry, never per call

3. **Structured Data**:

    - Log complex data structures directly; they reach the console as JSON and a sink as `data`
    - Use titles for context
    - Include problem IDs for trackable issues

4. **Exception Handling**:

    - Use `include_exception=True` for error context
    - Include relevant data in error logs
    - Use appropriate log levels for exceptions

## Related Documentation

- [Logging Configuration](../configuration/config-practical/logging-config.md) - Configure log behavior in `pipelex.toml`
- [CLI](./cli/index.md) - Commands that surface runtime logs during development
