---
status: draft
item: L-260927-6b356b
---

# Plan: log trace fields follow OpenTelemetry's current span

The design is [`design.md`](design.md). The work is one pull request on `feature/Log-trace-fields-current`, in the order below, tests first at each step. Its size does not call for checkpoints between steps; the one review gate is before the PR opens.

## Steps

1. **The readers** (`pipelex/system/telemetry/current_span.py`). Rewrite `tests/unit/pipelex/system/telemetry/test_current_span.py` first: the current-span reader returns the host's valid span inside and outside a held Pipelex span and `None` with no valid current span; the Pipelex reader returns the innermost held span and `None` outside one; the fields helper renders both ids zero-padded, or nothing; the existing guarantees keep their tests (an exception crossing the block restores the previous span, `None` and a span naming no trace hold nothing, OpenTelemetry's current span is never touched). Then replace `span_context_for_logs` and `otel_context_for_logs` with `current_span_context_for_logs`, `pipelex_span_context_for_logs`, `pipelex_trace_fields_for_logs` and the two key constants, and rewrite the module docstring around the two-span rule.
2. **The `json` sink.** In `tests/unit/pipelex/tools/test_log_json_trace_context.py`, replace the "Pipelex span rather than the host's" test with the four cases of the rule (inside a run with a host span, inside a run without one, outside a run under a host span, outside everything), add the key order (standard trace keys, then the Pipelex ones, then the fields), the reservation of the two new keys with and without a span, and keep the held-boot-line test, now asserting both sets. Then `_trace_context()` reads the current span, the payload adds `pipelex_trace_fields_for_logs()`, and `FIXED_KEYS` gains the two keys.
3. **The `otlp` sink.** In `tests/unit/pipelex/tools/test_log_otlp_trace_context.py`, the same four cases against the in-memory exporter: the record's trace context names the host span or nothing, and the `pipelex.*` attributes name the held span or are absent; plus the reservation. Then `emit` passes `get_current()`, `_attributes` writes the Pipelex fields right after the source location, and `RESERVED_ATTRIBUTE_KEYS` gains the two keys.
4. **The `gcp` sink.** In `tests/unit/pipelex/tools/test_log_gcp_sink.py`, replace the "run's own trace id" test with the four cases on the fake transport: `trace`, `span_id` and `trace_sampled` from the current span or absent, the Pipelex fields in the payload or absent, and a record carrying `pipeline_run_id` with no span getting no `trace`. Extend `test_log_gcp_client_library_contract.py` so the installed library renders the `trace`, `span_id` and `trace_sampled` the sink passes into the entry, and drop the `trace_name_for_run` test from `test_log_gcp_sink_mapping.py`. Then replace `trace_name_for_run` with a builder taking the project and a trace id, pass the three kwargs only when a current span exists, write the Pipelex fields into the payload, and drop the `hash_md5_to_int` import. Check `test_log_gcp_json_payload_parity.py` still holds with the new reserved keys.
5. **The span-holding tests.** `test_live_run_pipe_current_span.py`, `test_llm_worker_current_span.py` and `test_bedrock_boto3_current_span.py` assert which Pipelex span the runtime holds; move them to `pipelex_span_context_for_logs()`, and in the Bedrock test assert the thread sees the host span through `current_span_context_for_logs()` as well.
6. **The docs.**
    - `docs/tools/logging.md`, "The trace context": replace the three-step precedence with the two independent sets and the four cases, keep the paragraph on which spans the runtime holds, and say the `pipelex.*` fields are the ones that name the pipe or the LLM call.
    - `docs/setup/telemetry.md`, "Pipelex's spans in your process": the third bullet says the standard fields name your current span and the Pipelex span rides under `pipelex.*`, and what an operator exporting Pipelex's spans joins on until the opt-in exists.
    - `docs/configuration/config-practical/logging-config.md`: the `json` line description and its example line, and the `gcp` entry's `trace`, `span_id` and `trace_sampled` and payload keys.
    - `docs/under-the-hood/log-sink-plugins.md`: the reader functions a sink plugin calls, the reserved keys, and the `json` row of the sink table.
    - The module docstrings of the three sinks.
7. **The CHANGELOG**, under `[Unreleased]`, one breaking entry: the standard trace fields name OpenTelemetry's current span, the Pipelex span rides as `pipelex.trace_id` and `pipelex.span_id` in the `json`, `otlp` and `gcp` sinks, the `gcp` sink's `trace` is no longer derived from `pipeline_run_id` and now carries `span_id` and `trace_sampled`, and `span_context_for_logs` and `otel_context_for_logs` are replaced by the new readers.
8. **The gates.** `make agent-check`, then `make agent-test`, then `/rev` at the depth `ledger review-profile` derives, then the PR `feature/Log-trace-fields-current · L-260927-6b356b` with `Closes L-260927-6b356b`. Flip this plan and the design to `landed` inside the PR.

## Follow-ups filed with this plan

- `pipelex-api/docs/logging.md:28` describes the trace fields as present on any line inside a traced run, which stops being true: L-260927-a12b10, owned by `pipelex-api`.
- `pipelex-server/docs/logging.md:14` describes the trace fields without the Pipelex ones: L-260927-4e4777, owned by `pipelex-server` and related to L-260927-f30932, which changes the same paragraph again when the hosted plane opts in.

## Open question

- **Release together with L-260927-f30a84, or alone?** Alone, the change opens the window the design's "What it costs" names for an operator who exports Pipelex's spans to their own backend. The recommendation is to land this independently, since it is small and the opt-in is not, and to release it alone unless the opt-in is ready for the same release; the CHANGELOG entry covers the window either way.
