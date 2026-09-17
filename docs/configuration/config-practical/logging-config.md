---
description: "Select where Pipelex log records go with the sink key, and fine-tune logging levels, the console rendering, the JSON and OTLP sinks and message formatting through TOML configuration settings in pipelex.toml."
---

# Logging Configuration

Configuration section: `[runtime.log]`

## Overview

The logging configuration controls the levels, where the records go, and how they are rendered. Where they go is one key, `sink`, naming a registered log sink; each shipped sink then reads its own settings from the section, and the rest of the section applies to every sink.

## General Settings

### Log Levels

```toml
default_log_level = "INFO"
```

- Sets the default logging level for all loggers
- Valid values: `"VERBOSE"`, `"DEBUG"`, `"DEV"`, `"INFO"`, `"WARNING"`, `"ERROR"`, `"CRITICAL"`, `"OFF"`
- `"OFF"` silences the loggers `[runtime.log.package_log_levels]` does not pin; Pipelex's own loggers are pinned there at `INFO`, so silencing them, whichever sink is selected, is `pipelex = "OFF"` in that section

### Package-Specific Log Levels

```toml
[runtime.log.package_log_levels]
anthropic = "INFO"
asyncio = "INFO"
botocore = "INFO"
openai = "INFO"
pipelex = "INFO"
```

- Override log levels for specific packages
- Use `-` instead of `.` in package names (e.g., `urllib3-connectionpool`)
- A key works at any depth of the logger hierarchy, because Pipelex names every logger after the emitting module: `pipelex` governs the whole runtime, and `pipelex-pipe_operators-pipe_llm = "DEBUG"` opens one module while the rest of `pipelex` stays at its level

### The Sink

```toml
sink = "console"
```

- Names the registered log sink boot installs on the root logger, the way `runtime.storage.method` names a storage backend
- `"console"`: the Rich handler, for a terminal. The default, so the CLI keeps its rendering
- `"json"`: one JSON object per line, for a server behind a log agent
- `"otlp"`: the OpenTelemetry logs signal, for a collector
- Any other token an installed plugin registers; a token nobody provides stops the boot naming the registered ones
- The sink is a plugin capability: how it is discovered, selected and written is in [Log Sink Plugins](../../under-the-hood/log-sink-plugins.md)

### Console Log Target

```toml
console_log_target = "stderr"
```

- The process stream the `console` and `json` sinks write to: `"stdout"` or `"stderr"`
- Default: `"stderr"`, because logs are diagnostics and must stay off the data channel
- `console_print_target`, beside it, is a different knob: the Rich `Console` used for banners and the main CLI's data tables, which default to `"stdout"` so they can be piped to a file

### Pretty-Print Mode

```toml
pretty_print_mode = "rich"
```

- Controls the panels that `pretty_print(...)` renders, such as the "Output of pipe" panel shown after every operator pipe
- `"rich"`: Rich tables and panels on the console print target
- `"poor"`: plain text in a drawn frame on stderr, with no Rich panel; a pipe's output prints as its plain rendering
- `"silent"`: nothing is printed and no renderable is built, for a host with no console or one that must not spend time rendering on the thread that runs pipes
- Default: `"rich"`. The agent CLI forces `"silent"`
- Boot applies the key, replacing any `PrettyPrinter.mode` assigned in code before it, and teardown returns the printer to the mode the process held before that boot

### JSON Formatting

```toml
json_logs_indent = 4
presentation_line_width = 120
```

- `json_logs_indent`: Indentation of the JSON rendering a structured content (a `dict`, a `list`, a model) gets in the message
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

### Redaction

```toml
[runtime.log.redaction]
is_enabled = true
extra_patterns = []
```

One processor, applied to every record before any sink renders it, whichever sink is selected. It does two things, and the difference between them matters.

**It scrubs secrets** from the message, from the exception's rendered text and from every string a field carries, replacing what a pattern matched with `[REDACTED]` and keeping whatever named the secret, so a reader still sees which header or which entry was carrying it. The shipped families are the ones the hosted plane already ran over its own records:

- an `Authorization` header, whichever scheme it carries — `Bearer`, `Basic`, `Token`, `Digest`, `Negotiate`, `HMAC` — the scheme kept and the credential after it removed,
- an api-key header or entry, however it is spelled (`x-api-key`, `api-key`, `api_key`),
- a webhook signature header (`x-signature`, `x-completion-signature`),
- an OAuth authorization code in a query string (`?code=…`, `&code=…`), read to the `&` or the `#` that ends the parameter rather than through an alphabet of its own, so a percent-encoded code goes whole,
- a `Cookie` or `Set-Cookie` header's whole value, every crumb and every flag attribute of it. The value has to be a cookie header's own `name=value` grammar, which is what tells a header from a sentence: a quoted crumb is read to its closing quote and a crumb holding an apostrophe is read whole, while prose that merely says "cookie:" before ordinary words keeps its line,
- a serialised entry, in a JSON object or a Python `repr` alike, whose name is one of the secret names below: its value is removed whether it is quoted — with either quote character, and whichever quoted the name — or a bare number or boolean,
- those same names again in the plain `name=value` or `name: value` form a query string, a form-encoded body or a header line writes them in, which is the shape a raw request reaches the processor in,
- a key recognisable by its prefix alone: `sk_`, `plx_sk_`, `pk_`, `bl_`, each spelled with a dash as with an underscore, so `sk-proj-…` and `sk-ant-api03-…` go the way `sk_live_…` does. The prefix is kept and what follows it removed, and what follows has to end in a long unbroken run of letters and digits — which is what keeps this family off an ordinary snake_case identifier, a table or a partition named `pk_customer_reference_index` being words all the way down.

Every family but the serialised entry asks for at least eight characters of what a secret is written in. That bound is what keeps a family reading a `name: value` shape off ordinary prose, and it is the one the hosted plane's own scrubber was written with; a secret shorter than it is below what the shipped families read at all.

The **secret names** are `password`, `pipelex_api_key`, `gateway_api_key`, `jwt_secret_key`, `portkey_api_key`, `client_secret`, `access_token`, `refresh_token`, `id_token`, `authorization`, `api_key`, `x_api_key`, `x_signature`, `x_completion_signature`, `cookie` and `set_cookie`, read in any case and with a dash as an underscore. A **field of the record whose own name is one of them** loses its value whatever it holds — judged by the name the call used, so a field carried under the `field_` collision prefix because the record already owned that name is covered too — and so does a **mapping entry** at any depth, since the mapping split the name from the value the families read together. `code` is deliberately not a secret name: it is the runtime's own identifier for a pipe, a domain and an error, and the OAuth code has its query-string family.

A structured value, a field's `dict` or `list` or the `data` a structured content produces, is walked to any depth, and its strings go through the families above. A pydantic model is dumped and any other object rendered as text before the walk, exactly as the `json` and `otlp` sinks would have done after it, so neither carries a secret past the scrub; a model or an object that refuses to render becomes an `[UNRENDERABLE: <exception type>]` marker, which costs that one value and leaves the record and every other value it carries. A container that contains itself is cut at the cycle with a `[cycle]` marker.

A structured content is redacted by name **before the message is rendered**, so the line a sink writes beside `data` says exactly what `data` holds: a secret nested in an object or held as a number is beyond what a pattern can read back out of text. That holds for content JSON refuses outright too — a circular reference, a mapping with a non-string key — which is rendered as its `repr` and carries no `data`: the names are redacted on that path as well, since a `repr` is no more readable to a pattern than a rendering is. Text a call rendered itself, an f-string of a dictionary for one, is covered by the serialised-entry family alone, which does not see into a nested object.

**It neutralises control characters** in a field's string values, and only there: each becomes its printable escape, so a newline in a caller-supplied value cannot forge a line and a tab cannot forge a field separator, and an escape byte cannot colour a terminal. The message and the `data` attribute keep their control characters, because they are the runtime's own rendering — a titled call and a structured content both put a newline there deliberately, and the wire sinks escape `data` themselves, so a logged prompt keeps its line breaks. `data` is the runtime's name alone: a call that passes a field of that name has it carried as `field_data`, and escaped like every other field.

**It fails closed.** A scrub that raises costs that record its processing, never the log call, and the record it hands on carries nothing of the call: the message becomes `[REDACTION FAILED: <exception type>]` and every field the record carried becomes `[REDACTED]`. Where even that stripping cannot complete — a stack that has run out is the usual reason the scrub failed in the first place, and it can run out again a line later — the record is dropped instead of emitted, so no sink ever receives one the scrub did not read.

- `is_enabled`: `true` by default. `false` turns the processor off for a process that redacts downstream, or one whose records must be reproduced exactly as the calls made them
- `extra_patterns`: regular expressions added to the shipped families, for the secret shapes only this deployment knows. Every match is replaced by `[REDACTED]`. A pattern the `re` module refuses is a configuration error named when the configuration loads, and so is one that matches the empty string — `x*` where `x+` was meant matches at every position of every line, which would replace the whole of every line the process writes

What the processor does not reach is the `console` sink's Rich traceback, rendered from the exception object rather than from the scrubbed text, so on a person's terminal an exception reads as it was raised. Where the processor runs, and why it edits the record rather than a copy of it, is in [Logging](../../tools/logging.md#redaction).

### Problem Silencing

```toml
silenced_problem_ids = ["azure_openai_no_stream_options"]
```

- List of problem IDs to silence
- Prevents specific warnings from being logged

## The `console` Sink

Configuration section: `[runtime.log.rich_log]`, read only when `sink = "console"`. The sink writes to `console_log_target`.

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
is_markup_enabled = true
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

- Control how Python tracebacks are displayed; an exception a call carries with `include_exception=True` is rendered once, as a Rich traceback
- Enable/disable word wrapping and local variable display
- Suppress specific traceback patterns

### Keyword Highlighting

```toml
keywords_to_hilight = []
```

- List of keywords to highlight in log messages
- Useful for emphasizing important terms

## The `json` Sink

No section of its own: the sink writes to `console_log_target`, one JSON object per line and no ANSI ever. Each line carries `time` (ISO 8601, UTC, milliseconds, `Z`), `severity` (the level name), `logger` (the module-named logger), `message`, `exception` when the record carries one, and then every field, the run-scoped identifiers and the `data` attribute flat beside them, under their own names. Those keys are reserved on every line, so a field named like one of them is carried under a `field_` prefix whether or not the line carries an exception, and a non-finite float is written as the string `"NaN"`, `"Infinity"` or `"-Infinity"`. The key names are the ones the CloudWatch agent, the Google Cloud Logging agent and any OTLP collector ingest without a parser.

```json
{"time": "2026-09-16T10:12:03.417Z", "severity": "INFO", "logger": "pipelex.pipe_operators.pipe_llm", "message": "Running the pipe", "request_id": "req-7f3a", "pipeline_run_id": "plr-01", "pipe_run_id": "pr-9c", "model": "gpt-5"}
```

## The `otlp` Sink

Configuration section: `[runtime.log.otlp]`, read only when `sink = "otlp"`.

```toml
[runtime.log.otlp]
endpoint = "http://collector:4318/v1/logs"
headers = { Authorization = "Bearer ..." }
```

- `endpoint`: The collector's logs URL. Left unset, the exporter follows the OpenTelemetry environment conventions: `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`, then `OTEL_EXPORTER_OTLP_ENDPOINT` with the `/v1/logs` path, then the collector default on localhost
- `headers`: Headers sent with every export, an authorization header typically. Empty, the default, leaves `OTEL_EXPORTER_OTLP_HEADERS` in charge
- The records are exported in batches on the OTLP HTTP protocol, with the same service identity as the spans the runtime already exports, so a collector files the two together
- The sink never exports its own export path: a record the SDK or the transport emits while an export is in flight is rejected before the handler's lock is taken, so an unreachable collector costs a warning on the export thread and never a loop or a hang at exit. A flush at teardown is bounded by the exporter's own timeout, `OTEL_EXPORTER_OTLP_TIMEOUT`, and whatever the sink raises while it flushes or closes is said on stderr rather than left to interrupt the teardown

## Example Configuration

```toml
[runtime.log]
default_log_level = "INFO"
sink = "console"
console_log_target = "stderr"
console_print_target = "stdout"
pretty_print_mode = "rich"
json_logs_indent = 4
presentation_line_width = 120
is_caller_info_enabled = true
caller_info_template = "file_line_func"
silenced_problem_ids = []

[runtime.log.redaction]
is_enabled = true
extra_patterns = ["tnt-[0-9]+"]

[runtime.log.package_log_levels]
pipelex = "INFO"
openai = "WARNING"
anthropic = "INFO"

[runtime.log.rich_log]
is_show_time = false
is_show_level = true
is_link_path_enabled = true
highlighter_name = "json"
is_markup_enabled = true
is_rich_tracebacks = true
is_tracebacks_word_wrap = true
is_tracebacks_show_locals = false
tracebacks_suppress = []
keywords_to_hilight = ["error", "warning", "failed"]

[runtime.log.otlp]
headers = {}
```

## Migrating From the Log Mode

`log_mode` (`rich` / `poor`), `poor_loggers`, `generic_poor_logger` and `is_console_logging_enabled` are gone; `pipelex migrate` deletes them from an existing file (ledger entry `pipelex-config@5`), and the defaults layer then supplies `sink = "console"`. Two of those keys chose a behaviour the deletion undoes, and no migration may write the replacement, so it is yours to set: a file that had `log_mode = "poor"` chose a plain handler for a process with no terminal, and that process now sets `sink = "json"`; a file that had `is_console_logging_enabled = false` silenced every handler on the root logger, and to silence Pipelex's own records it now sets `pipelex = "OFF"` under `[runtime.log.package_log_levels]`, which deep-merges over the base's `INFO` and leaves the third-party levels alone, since `default_log_level` governs only the loggers that section does not pin; silence for everything takes `default_log_level = "OFF"` and every entry of that section at `OFF`, or the file selects the sink its records should go to instead. A file that had `log_mode = "rich"` needs nothing, and `poor_loggers` and `generic_poor_logger` have nothing to carry over.

## Best Practices

1. **Development Environment**:

    - Keep the `console` sink, and enable caller info for better debugging
    - Use verbose logging levels
    - Enable local variables in tracebacks

2. **Production Environment**:

    - Select the `json` sink behind a log agent, or the `otlp` sink in front of a collector
    - Disable caller info for performance
    - Use INFO or higher log levels

3. **Package Log Levels**:

    - Set noisy third-party packages to WARNING
    - Keep pipelex at INFO for important updates
    - Use VERBOSE only when debugging specific issues

## Related Documentation

- [Logging Tool](../../tools/logging.md) - Using Pipelex logging in your code
- [Log Sink Plugins](../../under-the-hood/log-sink-plugins.md) - The seam behind the `sink` key, and how to write a sink
