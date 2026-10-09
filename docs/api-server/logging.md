# Logging

The server writes structured logs: one JSON object per line, on **stderr**, with every value the line carries sitting as a key of its own. That is the shape a log agent in front of a container ingests without a parser — the CloudWatch agent, the Google Cloud Logging agent, an OTLP collector — so a query filters on a field rather than matching a substring of a message.

## What a line looks like

An error response produces exactly one line. A caller mistake:

```json
{"time": "2026-09-18T13:53:17.919Z", "severity": "WARNING", "logger": "pipelex_api.exception_handlers", "message": "API error 422: InvalidModelCategory", "request_id": "01M2TCP02W04RZG6DTM8AR508C", "event": "api_error", "route": "/v1/models", "error_type": "InvalidModelCategory", "error_domain": "input", "retryable": false, "status": 422, "detail": "Invalid model category. Valid values: extract, img_gen, judgment, llm, search"}
```

A server fault looks the same at `ERROR`, and carries the traceback under an `exception` key.

The `message` is a short, stable sentence built from the HTTP status and the error type — both of them values the server chose. Nothing a caller supplied ever reaches it: the caller-facing explanation rides the `detail` field instead, so a body crafted with newlines or quotes cannot break the line or forge a key. Two layers keep the `detail` value safe to write. Before any sink sees a record, the Pipelex runtime's redaction processor replaces a control character in a field's value with its printable escape, so a newline a caller sent reads as `\n` in `detail`, and replaces a credential it recognises, an `Authorization` header's token or an API key, with `[REDACTED]`. The sink then escapes what it writes, so a quote or an `=` stays inside its value. The processor is configured under `[runtime.log.redaction]` and is on by default.

## The fields a line carries

These keys come from the sink itself and are on every line written by the process, this server's and the Pipelex runtime's alike:

| Key | What it is |
| --- | --- |
| `time` | When the record was created — ISO 8601, UTC, milliseconds, `Z` |
| `severity` | The level name: `WARNING`, `ERROR`, … |
| `logger` | The module that emitted it |
| `message` | The human-readable summary |
| `exception` | The traceback, when the record carries one |
| `trace_id`, `span_id`, `trace_flags` | The process's current OpenTelemetry span, in lowercase hex, when one names a trace. This server registers no tracer and instruments nothing, so as shipped no line carries them; they appear only when the deployment runs it under OpenTelemetry instrumentation of its own that makes a span current |
| `pipelex.trace_id`, `pipelex.span_id` | The Pipelex span a runtime line was logged in, the pipe's or the LLM call's, in lowercase hex. Present on the runtime's lines inside a live run the runtime traces, which it does when AI span tracing is enabled on your own PostHog; never on the server's own lines, an error line included |

The two pairs name different traces. Pipelex's spans belong to a trace of their own, which only Pipelex's exporters receive, so if you export them to a backend of your own, such as Langfuse, an OTLP collector or your PostHog, join a line to them on `pipelex.trace_id` and `pipelex.span_id`. To gather a run's lines whether or not anything traces, use `request_id` or `pipeline_run_id`. How each sink writes both pairs is in the Pipelex documentation's [trace context](https://docs.pipelex.com/0.69.0/tools/logging/#the-trace-context) section.

`request_id` reaches a line in one of two ways, depending on which process writes it. In this server's own process, the request-id middleware binds it on the runtime's log context for the whole request, so every record emitted there while the request is in flight carries it: the server's own lines, like the example above, and the lines the Pipelex runtime emits from inside a run executed in-process (`orchestration_mode = "direct"`), without any call site passing it along. A run dispatched to a worker, under a distributed `orchestration_mode` such as `temporal`, happens in another process, which that binding does not reach, so the id travels with the run instead: both run routes, `POST /v1/execute` and `POST /v1/start`, put it on the run's metadata, and the worker binds it from there while it runs the run's workflow and activities, so the lines written inside them carry the same id. A line the worker writes outside those bindings does not, such as the one the orchestration SDK logs after an activity has failed. One path does not carry it at all yet: when `POST /v1/validate` dispatches its dry run to a worker, the lines that worker writes for it have no `request_id`. The value is the one echoed in the response's `X-Request-ID` header and in the problem document's `request_id` member, so a caller reporting a failure hands you the key to its log lines.

The remaining keys are what the error handlers attach to an `event: "api_error"` record:

| Key | What it is |
| --- | --- |
| `event` | Always `api_error` on an error line — the one key a query filters this server's error stream on |
| `route` | The request's URL path |
| `status` | The HTTP status actually sent, including any API-level override |
| `error_type` | The class or `ErrorType` name the response reports |
| `error_domain` | `input`, `config`, `runtime`, … — who fixes it |
| `error_category` | A Pipelex classification, on the failures it classifies; `unknown` on the catch-all 500 |
| `retryable` | Whether a blind retry can help, when the failure says |
| `detail` | The operator-facing explanation, the same text the response body carries — on an API-authored failure only, see below |
| `user_id` | The authenticated caller, when auth bound one |
| `pipe_code` | The pipe the request named, on a run route whose body parsed |
| `pipeline_run_id` | The run the request named, on a run route whose body parsed |
| `provider`, `model`, `provider_status_code`, `provider_request_id` | The inference provider's own identifiers, on a failure that reached one |

A key whose value is not set for this request is **absent** from the line rather than written as `null`, so a query filtering on presence gets an honest answer.

`detail` is the one field whose absence follows the failure's origin rather than the request's shape, and it is worth knowing which way round. A failure this API authored itself — a validation error, an unknown model category — carries `detail` on the record. A failure that arrives as a Pipelex `ErrorReport`, which is most `5xx` and every domain error, does not: the response body still carries a `detail`, but the record does not, because the body's text has been through disclosure redaction and the cause has not. So a `4xx` from that path logs as `API error 422: SomeError` with no explanation and no traceback, and the response is where the explanation is. Build an operator query on `error_type` and `route`, which every line carries, rather than on `detail`.

Every field in that table is a **record attribute**, which is a different thing from the message. A structured sink — `json` here, and the OTLP sink — writes them beside the message as keys. The Rich console sink shows them after the message as a `key=value` suffix, each value on one line and cut short when long, a handled exception's `error.message` at a far more generous length, and leaves out the run identifiers (`request_id`, `pipeline_run_id`), which a person at a terminal does not need on every line, so `API error 500: PipelexConfigError` is followed by the route, the status and the rest of the fields above. That rendering is for a person reading a terminal; keep `sink = "json"` wherever the lines are read by anything else.

Disposition follows the HTTP status, not the error domain: a `4xx` is a caller mistake and logs at `WARNING` without a traceback; a `5xx` is a server fault and logs at `ERROR` with one. See [Error Responses](error-responses.md) for the response side of the same failure.

## Configuration

The keys live in `[runtime.log]` of the server's own `api/.pipelex/pipelex.toml`, which the image copies to `/root/.pipelex/`:

```toml
[runtime.log]
default_log_level = "INFO"
sink = "json"
console_log_target = "stderr"
pretty_print_mode = "silent"

[runtime.log.package_log_levels]
pipelex = "INFO"
```

- `sink = "json"` selects the one-object-per-line renderer. The alternative, `"console"`, is the Rich renderer meant for a terminal. This server does not ask for Pipelex's `cli` extra, but that does not put the renderer out of reach: `typer` and `instructor` are core Pipelex dependencies that require Rich unconditionally, so Rich is installed in the image and an `import pipelex` loads it. Selecting `"console"` here would therefore give you a working console sink, not a refusal. This key is what keeps the renderer unused, and it is the only thing that does.
- `console_log_target = "stderr"` keeps logs off the data channel.
- `pretty_print_mode = "silent"` suppresses the "Output of pipe" panel an operator pipe would otherwise draw: there is no terminal to draw into, and a server should not spend time rendering on the thread serving a request.
- `[runtime.log.package_log_levels]` raises or lowers one package's level independently of `default_log_level`.

To change any of this for a deployment, mount a `pipelex_override.toml` into `/root/.pipelex/` with just the keys you want different — see [Configuration](configuration.md#providing-your-own-configuration-to-docker). Note that replacing the whole config directory, which that page documents as Option 2, drops the shipped `pipelex.toml` along with the three keys above and silently returns the server to Pipelex's terminal-facing defaults; a layered override does not.

## Uvicorn's own lines

Uvicorn logs through its own handlers, not through the sink above, so its startup banner and its access log are plain text rather than JSON: the banner on stderr, the access log on stdout. Pass `--no-access-log` to turn the access log off, which is what the hosted deployment does; configure uvicorn's `--log-config` if you want its lines structured too.
