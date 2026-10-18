# Logging

The server writes structured logs: one JSON object per line, on **stderr**, with every value the line carries sitting as a key of its own. That is the shape a log agent in front of a container ingests without a parser — the CloudWatch agent, the Google Cloud Logging agent, an OTLP collector — so a query filters on a field rather than matching a substring of a message.

## What a line looks like

An error response produces exactly one line. A caller mistake:

```json
{"time": "2026-10-17T13:53:17.919Z", "severity": "WARNING", "logger": "pipelex_api.exception_handlers", "message": "A request ended in an error response", "request_id": "01M2TCP02W04RZG6DTM8AR508C", "url.path": "/v1/models", "error.code": "request.invalid", "error.type": "RunnerRequestError", "error_domain": "input", "retryable": false, "http.response.status_code": 422, "error.chain": ["RunnerRequestError"]}
```

A fault the server has to fix looks the same at `ERROR`, and adds `error.frames`, where the deepest exception of its chain was raised.

The `message` is the same sentence on every error line, `A request ended in an error response`, whichever failure it reports, so it is the key a query or an alert selects this server's error stream by, following the [log-call conventions](../tools/logging.md#log-call-conventions). Everything about the failure, the HTTP status, the code and the error type included, rides a field of its own, and nothing a caller supplied ever reaches the message. **No error line carries an exception's text or its traceback**, whatever the failure: a traceback prints the text of every exception of its chain, and a foreign exception's text, a pydantic `ValidationError`'s or a method function's, can quote a run's inputs or a model's answer. The line names the classes of the chain under `error.chain` and, on an `ERROR` line, where the deepest was raised under `error.frames`, and the operator reads the error's message, cut to a bounded length, in the operator view's `diagnostics` of the response. Two layers keep the values a caller can shape, such as the `url.path`, safe to write. Before any sink sees a record, the Pipelex runtime's redaction processor replaces a control character in a field's value with its printable escape, and replaces a credential it recognises, an `Authorization` header's token or an API key, with `[REDACTED]`. The sink then escapes what it writes, so a quote or an `=` stays inside its value. The processor is configured under `[runtime.log.redaction]` and is on by default.

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

The two pairs name different traces. Pipelex's spans belong to a trace of their own, which only Pipelex's exporters receive, so if you export them to a backend of your own, such as Langfuse, an OTLP collector or your PostHog, join a line to them on `pipelex.trace_id` and `pipelex.span_id`. To gather a run's lines whether or not anything traces, use `request_id` or `pipeline_run_id`. How each sink writes both pairs is in the Pipelex documentation's [trace context](../tools/logging.md#the-trace-context) section.

`request_id` reaches a line in one of two ways, depending on which process writes it. In this server's own process, the request-id middleware binds it on the runtime's log context for the whole request, so every record emitted there while the request is in flight carries it: the server's own lines, like the example above, and the lines the Pipelex runtime emits from inside a run executed in-process (`orchestration_mode = "direct"`), without any call site passing it along. A run dispatched to a worker, under a distributed `orchestration_mode` such as `temporal`, happens in another process, which that binding does not reach, so the id travels with the run instead: both run routes, `POST /v1/execute` and `POST /v1/start`, put it on the run's metadata, and the worker binds it from there while it runs the run's workflow and activities, so the lines written inside them carry the same id. A line the worker writes outside those bindings does not, such as the one the orchestration SDK logs after an activity has failed. One path does not carry it at all yet: when `POST /v1/validate` dispatches its dry run to a worker, the lines that worker writes for it have no `request_id`. The value is the one echoed in the response's `X-Request-ID` header and in the problem document's `request_id` member, so a caller reporting a failure hands you the key to its log lines.

The remaining keys are what the error handlers attach to an error line. The ones OpenTelemetry's semantic conventions define keep their keys verbatim, and the rest are spelled as the runtime's own lines spell them, so a query written for the runtime's lines finds these too:

| Key | What it is |
| --- | --- |
| `url.path` | The request's URL path |
| `http.response.status_code` | The HTTP status actually sent, including any API-level override |
| `error.code` | The code of the problem the response carries: the body's `code` |
| `error.type` | The class of the exception that escaped, which for an exception that is not a Pipelex error is that exception's own class, and for a failure a route received as a value the class its problem names. A refusal the framework raised, FastAPI's `RequestValidationError`, Starlette's `ClientDisconnect` or an `HTTPException`, is answered by one of the runner's refusals standing in for it, `RunnerRequestError` or `RunnerAuthError`, which `error.type` names and which `error.chain` follows with the framework's class |
| `error.chain` | The classes of the exceptions the failure was raised from or while handling, by name, outermost first, as a traceback would print them, without their text |
| `error.frames` | On an `ERROR` line alone, a fault the server has to fix, where the deepest exception of the chain was raised, as `file:line in function` from the outermost frame inward, without the source lines |
| `error_domain` | `input`, `config` or `runtime` — who fixes it. On a failure the runtime raised it is read from the problem's `domain`, the `input` and `method` domains reading `input`, and the `account` and `operator` domains `config` |
| `error_category` | The inference error category, on a failure the cause chain of which carries one |
| `retryable` | Whether a blind retry can help: the problem's `retry` is `yes` |
| `error.params.<name>` | Each parameter of the problem that the registry declares operator-only, one key per parameter, such as `error.params.component` for the setting a `runtime.misconfigured` names, or `error.params.dependency` for the service a `runtime.unavailable` could not reach. Such a parameter names the runtime's own configuration or one of its components, never a caller's content, and a caller's response leaves it out with the rest of the `diagnostics`, so the line is where the operator reads it whichever view the response took |
| `user.id` | The authenticated caller, when auth bound one. An identity the server refused, a token's `user_id` claim or a forwarded `X-User-Id` that is not a path-safe segment, is never written under it: the warning about the refusal carries the claim's type as `claim_type`, and no value at all for the header |
| `pipe_code` | The pipe the request named, on a run route whose body parsed |
| `pipeline_run_id` | The run the request named, on a run route whose body parsed |
| `backend_name`, `model_handle` | The inference backend that served the model and the handle the pipe named it by, on a failure that reached one; the operator view's `diagnostics` carries them as `provider.name` and `model`. `backend_name` is only ever the backend the error names, which a worker attributes its failure to: a failure no worker attributed carries none, even when the provider's own metadata names who answered, `openai` or `gateway`, since that is neither a backend's name nor an SDK's as the backends configuration spells them, and the record leaves it off rather than write it under `backend_name` or `sdk` |
| `provider_status_code`, `provider_request_id` | The inference provider's own status and request id, on a failure that reached one: the operator view's `diagnostics.provider.status` and `diagnostics.provider.request_id` |

A key whose value is not set for this request is **absent** from the line rather than written as `null`, so a query filtering on presence gets an honest answer.

The record took these keys when the server's lines were brought to the log-call conventions, and it dropped two things it carried before: the `event` key, whose one value, `api_error`, the fixed message now plays the part of, and the message built from the status and the error type, `API error 422: InvalidModelCategory`. A query, a dashboard or an alert written for the earlier record moves to the keys of this one:

| Earlier record | This record |
| --- | --- |
| `event` = `api_error` | `message` = `A request ended in an error response` |
| `message` = `API error <status>: <error type>` | `message` = `A request ended in an error response`, with `http.response.status_code` and `error.type` |
| `route` | `url.path` |
| `user_id` | `user.id` |
| `error_type` | `error.type` |
| `status` | `http.response.status_code` |
| `provider` | `backend_name` |
| `model` | `model_handle` |

The other keys, `error_domain`, `error_category`, `retryable`, `pipe_code`, `pipeline_run_id`, `provider_status_code` and `provider_request_id`, kept their names. `error.code` came later, with the problem document.

Every error line carries `error.code`, since every failure, the runner's own refusals included, is answered by a problem with a registry code. The record is built from the problem's operator view, whichever view the response carried, so `error.type` names the class of the error behind it, and the sentence the response carried is the code's, which `error.code` already names. Build an operator query on `error.code` or `error.type`, with `url.path`. The error's message, which can quote what the caller sent or a foreign exception's text, never rides the line: it rides the operator view's `diagnostics` alone, which only a request the operator authenticated reads in its response (`AUTH_MODE=api_key`, or a trusted proxy's forwarded identity). A request authenticated by a caller's token reads the caller view, so for it the line is the operator's whole account: the code, the classes of the chain, the frames of a fault the server has to fix and the operator-only parameters. Two keys the line carried before the runner's refusals took codes are gone: `detail`, the explanation an API-authored refusal wrote, which `error.code` replaces, and the `exception` key holding a `5xx`'s traceback, which `error.chain` and `error.frames` replace without any exception's text.

Every field in that table is a **record attribute**, which is a different thing from the message. A structured sink — `json` here, and the OTLP sink — writes them beside the message as keys. The Rich console sink shows them after the message as a `key=value` suffix, each value on one line and cut short when long, a handled exception's `error.message` at a far more generous length, and leaves out the run identifiers (`request_id`, `pipeline_run_id`), which a person at a terminal does not need on every line, so `A request ended in an error response` is followed by the path, the status, the error type and the rest of the fields above. That rendering is for a person reading a terminal; keep `sink = "json"` wherever the lines are read by anything else.

The level says who has to act, read from the HTTP status and from the domain of the code, the registry's answer to who must act. A `4xx` is the caller's to act on, a mistake or a benign conflict, and logs at `WARNING`. A `5xx` logs at `ERROR`, with `error.frames`, only when the server has something to fix: its code's domain is `runtime` or `operator`. A `501` logs at `WARNING` without frames whatever its domain, because it states that this deployment does not offer what the request asks for, custom Python without a sandbox, `/v1/start` on a blocking-only orchestrator, a model it serves no backend for: nothing is broken, and any caller could fill the error-rate alerts by asking again. A `5xx` whose code's domain is the caller's, `input`, `method` or `account`, such as a webhook receiver of the caller's own refusing a delivery, logs at `WARNING` too. A request no route serves, a `404` for its path or a `405` for its method, logs at `DEBUG`: scanners probe for such paths by the thousand, and nobody has anything to do about them. See [Error Responses](error-responses.md) for the response side of the same failure.

## Security events

A request a security rule refused writes one more line beside its error line: the **security event**, so that whoever runs the server learns that someone tried to reach what a rule forbids, a private address, another tenant's stored file, a path on the server's disk, a template reaching for a private name. It is a record of its own kind, which a query or an alert selects without reading any text: its `logger` is `pipelex.errors.security_event`, its `message` is `A security rule refused a request`, and its `event.name` is `pipelex.security.refusal`. It is written at `WARNING`, with no traceback.

```json
{"time": "2026-10-17T09:12:03.512Z", "severity": "WARNING", "logger": "pipelex.errors.security_event", "message": "A security rule refused a request", "request_id": "01M2TCP02W04RZG6DTM8AR508C", "event.name": "pipelex.security.refusal", "error.code": "security.input_url_refused", "error.domain": "input", "error.type": "UriReadRefusedError", "security.target": "url", "security.target_class": "scheme", "run.extras.org_id": "org_abc"}
```

Its keys name the refusal and never its content: the refusal's code under `error.code`, the code's domain under `error.domain`, the class of the error under `error.type`, the kind of thing refused under `security.target`, the class of destination under `security.target_class` when the rule could tell it, the run and the request under `pipeline_run_id` and `request_id`, and each of the labels the body names as `analytics_groups`, the run's extras, under a key of its own, `run.extras.<key>`. The labels are read as soon as a JSON body is parsed, before any of its fields is refused, on every route, so a diagnostic route that runs nothing, `/validate`, `/resolve`, `/codegen` or `/pipe-io`, names whose request it refused as a run route does; labels the runtime's own rules refuse are never written. Never the URL, the path, the template or an input value, which are the caller's content or the method's. The Pipelex documentation's [error model](../under-the-hood/error-model.md#security-refusals-and-the-security-event) lists every value.

The server writes it for the refusals its own boundary decides too, which keep the response they always had: a run body carrying a reserved object key (`pipelex.security.reserved_key`, `security.target` `object_key`), a callback URL whose scheme is not http or https or whose host is a loopback, private, link-local or cloud metadata address (`security.input_url_refused`, with the class of destination), and a resource path or a key of a method tree, `files` or a `bundle_b64` member, that leaves the method: absolute, naming a drive or a network share, or climbing out with a `..` segment, read with either separator, so `..\secrets\key.pem`, `C:/Windows/win.ini` and `\\server\share` are among them (`security.input_path_refused`). A refusal of the shape of a field, an empty callback URL, one with no scheme or no host, or a path that is empty or holds an empty segment, a backslash or a colon, is the caller's mistake and writes no event, under `resources` as under `files`. The event never carries a `pipeline_run_id` a body names: before any run exists, that id is the caller's claim.

A refusal is written once, by the process that raised it, whichever part of that process saw it: during a run executed in-process, before the run while its inputs are read or its method loads, while an orchestration plugin prepares a run in this process before it dispatches it, or in the handler answering the request. A run dispatched to a worker under a distributed `orchestration_mode` is refused in the worker's process, so its event is in the worker's logs, written there by its orchestration plugin, and never in this server's: the failure the server receives back, or never receives for a `/start` run, is not logged a second time. The Pipelex documentation's [error model](../under-the-hood/error-model.md#security-refusals-and-the-security-event) states the rule an orchestration plugin follows.

## Authentication lines

The error line above is the record of every refused request, a `401` included, at `WARNING`. The authentication check before it says why it refused, at a level that depends on who has to act:

- **A caller's own mistake logs at `DEBUG`**: no bearer token, an expired or invalid token, a wrong API key. Each is the line `A caller's credentials were refused`, its `auth_mode` naming the mode in force and its `auth_refusal_reason` one of `missing_bearer_token`, `expired_token`, `invalid_token` and `api_key_mismatch`, with an invalid token's `error.type` and `error.message` beside it. The operator can do nothing about a client holding a stale token, so its refusals add nothing to the warnings beyond the error line of each request.
- **A misconfiguration of the deployment keeps its level**: forwarded identity headers trusted while a request arrives without a user id log at `WARNING`, and an unset `JWT_SECRET_KEY` or `API_KEY` at `ERROR`, each naming the variable in `env_var`. An unknown `AUTH_MODE` writes no line here, because the server refuses to start with it (see [Authentication](index.md#authentication)). A token that verifies against the server's secret but whose `user_id` claim is missing, is not a path-safe segment or is the reserved single-tenant id logs at `WARNING` too: whoever minted it holds the secret, so it is the deployment's token issuer that needs fixing, which the line's `user_action` says.

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

## Blob store lines

A file a request names by its hash is read from the runner's blob store and checked against that hash. Bytes that do not hash to it, or are not the size the store holds the blob at, are a damaged object in the deployment's storage, and the request is answered `500` `pipelex.storage.not_found`, whose verdict is not to retry, since a retry reads the same object (see [Error Responses](error-responses.md)). Beside the request's error line, the store writes one line at `ERROR` naming the object, the one place the operator reads which object to remove, after which the blob is uploaded again:

```json
{"time": "2026-10-17T10:41:09.204Z", "severity": "ERROR", "logger": "pipelex_api.blob_store", "message": "Stored blob bytes do not match their hash", "request_id": "01M2TCP02W04RZG6DTM8AR508C", "blob_sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08", "blob_size_bytes": 14, "read_size_bytes": 14, "storage_scheme": "s3"}
```

Its keys are the blob's hash under `blob_sha256`, the size the store holds it at under `blob_size_bytes`, the size of the bytes read under `read_size_bytes`, and the kind of storage under `storage_scheme`, `null` for a storage plugin whose kind the registry does not list. Never the bytes themselves, which are a caller's file.

## Uvicorn's own lines

Uvicorn logs through its own handlers, not through the sink above, so its startup banner and its access log are plain text rather than JSON: the banner on stderr, the access log on stdout. Uvicorn also logs, with its traceback, any exception that leaves the app it runs, and Starlette's own catch-all raises the exception it answered again for that purpose; the server stops every exception there (`AnsweredErrorBarrier` in `pipelex_api/exception_handlers.py`), so uvicorn never writes an exception's text. The error line above stays the one record of a failure the catch-all answered, even one that ended a response already streaming, since Starlette runs the catch-all then too. A failure no handler recorded, the catch-all's own failure while a response was streaming, or the server's failure to send the answer the barrier built, such as to a client already gone, is written at `ERROR` before it is dropped, as `A request failed after its response had started`, with `url.path`, the status already sent under `http.response.status_code`, absent when the catch-all failed before any status was sent, and `error.type` and `error.chain` naming its classes, never any exception's text. No response answers it: the status and part of the body had already left. Pass `--no-access-log` to turn the access log off, which is what the hosted deployment does; configure uvicorn's `--log-config` if you want its lines structured too.
