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
- `request_id`, `pipeline_run_id` and `pipe_run_id` are reserved for the [run-scoped context](#the-run-scoped-context), and `data` is reserved for [structured content](#structured-content). A field of one of those names is accepted and never dropped: it takes precedence over the context for the three identifiers, and a `data` field rides under `field_data` whatever the content is. Nothing else should use them.

### Names that are not yours to give

The stdlib refuses an `extra` key that would overwrite one of the record's own attributes (`name`, `message`, `lineno`, `module`, `args`, `asctime` and the rest), and a library's log call never raises. An entry of such a name is therefore carried under the prefix `field_`: `fields={"name": "alpha"}` lands as `record.field_name`. What counts as owned is read off the record actually built, through whatever record factory is installed, so an attribute an OpenTelemetry or tracing instrumentation stamps on every record is a collision too, for a field, a context identifier and `data` alike. The prefix is applied until the name lands on an attribute nobody owns, and entries attach in order, so a call that gives both `name` and `field_name` keeps both values whatever their order: the one that arrives second lands on `field_field_name`.

Two kinds of name are reserved though nothing on a fresh record owns them yet, because both are stamped after the entries are attached and the stdlib's refusal therefore cannot cover them: what the formatter sets (`message`, `asctime`) and what Pipelex's own logging machinery sets — `_pipelex_forwarded`, the marker that tells the sink's handler a record reached it through the boot's holding handler already. Both take the same `field_` prefix, and the marker is never handed to a sink as something the record carries. Without that reservation, `fields={"_pipelex_forwarded": True}` would have the sink's own filter read the record as one already delivered and drop it whole.

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

Structured content owns the `data` name, on every call: a `data` entry in `fields` keeps its value and is carried under `field_data` whatever the content is, a string included — the same prefix a field named like a record attribute or like a sink's reserved key gets. Nothing passed in `fields` is dropped for a name collision.

## Redaction

Every record is scrubbed once, before any sink renders it. The processor replaces what a secret pattern matched with `[REDACTED]`, in the message, in the exception's rendered text and in every string a field carries, and a field or a mapping entry whose own name is a secret's loses its value whatever it holds. It also replaces each control character in a field's string values with its printable escape, so a caller-supplied string cannot forge a line, a field separator or a colour on a terminal. The message keeps its control characters, which are the runtime's own rendering: a titled call and a structured content both put a newline there on purpose. The families, the secret names, the two configuration keys and the limits are in [Logging Configuration](../configuration/config-practical/logging-config.md#redaction).

A structured content is redacted by name before the dispatch renders it, so the message and the `data` attribute agree: `log.info({"password": {"nested": "hunter2"}})` writes `[REDACTED]` in both, where a pattern reading the rendered text could not have seen into the nested object. Content that JSON refuses outright — a circular reference, a mapping with a non-string key — falls back to its `repr` and carries no `data`, and is redacted by name on that path too: the `repr` of an object-valued entry is no more readable to a pattern than the rendering was.

An exception is scrubbed as text: the processor renders the traceback the way the stdlib would, chain included, scrubs it and stores it as the record's `exc_text`, which is what the stdlib formatter, the `json` sink and the `otlp` sink write. The exception object stays on the record, and the `otlp` sink emits `exception.type` and `exception.stacktrace` and no `exception.message`, since that one would be the exception's own text and nothing can scrub an exception. The one boundary that leaves is the `console` sink with `is_rich_tracebacks = true`, the default: Rich renders its traceback from the exception object, so on a person's terminal the exception reads as it was raised. A structured sink a collector reads is scrubbed.

**It runs on the sink's handler, not at the call sites, and it edits the record rather than a copy of it.** Both halves of that are deliberate.

On the handler, because that is where every record passes: a line a third-party library emitted with a raw request in it is exactly the line most likely to carry a bearer token, and no call site of ours is behind it. Scrubbing at the call sites would cover only what the facade emitted, which is the smaller and safer half.

In place, because what the processor does is *remove* something. A record that has lost a secret is strictly safer for any handler that sees it afterwards, so the edit is shared rather than kept to the sink: a handler an integration attached to the root logger after Pipelex booted is behind the scrub too. Handing the sink a redacted copy would have guaranteed the opposite — every other handler on the root logger would receive the secret the sink was spared. One limit follows, and it is the one the runtime cannot close: a handler already on the root logger *before* Pipelex booted runs ahead of the sink's and sees the record as the call made it. Redaction reaches the handlers Pipelex is in front of, and a host that installs its own handler first is in front of Pipelex.

`log.install_sink` is what puts the processor in front of the sink's own, so every sink gets it — the built-in ones, an out-of-tree one, and the console sink `pipelex doctor` falls back to — and no sink knows about it. A boot that dies before its sink arrives runs the same processor, behind the same guard, over every record it held before handing them to the stdlib's last resort on stderr, so the trail a failed boot leaves is scrubbed too. `[runtime.log.redaction] is_enabled = false` installs nothing at all.

The processor fails closed. A sink processor that raises is reported on stderr and the record is handed on, which is the right rule for a processor that enriches; for one that removes, it would mean the secret ships. So when the scrub itself fails, a value nested past the interpreter's recursion limit for one, the record is stripped before the failure is reported: its message becomes `[REDACTION FAILED: <exception type>]`, every field and the `data` attribute become `[REDACTED]`, and the exception text is dropped. The line says the scrub failed, and nothing of the call leaves with it.

The stripping can fail in its turn, and that case is closed too. The commonest reason the scrub fails is a stack that has run out — a `log.<level>(...)` call made a few frames from the limit, by a recursive walker or by an `except RecursionError:` handler — and a stack that could not take the scrub cannot always take the stripping of what it left behind a line later. So the record is marked before the stripping starts, by a plain assignment into its own dictionary that pushes no frame, and unmarked only once the stripping has gone all the way through; a record still carrying the mark when the processors are done is **dropped** rather than emitted. A notice saying the record was quarantined while it still carried the field the scrub never read would be worse than no line at all.

That report names the processor and the type of what it raised, and withholds the exception's own text and traceback — which the stdlib's `handleError` would have printed in full. A processor fails *on the record's values*, so its exception is exactly where they end up: the secret the scrub was removing among them. The same rule covers a record whose arguments do not fit its format string: rather than leave the handler to fail on it and have the stdlib print the format string and every argument raw, the processor renders the scrubbed format string alone, followed by `[ARGUMENTS WITHHELD: the message could not be rendered]`.

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

Logging is configured in two steps at boot. `log.configure` sets the levels and installs a holding handler on the root logger; then, once the plugin registrar is built, the configured sink is looked up, its handler is installed and the held records are replayed to it in order, so the boot's own lines reach the sink selected for them. A record emitted during the handoff reaches the sink either way, replayed or forwarded, and one held record the sink cannot render gets the stdlib's own recovery and costs none of the others. A call before `configure` never raises: the record goes to the stdlib's default handling at the stdlib's default level, so an `INFO` is dropped and a warning reaches stderr through `logging.lastResort`. A boot that fails between the two steps closes the holding handler, which hands every record it held to `logging.lastResort`, once the [redaction](#redaction) has run over each: they all passed the level the configuration set, and a boot that died is when that trail is read. No handler is installed before `configure`, and nothing is swallowed. A library that logs before Pipelex boots, and the boot itself while it configures, are both safe.

## Console rendering

The default sink, `console`, renders through Rich with every `[runtime.log.rich_log]` setting. Rich is the `cli` extra (`pipelex[cli]`), which the command-line tools install and a server leaves out. The sink imports Rich when it is built, so a process that selects `json` or `otlp` never loads it through the sink, and one that selects `console` without Rich installed stops at boot naming the extra to install and the `json` alternative. A server without the extra also sets `pretty_print_mode` to `"poor"` or `"silent"`, since the `"rich"` panels are refused at boot the same way (see [Pretty-Print Mode](../configuration/config-practical/logging-config.md#pretty-print-mode)).

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
