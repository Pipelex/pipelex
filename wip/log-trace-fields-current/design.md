---
status: landed
item: L-260927-6b356b
---

# A log line's standard trace fields name OpenTelemetry's current span

This is the log-line half of the ruling Louis took on L-260925-247280 on 2026-09-27, option L2: the standard trace fields of a log line always name OpenTelemetry's current span in the process, and the Pipelex span active in the task travels beside them as `pipelex.trace_id` and `pipelex.span_id`. The span half of the same ruling, the `join_host_trace` opt-in that makes Pipelex's spans current, is L-260927-f30a84 and is out of scope here.

## What the code does today

The item's claims were checked against `dev` at `4520b42a2` and hold.

- `pipelex/system/telemetry/current_span.py`: `span_context_for_logs()` returns the held Pipelex span's context whenever one is held, and falls back to OpenTelemetry's current span only outside a Pipelex span. `otel_context_for_logs()` does the same for the OpenTelemetry API that takes a context, by building a context with the Pipelex span set in it.
- `pipelex/tools/log/json_log_sink.py`: `_trace_context()` writes `trace_id`, `span_id` and `trace_flags` from `span_context_for_logs()`.
- `pipelex/tools/log/otlp_log_sink.py`: `OtlpLogHandler.emit` files each record under `otel_context_for_logs()`, so the OTLP record's own trace context names the Pipelex span.
- `pipelex/tools/log/gcp_log_sink.py`: the entry's `trace` field is `trace_name_for_run(...)`, a trace id derived from the record's `pipeline_run_id` by the tracer's own hash, whether or not any tracer exists, and the entry carries no `spanId` and no `traceSampled`.
- Every line already carries `pipeline_run_id` (`pipelex/tools/log/log_context.py`), and the `gcp` sink carries it as a label, so a run stays joinable without the standard fields.
- The behaviour shipped in v0.66.0 (the CHANGELOG entry "Log lines carry the trace context of the span they were logged in"), so this is a change to a released wire shape.
- Neither `pipelex-server` nor `pipelex-api` reads these helpers, registers a global tracer provider, or instruments FastAPI; nothing in the hosted plane consumes `trace_id` from a log line. Two docs describe the current behaviour: `pipelex-api/docs/logging.md:28` says the trace fields are present "for a line the runtime emits from inside a traced run", which this change makes false, and `pipelex-server/docs/logging.md:14`.

## The rule

For every sink that writes trace context:

- **The standard fields** (`trace_id`, `span_id`, `trace_flags`, or the sink's own equivalent) name OpenTelemetry's current span in the process when it is valid, and are absent otherwise. Pipelex only reads that span; it never sets it.
- **The Pipelex fields** `pipelex.trace_id` and `pipelex.span_id` name the Pipelex span held in the task by `pipelex_span_active`, when one is held, and are absent otherwise.

The two are independent: a line can carry both, either, or neither. Inside a run with a host span it carries both, naming different traces; inside a run with no host span only the Pipelex fields; outside a run under a host span only the standard fields; outside everything, neither. Once L-260927-f30a84 makes the Pipelex span current under its opt-in, the two sets coincide inside a run, and nothing on the log side has to change for that.

## Wire shape per sink

| Sink | Standard fields, from OpenTelemetry's current span | Pipelex fields, from the held Pipelex span |
| --- | --- | --- |
| `json` | `trace_id` (32 hex), `span_id` (16 hex), `trace_flags` (2 hex), as today | `pipelex.trace_id` (32 hex), `pipelex.span_id` (16 hex), right after the standard ones and before the carried fields |
| `otlp` | The log record's own trace context, from `get_current()` | Attributes `pipelex.trace_id` and `pipelex.span_id`, hex |
| `gcp` | The entry's `trace` (`projects/<project>/traces/<32 hex>`), `span_id` (16 hex) and `trace_sampled` (the sampled bit) | Payload keys `pipelex.trace_id` and `pipelex.span_id`, hex |

The `console` sink writes no trace context and is untouched.

## Decisions

- **Flat dotted keys, not a nested `pipelex` object.** `pipelex.trace_id` is the OpenTelemetry attribute-namespace spelling, which the `otlp` sink needs anyway, and the span attributes Pipelex already exports use the same prefix (`pipelex.run.user_id`). One spelling across the three sinks keeps a field's wire name independent of the sink, which is the rule the sinks already follow for every other key. A backend that flattens nested JSON into dotted names, CloudWatch Logs Insights among them, addresses the flat key the way it would a nested one.
- **The Pipelex fields are written whenever a Pipelex span is held, even when they equal the standard ones.** A consumer that joins on `pipelex.trace_id` must find it on every line of a traced run, whatever the operator's configuration. Omitting it when it duplicates the standard fields would save a few bytes and make the key conditional on a setting the reader cannot see.
- **No `pipelex.trace_flags`.** The ruling names the trace and span ids only, and the Pipelex span's flags are the hard-coded `SAMPLED` of its synthetic parent (`pipe_abstract.py`, `llm_worker_abstract.py`), which says nothing a reader can use. L-260927-f30a84 replaces that flag with the host's decision; if the flag ever carries information on its own, adding the key is additive.
- **The `gcp` sink stops deriving a trace from `pipeline_run_id`.** `trace_name_for_run` goes; the `trace` field is built from the current span's trace id, and `span_id` and `trace_sampled` are passed beside it, which the client library's `BackgroundThreadTransport.send` forwards as keyword arguments to the entry (checked against the installed `google-cloud-logging`: `send(record, message, **kwargs)` enqueues the kwargs, and `Batch.log(message=None, **kw)` builds the entry from them). The derivation was also wrong in a way the item does not mention: it filed a line under a trace even when no tracer existed, and under the opt-in the Pipelex trace id will no longer be the hash of `pipeline_run_id` at all. The Pipelex fields in the payload come from the held span, never from a derivation, for the same reason.
- **The new keys are reserved like the others.** `pipelex.trace_id` and `pipelex.span_id` join the `json` sink's `FIXED_KEYS`, which the `gcp` sink reuses as its reserved payload keys, and the `otlp` sink's `RESERVED_ATTRIBUTE_KEYS`, so a carried field of the same name is written under the `field_` prefix on every line, with or without a span.
- **The readers are renamed, not re-pointed.** `span_context_for_logs()` keeps a name while changing its meaning, and every caller of it, the sinks and the tests that assert which Pipelex span a pipe, an LLM call or the Bedrock thread holds, needs to decide which of the two spans it means. `current_span.py` exposes instead:
    - `current_span_context_for_logs() -> SpanContext | None`: OpenTelemetry's current span when valid.
    - `pipelex_span_context_for_logs() -> SpanContext | None`: the held Pipelex span's context.
    - `pipelex_trace_fields_for_logs() -> dict[str, str]`: the two Pipelex fields, hex-encoded, or an empty dict, which all three sinks write.
    - `PIPELEX_TRACE_ID_KEY` and `PIPELEX_SPAN_ID_KEY`, the one place the two names are spelled.

  `otel_context_for_logs()` is deleted: the `otlp` sink passes `get_current()`. The old names disappear rather than stay as aliases, per the workspace's no-backward-compatibility rule; `docs/under-the-hood/log-sink-plugins.md` documents them for sink-plugin authors, so the CHANGELOG entry names the rename.
- **The held span keeps being held.** `pipelex_span_active` and its call sites in `pipe_abstract.py` and `llm_worker_abstract.py` are unchanged: the private context variable is now read only for the `pipelex.*` fields, and it is still what L-260927-f30a84 builds on.

## What it costs

- **An operator who exports Pipelex's spans to their own backend loses the standard-field join inside a run until the opt-in exists.** With an OTLP, Langfuse or custom-PostHog destination and the `json` or `otlp` log sink, a line inside a run today carries the Pipelex span in `trace_id`, so the backend links it to the Pipelex span it received. After this change that line carries the host's span, or none, in `trace_id`, and the Pipelex span only under `pipelex.trace_id`, which a backend's trace view does not follow on its own. The ruling accepted this: the opt-in L-260927-f30a84 is where the two coincide. If both are close to done, releasing them together removes the window; if not, the CHANGELOG entry tells such an operator to join on `pipelex.trace_id` until the opt-in ships.
- **The hosted plane's lines inside a run lose `trace_id` until it opts in.** The runner and the worker register no host tracer, so after this change their JSON lines carry only `pipelex.trace_id` and `pipelex.span_id` inside a run. Nothing there consumes `trace_id` today; L-260927-f30932 turns the opt-in on.
- **A `gcp` line inside a run with no host span is no longer grouped under a trace in Cloud Logging.** The derived trace grouped a run's lines in the Logs Explorer's trace view even with no spans exported anywhere. The `pipeline_run_id` label still selects the run's lines, which is the join the ruling relies on.
- **A released wire shape and a documented plugin API change.** The field semantics shipped in v0.66.0, and the reader names are in the sink-plugin page. Both go in the CHANGELOG as breaking.

## Out of scope

- Making Pipelex's spans current, following the host's sampler, and seeding the run's trace from the host span: L-260927-f30a84.
- Turning the opt-in on in the hosted plane: L-260927-f30932.
- Emitting Pipelex's spans through the host's global provider: L-260927-0355ff.
- The `pipelex-api` and `pipelex-server` logging docs, which describe the fields as they are today: L-260927-a12b10 and L-260927-4e4777, owned by those repos and blocked by this item.
