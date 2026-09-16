---
title: "Logging"
description: "Explore Pipelex logging: named fields, the run-scoped context, module-named loggers, custom log levels, the console, json and otlp sinks and structured data logging."
---

# Pipelex Logging System

## Overview

Pipelex logs through one facade, `from pipelex import log`, built on Python's standard `logging`. A call takes a message, optional named fields and the usual presentation options; the run-scoped identifiers are bound once at a process entry and stamped onto every record emitted in scope. Fields and identifiers ride the stdlib `LogRecord` as attributes, never spliced into the message text, so a structured sink renders them as fields while the console keeps a narrative line. Where the records go is one config key, `sink` under `[runtime.log]`: `console` renders them through Rich, `json` writes one JSON object per line, `otlp` ships them to an OpenTelemetry collector, and a plugin can register another. The keys are in [Logging Configuration](../configuration/config-practical/logging-config.md) and the seam itself in [Log Sink Plugins](../under-the-hood/log-sink-plugins.md).

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

# Error carrying the exception being handled, for the sink to render
log.error("Failed to process", include_exception=True)

# Development logging
log.dev("Testing new feature")

# Verbose logging
log.verbose("Detailed debug information")
```

Every one of the seven methods (`verbose`, `debug`, `dev`, `info`, `warning`, `error`, `critical`) takes the same keyword-only `fields`. `title`, `inline`, `problem_id` and `include_exception` keep their meaning beside it. `include_exception=True` carries the exception being handled as the record's `exc_info`, with nothing spliced into the message: the `console` sink renders the traceback under the line, the `json` sink writes it under the `exception` key and the `otlp` sink under the `exception.*` attributes. Outside an `except` block it carries nothing.

## Fields

`fields` is a mapping of named values. Each entry becomes an attribute of the emitted `LogRecord`, which is where a formatter or a sink reads it: `record.files` for the example above, or `%(files)s` in a stdlib format string. Nothing from `fields` is written into the message, so `record.getMessage()` is exactly the text you passed.

A value can be anything. It rides the record by reference and the sink serializes it on emit, on the calling thread, so what leaves the process is the value as it was at the call, and mutating it afterwards changes nothing already emitted. The `console` sink ignores it, the `json` sink dumps a pydantic model in JSON mode and falls back to `str` for a value JSON does not know, and the `otlp` sink carries a scalar or a sequence of scalars as an attribute and anything else as JSON text; prefer plain JSON-ready values (strings, numbers, booleans, lists and dictionaries of those) for anything meant to be queried later.

### Naming convention

- A field name is a `snake_case` identifier, spelled the way the value is spelled where it comes from: a field carrying a payload's `pipeline_run_id` is `pipeline_run_id`, not `pipelineRunId` or `run`.
- Where the [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/general/logs/) define a key for the concept, use that key verbatim, dots included (`http.response.status_code`, `code.function.name`), so an OTLP sink emits it without translation. The three run identifiers have no such key and keep their payload names.
- `request_id`, `pipeline_run_id` and `pipe_run_id` are reserved for the [run-scoped context](#the-run-scoped-context), and `data` is reserved for [structured content](#structured-content). A field of one of those names is accepted and takes precedence as described below, but nothing else should use them.

### Names the stdlib owns

The stdlib refuses an `extra` key that would overwrite one of the record's own attributes (`name`, `message`, `lineno`, `module`, `args`, `asctime` and the rest), and a library's log call never raises. An entry of such a name is therefore carried under the prefix `field_`: `fields={"name": "alpha"}` lands as `record.field_name`. What counts as owned is read off the record actually built, through whatever record factory is installed, so an attribute an OpenTelemetry or tracing instrumentation stamps on every record is a collision too, for a field, a context identifier and `data` alike. The prefix is applied until the name lands on an attribute nobody owns, and entries attach in order, so a call that gives both `name` and `field_name` keeps both values whatever their order: the one that arrives second lands on `field_field_name`.

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

- **A direct-mode run**: `PipeRun.run` binds `request_id` and `pipeline_run_id` from the job's `JobMetadata` for the whole run, delivery included, and releases the binding when the run returns. The metadata a submission builds carries no `pipe_run_id` yet.
- **Every pipe run**: `live_run_pipe` mints the pipe run's id and binds `pipe_run_id` around the whole of the run, the line announcing it, its span lines and its failure included, so every record emitted during a pipe's run names the run it belongs to, a nested pipe rebinding its own and the outer id coming back when it returns, however it returns. A pipe lifted for absent optional inputs does not run and has no id: its skip line carries the enclosing binding, the parent pipe's or none. This is the binding every orchestration shares, direct or distributed.
- **An API request**: the runner's request middleware is where `request_id` is bound from the inbound request, for the request's duration.
- **A durable-execution activity or workflow**: the entry is where the identifiers are bound from the payload the orchestrator handed it.

The last two are the runner's and the orchestration plugin's to bind, beside the payload they read; the runtime only provides `log.context`.

## Structured content

When the content is not a string, it is rendered as JSON for the message, indented by `json_logs_indent`, and the rendering is read back as the record's `data` attribute for a structured sink. `data` is therefore a snapshot of the call, JSON-ready whatever the content held, and the caller may mutate the object afterwards without changing what was emitted:

- a `dict` is carried as a dictionary and a `list` as a list, their values as JSON reads them back: a datetime as its text, a `Decimal` as a string,
- a pydantic model, or a list of models, is carried as the dictionary or list its serialization produces,
- a number or a boolean is carried as itself, `log.info(42)` giving `data == 42`,
- a value JSON cannot serialize goes through the JSON helpers' fallbacks, kajson first and `str` last, and a dictionary that reaches the last fallback is wrapped as `{"!": ...}` to flag it,
- `None` is rendered as the word `None` and carries no `data`,
- content `json` refuses outright, a circular reference or a mapping with a non-string key, is rendered as its `repr` and carries no `data`; a log call never raises.

A `NaN` or an infinity survives the round trip as a float; a wire sink writes it as the string `"NaN"`, `"Infinity"` or `"-Infinity"`, since JSON has no token for it that a strict parser accepts.

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

The record's `pathname`, `lineno` and `funcName` point at the calling line, which is what the `console` sink links to and what the caller-info templates render when `is_caller_info_enabled` is on; all of it comes from that same frame, with no source file read.

A filter attached to `logging.getLogger("pipelex")` never sees these records: the stdlib runs a logger's filters only for records emitted on that very logger, and a record is emitted on the module-named one. Attach the filter to the handler instead, which the stdlib runs for every record it handles, or, to reach whichever sink is installed, append a processor to the sink's `processors` list, as described in [Log Sink Plugins](../under-the-hood/log-sink-plugins.md#logsink).

## Before configuration

Logging is configured in two steps at boot. `log.configure` sets the levels and installs a holding handler on the root logger; then, once the plugin registrar is built, the configured sink is looked up, its handler is installed and the held records are replayed to it in order, so the boot's own lines reach the sink selected for them. A record emitted during the handoff reaches the sink either way, replayed or forwarded, and one held record the sink cannot render gets the stdlib's own recovery and costs none of the others. A call before `configure` never raises: the record goes to the stdlib's default handling at the stdlib's default level, so an `INFO` is dropped and a warning reaches stderr through `logging.lastResort`. A boot that fails between the two steps closes the holding handler, which hands what it held at `WARNING` and above to `logging.lastResort` and drops the rest. No handler is installed before `configure`, and nothing is swallowed. A library that logs before Pipelex boots, and the boot itself while it configures, are both safe.

## Console rendering

The default sink, `console`, renders through Rich with every `[runtime.log.rich_log]` setting. Rich is imported when the sink is built and nowhere else, so a process that selects `json` or `otlp` never loads it, and one that selects `console` without Rich installed stops at boot naming the extra to install and the `json` alternative.

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

    - Use `include_exception=True` inside the `except` block, and let the sink render the traceback its own way
    - Include relevant data in error logs
    - Use appropriate log levels for exceptions

## Related Documentation

- [Logging Configuration](../configuration/config-practical/logging-config.md) - Configure log behavior and select the sink in `pipelex.toml`
- [Log Sink Plugins](../under-the-hood/log-sink-plugins.md) - The sink seam, the built-in sinks and how to write one
- [CLI](./cli/index.md) - Commands that surface runtime logs during development
