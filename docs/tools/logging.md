---
title: "Logging"
description: "Explore Pipelex logging: named fields, the run-scoped context, module-named loggers, custom log levels, the console, json and otlp sinks, structured data logging and the log-call conventions."
---

# Pipelex Logging System

## Overview

Pipelex logs through one facade, `from pipelex import log`, built on Python's standard `logging`. A call takes a message, optional named fields and the usual presentation options; the run-scoped identifiers are bound once at a process entry and stamped onto every record emitted in scope. Fields and identifiers ride the stdlib `LogRecord` as attributes, never spliced into the message text, so a structured sink writes them as keys while the console shows the fields after the message, coloured by name. Where the records go is one config key, `sink` under `[runtime.log]`: `console` renders them through Rich, `json` writes one JSON object per line, `otlp` ships them to an OpenTelemetry collector, and a plugin can register another. The keys are in [Logging Configuration](../configuration/config-practical/logging-config.md) and the seam itself in [Log Sink Plugins](../under-the-hood/log-sink-plugins.md).

## Log Levels

Pipelex uses the standard Python log levels and adds two of its own, `VERBOSE` below `DEBUG` and `OFF` above everything. Each level makes a promise about what a line at that level means:

| Level | Value | What a line at this level means |
|-------|-------|---------------------------------|
| VERBOSE | 5 | Step-level tracing for Pipelex's own developers, following the runtime through its steps |
| DEBUG | 10 | What you would need to diagnose a problem from a log a user sends |
| INFO | 20 | A lifecycle milestone, and there are few of them |
| WARNING | 30 | A handled degradation, or a user misconfiguration worth fixing; a warning is actionable |
| ERROR | 40 | A run failed or data was lost |
| CRITICAL | 50 | The process cannot go on |
| OFF | 999 | Disable logging |

A line names what it is about, a pipe, a model or a file, and never carries its contents: base64 data, a prompt or a raw response stays out of the log at every level, `DEBUG` and `VERBOSE` included.

## Using the Logger

```python
from pipelex import log

# Basic logging
log.info("Simple message")

# Named fields ride the record as attributes; the message stays narrative
log.info("Scanned the inputs", fields={"file_count": 7, "byte_count": 12_288})

# A named console layout; every sink but the console writes the plain message and the fields
from pipelex.tools.log.console_layouts import LogLayout

log.info(
    "Pipe run starts",
    fields={"pipe_type": "PipeCompose", "pipe_code": "compose_company", "output_concept": "Company", "pipe_depth": 1},
    layout=LogLayout.PIPE_RUN,
)

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

# Verbose logging
log.verbose("Detailed debug information")
```

Each level's method (`verbose`, `debug`, `info`, `warning`, `error`, `critical`) takes the same keyword-only `fields` and `layout`, the second naming a [console layout](#layouts). `title`, `inline`, `problem_id` and `include_exception` keep their meaning beside them. `include_exception=True` carries the exception being handled as the record's `exc_info`, with nothing spliced into the message: the `console` sink renders the traceback under the line, the `json` sink writes it under the `exception` key and the `otlp` sink under the `exception.*` attributes. Outside an `except` block it carries nothing.

## Fields

`fields` is a mapping of named values. Each entry becomes an attribute of the emitted `LogRecord`, which is where a formatter or a sink reads it: `record.file_count` for the example above, or `%(file_count)s` in a stdlib format string. Nothing from `fields` is written into the message, so `record.getMessage()` is exactly the text you passed.

A value can be anything. It rides the record by reference and the sink serializes it on emit, on the calling thread, so what leaves the process is the value as it was at the call, and mutating it afterwards changes nothing already emitted. The `console` sink shows it after the message on one line, as [Fields after the message](#fields-after-the-message) describes, the `json` sink dumps a pydantic model in JSON mode and falls back to `str` for a value JSON does not know, and the `otlp` sink carries a scalar or a sequence of scalars as an attribute and anything else as JSON text; prefer plain JSON-ready values (strings, numbers, booleans, lists and dictionaries of those) for anything meant to be queried later. A value JSON refuses outright, a circular reference or a mapping with a non-string key, is written by the `json` sink as its `repr`, and that costs the value alone: every other field on the line keeps its JSON type, so a number or a boolean beside it is still queried as one.

### Naming convention

- A field name is a `snake_case` identifier, spelled the way the value is spelled where it comes from: a field carrying a payload's `pipeline_run_id` is `pipeline_run_id`, not `pipelineRunId` or `run`.
- Where the [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/general/logs/) define a key for the concept, use that key verbatim, dots included (`http.response.status_code`, `code.function.name`), so an OTLP sink emits it without translation. The three run identifiers have no such key and keep their payload names.
- `request_id`, `pipeline_run_id` and `pipe_run_id` are reserved for the [run-scoped context](#the-run-scoped-context), and `data` is reserved for [structured content](#structured-content). A field of one of those names is accepted and never dropped: it takes precedence over the context for the three identifiers, and a `data` field rides under `field_data` whatever the content is. Nothing else should use them.

### Names that are not yours to give

The stdlib refuses an `extra` key that would overwrite one of the record's own attributes (`name`, `message`, `lineno`, `module`, `args`, `asctime` and the rest), and a library's log call never raises. An entry of such a name is therefore carried under the prefix `field_`: `fields={"name": "alpha"}` lands as `record.field_name`. What counts as owned is read off the record actually built, through whatever record factory is installed, so an attribute an OpenTelemetry or tracing instrumentation stamps on every record is a collision too, for a field, a context identifier and `data` alike. The prefix is applied until the name lands on an attribute nobody owns, and entries attach in order, so a call that gives both `name` and `field_name` keeps both values whatever their order: the one that arrives second lands on `field_field_name`.

Two kinds of name are reserved though nothing on a fresh record owns them yet, because both are stamped after the entries are attached and the stdlib's refusal therefore cannot cover them: what the formatter sets (`message`, `asctime`) and what Pipelex's own logging machinery sets — `_pipelex_forwarded`, the marker that tells the sink's handler a record reached it through the boot's holding handler already, `_pipelex_field_names`, the names the call's entries landed on, which is what the console renders, and `_pipelex_layout`, the [layout](#layouts) a call named. Both kinds take the same `field_` prefix, and no mark is ever handed to a sink as something the record carries. Without that reservation, `fields={"_pipelex_forwarded": True}` would have the sink's own filter read the record as one already delivered and drop it whole, and `fields={"_pipelex_layout": "pipe_run"}` would pick the line's layout.

The names Rich's console handler reads off each record ahead of its own settings, `markup` and `highlighter`, are reserved the same way and for the same reason: a field landing on `markup` would turn markup back on for that line, which the console otherwise never reads, and one landing on `highlighter` would be called in the highlighter's place, so `fields={"highlighter": "pygments"}` would raise inside the handler and lose the whole line. Such a field rides under `field_markup` or `field_highlighter`, and neither name is handed to a sink as something the record carries.

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

- **A direct-mode run**: `PipeRun.run` binds `request_id` and `pipeline_run_id` from the job's `JobMetadata` for the whole run, delivery included, through `JobMetadata.log_context()`, and releases the binding when the run returns. The metadata a submission builds carries no `pipe_run_id` yet.
- **Every pipe run**: `live_run_pipe` mints the pipe run's id and binds `pipe_run_id` around the whole of the run, the line announcing it, its span lines and its failure included, so every record emitted during a pipe's run names the run it belongs to, a nested pipe rebinding its own and the outer id coming back when it returns, however it returns. A pipe lifted for absent optional inputs does not run and has no id: its skip line carries the enclosing binding, the parent pipe's or none. This is the binding every orchestration shares, direct or distributed.
- **Every kernel step**: each kernel function that takes a `job_metadata` — `run_llm_text`, `run_llm_object`, `generate_object_content`, `run_extract`, `run_search` and `run_img_gen` — binds it for the length of its call, so a program driving the kernel directly gets lines naming the run and the step. Inside the interpreter the operator hands the kernel the `pipe_run_id` that `live_run_pipe` already bound, so this nested binding changes nothing there.
- **A kernel-driven run**: the host wraps its run in `PipelexKernel.log_context()`, which binds `request_id` and `pipeline_run_id` and no step. The kernel has no run boundary of its own, so this binding is the host's, and each step's binding merges over it. See [The Pipelex Kernel](../under-the-hood/pipelex-kernel.md#the-log-context).
- **An API request**: the runner's request middleware is where `request_id` is bound from the inbound request, for the request's duration. The runner then puts the same id on the run's `RunMetadata`, by passing it as `request_id` to `PipelexMTHDSProtocol.execute` or to `pipeline_run_setup`, so the payload carries it to whichever process runs the pipes, and each of them binds it from there.
- **A durable-execution activity or workflow**: the entry is where the identifiers are bound from the payload the orchestrator handed it.

The last two are the runner's and the orchestration plugin's to bind, beside the payload they read. The runtime provides `log.context` for any identifiers, and `JobMetadata.log_context()` to bind the three a `JobMetadata` carries in one call.

### The trace context

Beside the identifiers, a record names the spans it was logged in, and the structured sinks write them on their own, with nothing for a call site to pass. There are two, read independently of each other:

- **The standard trace fields name OpenTelemetry's current span** in your process, which Pipelex reads and never changes, so your log backend files a line under the same trace as your own spans. The `json` sink writes them as `trace_id`, `span_id` and `trace_flags`, lowercase hex, the keys OpenTelemetry specifies for trace context in a JSON log that is not OTLP; the `otlp` sink as the record's own trace context, so a collector files the record under the span; and the `gcp` sink as the entry's `trace`, `spanId` and `traceSampled`. A line logged where no current span names a trace carries none of them.
- **The Pipelex fields name the Pipelex span active at the log call**, the pipe's or the LLM call's, while Pipelex runs one: `pipelex.trace_id` and `pipelex.span_id`, lowercase hex, as keys in the `json` line and the `gcp` payload and as attributes on the `otlp` record. They are the fields that say which pipe or which LLM call a line belongs to. A line logged outside a Pipelex span carries neither.

So a line carries both, either or neither:

| Where the line is logged | Standard fields | `pipelex.*` fields |
| --- | --- | --- |
| In a Pipelex run, under a span of your own | Your span | The pipe's or the LLM call's span |
| In a Pipelex run, under no span of yours | Absent | The pipe's or the LLM call's span |
| Outside a Pipelex run, under a span of your own | Your span | Absent |
| Outside both | Absent | Absent |

The two sets name different traces inside a run: Pipelex's spans belong to a trace of their own, which only Pipelex's exporters receive. If you export Pipelex's spans to your own backend, join a line to them on `pipelex.trace_id` and `pipelex.span_id`. Every line of a run also carries its `pipeline_run_id`, which selects the run's lines whatever the spans. The `console` sink writes no trace context in any case.

The runtime holds each span it starts as the active Pipelex span from its start to its end, however it ends:

- **A pipe run's span**: `live_run_pipe` starts the span, then runs the pipe with it held, so a line logged by the pipe's own work, a controller's or an operator's and the lines of the extract, image-generation, search or function call an operator makes, names the pipe's span under `pipelex.*`, and a nested pipe's lines name the nested pipe's span until it returns. The line announcing the run is logged before the span starts, under the enclosing span.
- **An LLM call's span**: the LLM worker runs the provider call with its generation span held, so the lines of the call and of its failure name that span under `pipelex.*`, a provider SDK's own lines included.

The runtime starts these spans only when it traces a live run, which it does once telemetry has created its tracer, with AI span tracing enabled on your own PostHog, as [Telemetry](../setup/telemetry.md#pipelexs-spans-in-your-process) describes. Otherwise it holds no span, as it does when its tracer is a no-op one, under `OTEL_SDK_DISABLED` for instance, which starts no span of its own, and a line carries no `pipelex.*` fields. A boot line held until the sink arrives is replayed in the context it was logged in, so it keeps both its spans, and a thread started with `asyncio.to_thread` or `contextvars.copy_context` inherits both from the code that started it.

Holding a span is in-process plumbing, like binding the log context: it lives in a context variable of Pipelex's own. **Pipelex never makes its spans current in your process's OpenTelemetry context**, so your own instrumentation, an HTTP client's or a provider SDK's, is never re-parented under a Pipelex span, and an error tracker that reads OpenTelemetry's current span sees yours, not Pipelex's. A span's children take their parent from the job metadata, so a step running in another process gets the parent it always did, and a line that process logs carries `pipelex.*` fields only while the process runs a span of its own, the LLM call's for instance.

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

The processor fails closed. A sink processor that raises is reported on stderr and the record is handed on, which is the right rule for a processor that enriches; for one that removes, it would mean the secret ships. So when the scrub itself fails, a value nested past the interpreter's recursion limit for one, the record is stripped before the failure is reported: its message becomes `[REDACTION FAILED: <exception type>]`, every field and the `data` attribute become `[REDACTED]`, the exception text is dropped, and so is any [console layout](#layouts) the call named, which would otherwise draw the redacted fields in place of the notice. The line says the scrub failed, and nothing of the call leaves with it.

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

The default sink, `console`, renders through Rich with every `[runtime.log.rich_log]` setting, and reads no message as markup (see [Messages are plain text](#messages-are-plain-text)). Rich is the `cli` extra (`pipelex[cli]`), which the command-line tools install. The sink imports Rich when it is built, so a process that selects `json` or `otlp` never loads it through the sink, and one that selects `console` without Rich installed stops at boot naming the extra to install and the `json` alternative. That refusal is not what keeps a server off the console: `typer` and `instructor`, both core dependencies, require Rich, so it is installed even where the extra is not, and a server that forgot to select `json` boots on the `console` sink. A server therefore selects `json` in its own configuration, and sets `pretty_print_mode` to `"poor"` or `"silent"` beside it, since the boot makes neither choice for it (see [Pretty-Print Mode](../configuration/config-practical/logging-config.md#pretty-print-mode)).

### Messages are plain text

The console reads no log message as Rich markup: a message is the caller's text, made of values nobody chose, and it prints exactly as written.

```python
log.error("Expected list[int], got [red]str[/red]")
```

```text
ERROR    🧠: Expected list[int], got [red]str[/red]
```

A tag-shaped span in a message is text like any other: a `list[int]` in a type complaint, a bracketed path, the `[cycle]` marker in the rendering of a circular content, and the `[name]: ` prefix the console puts before a line from a logger with no emoji, such as `[myapp.jobs.nightly]: `. Colour is the console's own: it styles the [fields after the message](#fields-after-the-message) by their names and draws the few [layouts](#layouts), so a call is coloured by naming its fields, never by writing markup into its message. No sink but the console has ever read markup, so a message carrying a tag would reach the `json`, `otlp` and `gcp` sinks with the tag in it, and the rule for a Pipelex log call is to write none. Two checks hold the calls to it, by one reading of what a tag is: a tag Rich would apply as styling, a closing tag, an `@` handler, or a tag naming a style, `[bold]` or `[link=https://pipelex.com]`. A bracketed word that names no style, `list[int]` or `[openai]`, passes, since it prints as written. The [log-call guard](../contribute/log-calls.md), `make check-log-calls`, reads the source of every call: it refuses such a tag in the literal text of a message, its title or its inline title, at every level, that text folded across concatenations and named literals the way it reaches the console. A test checks the messages of one run: it runs the pipes of one test bundle live, a sequence nesting a structuring step, parallel summaries and a condition, with a stand-in worker answering every model call, and fails on any message the run logs, at any level, that holds such a tag, whatever built it. A message the guard cannot read, a value built at run time, is covered only when that run logs it.

Rich still honours its own per-record `markup` attribute, which a third-party library may set on a record it logs to ask for markup. No Pipelex call can set it: a field of that name is [reserved](#names-that-are-not-yours-to-give) and lands under `field_markup`.

### Fields after the message

The console shows the fields a call gave after its message, as a `key=value` suffix, the way structlog's console renderer and pino-pretty do:

```python
log.info("Scanned the inputs", fields={"file_count": 7, "source": "inbox/march"})
```

```text
INFO     🧠: Scanned the inputs file_count=7 source=inbox/march
```

- **What is shown.** The fields the call attached, in the order it gave them, under the name each landed on (`field_name` for a field called `name`). The run identifiers (`request_id`, `pipeline_run_id`, `pipe_run_id`) are left out, since they are the same on every line of a run and would drown the message, and so is `data`, the structured content the message already renders. Nothing else on the record is shown: neither the stdlib's own attributes, nor Pipelex's marks, nor what a record factory or a third-party library stamped on it.
- **How a value is written.** On one line: a string bare, or quoted when it is empty or holds a space, an `=`, a `"`, a `\` or a character a terminal would act on. Inside the quotes a backslash is written `\\`, a quote `\"` and any character a terminal would act on as its escape (`"line\nbreak"`), so `fields={"a": "b=c"}` prints `a="b=c"` rather than a second pair. A number, a boolean, `None`, a mapping, a list or a pydantic model is written as compact JSON (`true`, `null`, `{"key":"value"}`, `["a","b"]`), and anything else as its text. A value longer than 80 characters is cut short and ends with `…`, except `error.message`, a handled exception's text, which is cut only past 2000 characters, quoted and escaped the same way: its diagnosis, a cause chain or a parse error's location, is what a fragment would lose, while a dependency's raw output, a validation error's every line or git's stderr, would flood the terminal uncut. A key is written the same way, so a field whose name holds a line break, a space, an `=` or an escape sequence is quoted and escaped rather than forging a line or a second pair: `fields={"x=1": 2}` prints `"x=1"=2`. The [redaction](#redaction) has run before the console renders, so a secret is already `[REDACTED]`.
- **Never markup.** The suffix is built as styled Rich `Text`, not as a markup string, so a value carrying `[red]x[/red]` prints exactly that.

There is no setting to hide the suffix: it carries the values a message used to interpolate, so hiding it would hide what the line is about.

### The style map

A field's value is coloured by the field's name, wherever it appears, from one table in `pipelex/tools/log/console_fields.py` (`FIELD_STYLES`): a pipe code red, a concept (`output_concept`, `concept_ref`, `concept_code`) bold green, a pipe type white, a stuff name cyan and a domain bold magenta, the colours the pipe announcement and the stuff renderings have always used. A field outside the map, and every key, is dimmed. The colour follows the name the field was given, so a `pipe_code` that landed on `field_pipe_code` because a record factory owns `pipe_code` is still red. So a call is coloured by naming its fields, never by writing markup into its message. The map lives in code, with no configuration key; extending it is a one-line change beside the sink.

### Layouts

A few lines have a shape that matters on a terminal, the pipe-run tree above all. For those, a call names a layout, a Rich template over the record's fields registered in `pipelex/tools/log/console_layouts.py`. Every live pipe run announces itself this way, with the message `Pipe run starts` and the pipe in the fields, and the console draws the line byte for byte as it did when the announcement was markup in its message:

```python
from pipelex.tools.log.console_layouts import LogLayout

log.info(
    "Pipe run starts",
    fields={"pipe_type": "PipeCompose", "pipe_code": "compose_company", "output_concept": "Company", "pipe_depth": 1},
    layout=LogLayout.PIPE_RUN,
)
```

```text
INFO     🧠:    ↳ PipeCompose: compose_company → Company
```

- **The console renders the layout in place of the message**, after the logger's emoji, and every other sink ignores it: the `json`, `otlp` and `gcp` sinks write the plain message, `Pipe run starts`, and the fields, and never the layout's name, which rides the record under a reserved mark. The name is explicit at the call, so rewording the message cannot lose the layout, and it is a `LogLayout` member, so a misspelt one is a type error.
- **Every value is escaped** with Rich's own escape before it is substituted, the values the layout derives included, so a field carrying `[red]x[/red]` prints literally. A value is written on one line and cut short past 80 characters, as in the suffix, except that a string is never quoted.
- **The fields a layout presents are not repeated after it**; any other field the call gave still follows as the suffix, and the run identifiers stay hidden.
- **A layout that cannot be filled costs nothing but itself.** A field it needs is missing, a value its derivation refuses, or anything else the layout raises: the console falls back to the message and shows every field after it.
- **A layout is for a string message.** A call whose content is anything else, a mapping, a list or a model, keeps its layout off the record, and the console renders its message: the message is the only place that content renders, since the suffix never repeats `data`, and a content JSON refuses, a circular one for instance, lives only in the message's `repr`. A record whose [redaction](#redaction) failed loses its layout too, so the notice saying the scrub failed is what prints.
- **A layout replaces the whole message.** A line rendered through a layout shows neither the title nor the inline text the call gave, nor any [caller information](#caller-information), all of which belong to the message it replaces. A traceback the record carries still prints under the line, as it does under a message, and the fields stay on the line above it, whether Rich renders the traceback or `is_rich_tracebacks = false` has it printed as plain text.

The registry holds these layouts:

| Layout | Fields it presents | What it draws |
| --- | --- | --- |
| `LogLayout.PIPE_RUN` | `pipe_type`, `pipe_code`, `output_concept`, `pipe_depth` (an integer, `0` at the top level and at most `100`) | `PipeCompose: compose_company → Company`, indented three spaces per level of depth and behind `↳` when nested, in the style map's colours. A depth of another type, or out of range, falls back to the message. The pipe announcement names it, and only a live run announces itself, so the line carries no run mode |

A layout is a `ConsoleLayout`: a `template` of Rich markup whose placeholders are bare field names (`{pipe_code}`, never an attribute, an index or a format spec, which registration refuses), the `presented_fields` the suffix leaves out, and, for a shape a template cannot express alone, a subclass whose `derived_values` computes presentation values such as an indentation from the fields.

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

## Log-call conventions

Pipelex's own log calls, in `pipelex/` and in the API server's `api/pipelex_api/`, follow these conventions, so that a line written today can be grouped, counted and filtered in a log store tomorrow. The [log-call guard](../contribute/log-calls.md), `make check-log-calls`, holds every call to the ones that can be read off the source, the fixed message at INFO and above and the absence of markup; the rest is for review. Code of your own that logs through `log` is welcome to follow them too.

### A fixed message

A message is a sentence that reads the same on every emission. A log store groups and counts lines by their message, and an interpolated value makes a different string of every line, so a question as plain as "how many of these today" needs a regular expression. The message is the key a query, a dashboard or an alert selects a line by, and Pipelex carries no separate `event` field beside it, so rewording a message is a change made on purpose.

At INFO and above, the message is a literal written at the call: no f-string, no `%`, no `+` and no `.format()`, and no message built elsewhere and passed in, since nothing can tell that one is fixed. DEBUG and VERBOSE may keep an f-string, because a person at a terminal reads them; fields are welcome there too.

```python
# Not this: the alias makes every line a different message, and the exception is buried in the text
log.warning(f"Could not load dependency '{alias}' pipe '{pipe_code}': {exc}")

# This: one message, the values in fields, the exception's class and text as fields of their own
log.warning(
    "A pipe of a dependency could not be loaded",
    fields={"dependency_alias": alias, "pipe_code": pipe_code, **error_fields(exc=exc)},
)
```

### Values in fields

What varies goes in `fields`, named by the [naming convention](#naming-convention), and one concept has one name across the codebase, so that a query written for one line finds every line about the same thing. Pipelex's own concepts take the names in the table below. A concept the OpenTelemetry semantic conventions define takes their key verbatim: `file.path` for a path on disk, `url.full` for a URL, `user.id` for a user, `error.type` for the class of an error, and the `gen_ai.*` keys for inference, such as `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.request.temperature`, `gen_ai.operation.name`, `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens`. A `gen_ai.*` key means on a log line what it means on Pipelex's LLM span: `gen_ai.request.model` is the model's handle and `gen_ai.response.model` the provider's id of the model serving it. A line about an inference call carries them beside `model_handle`, `backend_name` and `sdk`, so it joins its span in a log store, while `model_handle` names the handle on every line about a model, inference or not. A count is named `<what>_count` (`concept_count`) and a duration `duration_ms`, in milliseconds.

| Field | What it names |
| --- | --- |
| `pipe_code` | The pipe a line is about, bare or qualified by its domain, as the call site holds it: `compose_company`, `company.compose_company` |
| `pipe_type` | The pipe's class: `PipeLLM`, `PipeCompose` |
| `pipe_depth` | How deep a pipe run is nested, `0` at the top level |
| `is_dry_run` | Whether the run is a dry run |
| `output_concept` | The concept a pipe produces |
| `concept_ref` | A concept's qualified reference, `<domain>.<Code>`: `company.Company` |
| `concept_code` | A concept's code alone, where the call site has no domain for it: `Company` |
| `domain_code` | A domain's code: `company` |
| `stuff_name` | The name a stuff has in working memory |
| `variable_path` | A dotted path into working memory, as a pipe's inputs name it: `invoice.total` |
| `library_id` | The library a load or a lookup runs in |
| `package_address` | A method package's address, as its manifest declares it or a bundle's reference names it: `github.com/acme/methods/invoices` |
| `dependency_alias` | The alias under which a package's manifest declares a dependency; a dependency a bundle names by address has its address as its alias |
| `method_ref` | The address a caller names a method by, selector and tag included, as the run routes and the CLI take it: `github.com/acme/methods/invoices@v1.2.0` |
| `commit_sha` | The commit a fetched method package was cloned at |
| `mthds_version_constraint` | The MTHDS standard versions a package accepts, as the `mthds_version` of its `METHODS.toml` declares them: `^4.0.0` |
| `mthds_standard_version` | The MTHDS standard version this runtime implements |
| `mthds_paths` | The `.mthds` files a load reads, as a list of paths |
| `crate_fingerprint` | The fingerprint that identifies a normalized crate in the library it is loaded into |
| `model_handle` | The handle a pipe or the model deck names a model by, an alias included: `gpt-image-2`, `@default-premium` |
| `backend_name` | The inference backend serving a model, as the backends configuration names it: `anthropic`, `bedrock` |
| `sdk` | The SDK a backend reaches a model through, as the backends configuration names it: `openai`, `bedrock_anthropic` |
| `fixed_temperature` | The one temperature a model accepts, as its constraints declare it, used in place of the one requested |
| `node_id` | A node of a run's execution graph, as the graph tracer names it |
| `env_var` | The name of an environment variable, never its value |
| `error.type`, `error.message` | A handled exception's class name and its text, as [Exceptions](#exceptions) describes |

`pipe_code`, `pipe_type`, `output_concept`, `concept_ref`, `concept_code`, `domain_code` and `stuff_name` are in the console's [style map](#the-style-map), which colours their values wherever they appear. A concept missing from the table is added to it in the change that first logs it.

### Exceptions

An exception rides the record, never the message. Spliced into the text, `{exc}` makes the message vary, loses the exception's type and traceback, and gets only the pattern half of the [redaction](#redaction), where a field also has its control characters escaped. So:

- **At ERROR and CRITICAL**, inside the `except` block, pass `include_exception=True`: the record carries the exception, and each sink writes its type and its traceback its own way.
- **At WARNING and below**, an exception the code expected and handled rides as two fields, `error.type`, its class's name, and `error.message`, its text, with no traceback, through `error_fields` (`pipelex.tools.log.error_fields`): `fields={"package_address": address, **error_fields(exc=exc)}`. A warning promises a degradation that was handled, and a traceback of Pipelex's own frames repeated on every emission of an expected failure says nothing a reader can act on; the facade's `warning` takes no `include_exception` for that reason. Where the diagnosis is the cause chain rather than the exception's own text, as when a fetch fails in git underneath, `error_fields(exc=exc, text=...)` carries the chain instead. The console cuts `error.message` only past 2000 characters, where it cuts every other field's value at 80, so the chain reaches the terminal whole without a dependency's raw output flooding it.

`error.type` is the OpenTelemetry key for the class of error an operation ended with. `error.message` is the key OpenTelemetry gave an error's text before deprecating that general attribute in favour of domain-specific ones; Pipelex keeps it as `error.type`'s companion because the `exception.*` keys belong to the sinks, which write them for a record that carries the exception itself and prefix a field spelling one.

### What a line never carries

- **No run identifier in the text.** `request_id`, `pipeline_run_id` and `pipe_run_id` are stamped on every record by the [run-scoped context](#the-run-scoped-context); a message repeating one is noise, and a field passing one is only for a call that speaks about a run it is not running under.
- **No payload contents, at any level.** No prompt text, no base64 data, no raw response and no whole object: a size, a count, a hash or a code instead, as the [level table](#log-levels) already says of every level.
- **No markup and no emoji in a message.** Colour is the console sink's job: it colours a value by its field's name and draws the few [layouts](#layouts), and its emoji are its own per-logger decoration. Markup in a message travels to every sink as literal tags, the console's included, since it reads no message as markup (see [Messages are plain text](#messages-are-plain-text)). Markup keeps its place in the CLI's own output and in the pretty-print channel, which are presentation to a person and not log records.

### Choosing a level

The [level table](#log-levels) states what a line at each level means, and choosing the level of a call follows from it. There is no DEV level.

- **ERROR** says a run failed or data was lost, and that somebody should look; it carries the exception with `include_exception=True` when there is one.
- **WARNING** must be actionable: a degradation that was handled, or a misconfiguration the user can fix. A warning nobody can act on moves down to DEBUG, or up to ERROR when something was in fact lost.
- **INFO** marks a lifecycle milestone, and there are few of them, because Pipelex is also a library and a library is quiet at INFO.
- **DEBUG** answers a question you would ask on reading a log a user sent: which file was read, which fallback was taken, why a model was left out.
- **VERBOSE** follows the runtime step by step, for Pipelex's own developers.

## Related Documentation

- [Logging Configuration](../configuration/config-practical/logging-config.md) - Configure log behavior and select the sink in `pipelex.toml`
- [Log Sink Plugins](../under-the-hood/log-sink-plugins.md) - The sink seam, the built-in sinks and how to write one
- [CLI](./cli/index.md) - Commands that surface runtime logs during development
- [Log-Call Guard](../contribute/log-calls.md) - The check that holds Pipelex's own log calls to the conventions above, and its baseline
