---
description: "Select where Pipelex log records go with the sink key, and fine-tune logging levels, the console rendering, the JSON, OTLP and Google Cloud Logging sinks and message formatting through TOML configuration settings in pipelex.toml."
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
- `"gcp"`: Google Cloud Logging through the client library, for a process that must write to it directly
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
- The semantic-convention keys the sink writes itself — the source location `code.file.path`, `code.function.name` and `code.line.number`, and the `exception.*` keys — are reserved on every record whether or not it carries an exception, exactly as the `json` sink reserves its own keys: a field named like one of them is carried under the same `field_` prefix, so nothing is overwritten and a field keeps one wire name whichever sink is selected
- The sink never exports its own export path: a record the SDK or the transport emits while an export is in flight is rejected before the handler's lock is taken, so an unreachable collector costs a warning on the export thread and never a loop or a hang at exit. A flush at teardown is bounded by the exporter's own timeout, `OTEL_EXPORTER_OTLP_TIMEOUT`, and whatever the sink raises while it flushes or closes is said on stderr rather than left to interrupt the teardown

## The `gcp` Sink

Configuration section: `[runtime.log.gcp]`, read only when `sink = "gcp"`. The sink writes to Google Cloud Logging through the `google-cloud-logging` client library, which the `gcp-logging` extra installs: `uv pip install "pipelex[gcp-logging]"`. Selecting the sink without the extra stops the boot with the install hint and the `json` alternative named.

### Which of the two to pick

**Most processes on Google Cloud should select `json`, not `gcp`.** Cloud Run, GKE and every platform that runs a logging agent over the container's stdout ingest one JSON object per line with a `severity` and a `message` — exactly what the `json` sink writes — and the lines arrive in Cloud Logging with no client library installed, no credentials to hold and no API call on the logging path. Select `gcp` for the process the agent cannot serve: one with nothing ingesting its stdout, or one that must write to a log name or a project that is not the ambient one.

### Settings

```toml
[runtime.log.gcp]
log_name = "pipelex"
project_id = "my-project"
credentials_file_path = "gcp_credentials.json"
```

- `log_name`: the Cloud Logging log the entries land under. Default: `"pipelex"`
- `project_id`: the project to write to. Left unset, the client library resolves it from the credentials or from the metadata server of the machine the process runs on
- `credentials_file_path`: a service-account JSON file to build the client from. Left unset, authentication is Application Default Credentials, which is what a process already running on Google Cloud has. This is a plain config value rather than a secret id read through the secrets provider, because the log sink is the first capability boot resolves — deliberately ahead of the secrets provider, so that every later line of the boot goes through the sink the configuration chose — and there is no provider to ask when this section is read

### What each entry carries

Each record becomes one Cloud Logging entry with a JSON payload:

- The level maps onto the Cloud Logging severity scale. That scale has nothing below `DEBUG`, so Pipelex's two custom levels, `VERBOSE` and `DEV`, both land there
- The payload carries `message`, `logger` and `exception` when the record carries one, then every field and the `data` attribute flat beside them. The keys the `json` sink reserves are reserved here too, `time` and `severity` included although the payload carries neither — the client library takes both out of band — so a field named like one of them is carried under a `field_` prefix under either sink rather than under one and not the other; a value JSON cannot carry — a non-finite float, a model, a circular structure — is written as text rather than costing the line
- The run-scoped identifiers become the entry's **labels** rather than payload keys: `request_id`, `pipeline_run_id` and `pipe_run_id`, whichever of them the record carries. Cloud Logging indexes labels, so these are what a query filters a run by
- The entry's `trace` field carries the run's own OpenTelemetry trace id, project-qualified as `projects/<project>/traces/<trace-id>`. The id is derived from `pipeline_run_id` by the same hash the tracer uses, so a line and the spans of the run it belongs to agree on it and Cloud Logging files them together
- The entries leave through the client library's background-thread transport, which batches them off the thread that logged, so no record costs an API round trip on the calling thread. The teardown flushes and closes it, and the flush carries a deadline of its own because the library's does not
- What the export path logs never leaves through the sink: the library reports a refused batch through a logger of its own, and a report exported through the pipeline it reports on would fail with it and be reported again. The handler rejects those records, and every record emitted on the library's export thread, before its lock is taken — the same guard the `otlp` sink carries, against the same deadlock at exit
- A refused write is still said: the library marks a refused batch done, so the flush succeeds and nothing else would report it, and the entries in it are lost. The export path's warnings and errors are printed on stderr instead, the first one in each window of time with its traceback and the ones after it counted in a single line once that window has passed — with the next failure, on the next line the process logs, or at the teardown at the latest — so a process whose credentials Cloud Logging refuses says so without printing once per line it logs

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

[runtime.log.gcp]
log_name = "pipelex"
```

## Migrating From the Log Mode

`log_mode` (`rich` / `poor`), `poor_loggers`, `generic_poor_logger` and `is_console_logging_enabled` are gone from the schema, and the defaults layer supplies `sink = "console"` in their place. Run `pipelex migrate`: ledger entry `pipelex-config@5` deletes the four keys from an existing file, and the defaults then take over.

Two of those keys chose a behaviour their deletion undoes, and no operation in the migration vocabulary can write the replacement — so where a choice was made, writing the replacement is yours:

- `is_console_logging_enabled = false` suppressed every record Pipelex's own log calls emitted. Its equivalent is `pipelex = "OFF"` under `[runtime.log.package_log_levels]`, which deep-merges over the base's `INFO` and leaves the third-party levels alone; `default_log_level` governs only the loggers that section does not pin, so on its own it silences none of Pipelex's records. Silence for everything takes `default_log_level = "OFF"` and every entry of that section at `OFF`, and sending the records elsewhere instead means selecting the sink that goes there. `is_console_logging_enabled = true` was the default and asks for nothing: the migration deletes it and the new default renders the same console.
- `log_mode = "poor"` chose a plain handler for a process with no terminal; that process now sets `sink = "json"`. `log_mode = "rich"` chose what `console` renders, and asks for nothing either.
- `poor_loggers` and `generic_poor_logger` have nothing to carry over: every record goes to the one selected sink.

## Best Practices

1. **Development Environment**:

    - Keep the `console` sink, and enable caller info for better debugging
    - Use verbose logging levels
    - Enable local variables in tracebacks

2. **Production Environment**:

    - Select the `json` sink behind a log agent, the `otlp` sink in front of a collector, or the `gcp` sink for a process that must write to Google Cloud Logging directly
    - Disable caller info for performance
    - Use INFO or higher log levels

3. **Package Log Levels**:

    - Set noisy third-party packages to WARNING
    - Keep pipelex at INFO for important updates
    - Use VERBOSE only when debugging specific issues

## Related Documentation

- [Logging Tool](../../tools/logging.md) - Using Pipelex logging in your code
- [Log Sink Plugins](../../under-the-hood/log-sink-plugins.md) - The seam behind the `sink` key, and how to write a sink
