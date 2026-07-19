---
title: TokensUsage Wire Records
description: "The client-facing wire shape of tokens_usages: what a Pipelex API consumer receives on the /execute response and the durable tokens_usages.json artifact."
---

# TokensUsage Wire Records

`TokensUsageRecord` (`pipelex/reporting/usage_records.py`) is the ONLY shape of a run's token usage that crosses the client boundary. Internally, the runtime tracks usage with full-fidelity models (`AnyTokensUsage` carrying a `JobMetadata`); those internals never reach a client — the converter trims them at the two terminal emission points.

## The two surfaces

Both surfaces carry the same record shape:

- **Blocking `/execute` response** — `pipe_output.tokens_usages` on the response body. The API server dumps its full response, then calls `apply_tokens_usage_wire_shape(response_dump, pipe_output=...)` to replace the usage dumps with wire records.
- **Durable `tokens_usages.json` result artifact** — written by the delivery executor as `{"tokens_usages": [...] | null, "usage_assembly_error": string | null}` and relayed verbatim by the platform's runs-results endpoint.

## Record fields

One record per inference call, in completion order:

| field | type | semantics |
|---|---|---|
| `model_type` | string | Kind of inference: known values `llm`, `img_gen`, `extract`, `search`. Open set. |
| `inference_model_name` | string | Human model name (e.g. `gpt-4o`). |
| `inference_model_id` | string | Provider/platform model id (e.g. `gpt-4o-2024-11-20`). |
| `pipe_code` | string \| null | Pipe that made the call — per-pipe cost attribution. |
| `job_category` | string \| null | Known values: `llm_job`, `img_gen_job`, `extract_job`, `search_job`, `jinja2_job`, `mock_job`. Open set. |
| `unit_job_id` | string \| null | Known values: `llm_gen_text`, `llm_gen_object`, `img_gen_text_to_image`, `extract_pages`, `search_sourced_answer`, `search_structured`. Open set. |
| `nb_tokens_by_category` | object&lt;string, int&gt; | Raw provider-reported token counts, keyed by `TokenCategory` values (`input`, `input_cached`, `output`, ...). Open set. `input` is the joined total; `input_cached` is a subset of it, not additive. |
| `cost` | number \| null | Computed USD cost of this call. `null` when the model has no rate table (own-GPU, mock, dry-run). |
| `started_at` | string \| null | ISO 8601. |
| `completed_at` | string \| null | ISO 8601. Duration is client-derivable; not shipped. |

Enum-ish fields are **open sets** on the wire: consumers must treat them as plain strings, so runtime enum churn is non-breaking.

## What never crosses the wire

The converter deliberately drops runtime plumbing and the rate table: `job_metadata` (the object and any nesting of it), `unit_costs`, `user_id`, `session_id`, `request_id`, `pipe_run_id`, `otel_context`, `trace_context`, `content_generation_job_id`, and `pipeline_run_id` (redundant — the envelope already identifies the run). `TokensUsageRecord` is `extra="forbid"` server-side so an accidental new field fails loudly instead of silently widening the contract.

The record shape is also invariant to server-side observability settings: telemetry/tracing on or off, a consumer always gets structurally identical records.

## Cost semantics

`cost` is computed by `compute_tokens_usage_cost` (`pipelex/cogt/usage/cost_registry.py`) from the rates stamped on the internal record at inference time — the same cost engine and the same canonical total as the CLI cost table: input_non_cached + input_cached + output component costs, with the cached-discount fallback (cached input at 50% of the input rate when no explicit cached rate exists). Categories the cost engine excludes from totals (audio, reasoning, prediction) are excluded here too. A run-level total is the sum of per-record `cost` values.

`cost: null` means "unrated" (no rate table: own-GPU models, mock/dry runs) — distinct from `0.0`, which is a rated call that cost nothing.

## Null semantics

- `tokens_usages: null` — usage assembly was off for the run. (The durable file is absent entirely when the run failed — a failed run stores no result files — or, hosted, when it was delivered before the artifact existed.)
- `tokens_usages: []` — assembly on, no inference happened.
- `usage_assembly_error` non-null — assembly *broke* (event-read failure), distinct from "off". It is a bare diagnostic string, mirroring `graph_assembly_error`.

## Where the trim happens (and where it must NOT)

The trim runs only at the terminal, client-facing emitters:

1. `DeliveryExecutor._generate_usage_file` (durable artifact write, worker-side).
2. `apply_tokens_usage_wire_shape` on the `/execute` response dump (called by the API server).

Every internal crossing keeps full fidelity: the runtime-bridge `tokens_usages_dump` (rehydrated back into typed records by the host), `PipeOutput` over the Temporal kajson wire, and the usage-event telemetry stream (NDJSON / event log), which keeps emitting full records including `job_metadata` — that stream is operator-side observability, never returned to clients.

For this reason the trim must never be implemented as a `field_serializer`/`model_serializer` on `PipeOutput`: it would silently trim internal transport too.

## Related pages

- [Cost Tracking & Reporting](../features/cost-tracking.md) — the in-process cost table and CSV export (full internal records, unaffected by this wire contract).
- [Execution Graph Tracing](execution-graph-tracing.md) — the sibling `graph_spec` artifact and the trace event streams.
