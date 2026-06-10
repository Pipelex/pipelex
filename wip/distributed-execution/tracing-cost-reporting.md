# Tracing & Cost Reporting — As Built

> **Status**: Shipped — the current tracing & cost-reporting implementation (supersedes an earlier distributed-tracing design, now retired). T1 **and** T2 are now fixed; cross-worker cost reporting works end to end.
> **Last updated**: 2026-06-07
> **Related**: [the distributed-execution plan](README.md), [the registry overview](../registry/cost-reporting-overview.html), and [the registry feature](../registry/README.md).

This file documents what actually shipped, plus the known gaps that the plan addresses.

---

## What shipped

The original Step 6 plan called for a `TracingActivityInboundInterceptor` to set up an NDJSON event log per standalone activity. The team picked a different design:

- **Pluggable backends behind `EventLogProtocol`** — `pipelex/tracing/event_log_protocol.py`. Implementations:
  - `NdjsonEventLog` — local file backend (`pipelex/tracing/ndjson_event_log.py`).
  - `DynamoDBEventLog` — cloud backend (`pipelex/tracing/dynamodb_event_log.py`), schema-compatible with `pipelex-api-infra`'s `TraceEventDynamoDBAdapter`. Available behind `pip install "pipelex[dynamodb]"`.
  - `BufferingEventLog` — in-memory buffer used **inside** Temporal workflow code (`pipelex/tracing/buffering_event_log.py`). Synchronous I/O is forbidden in workflow context, so workflows buffer here and flush via an activity.
  - `InMemoryEventLog` — for tests.
  - Backend chosen at runtime via `make_event_log(tracing_config)` in `pipelex/tracing/event_log_factory.py` (`TracingBackend.NDJSON | DYNAMODB | TEMPORAL_DYNAMODB`).
- **Workflow → activity flush, not interceptor.** `WfPipeRouter.run()` (`pipelex/temporal/tprl_pipe/wf_pipe_router.py`) wires a `BufferingEventLog` into the per-workflow `GraphTracerManager` and into the `ReportingManager` via `set_event_log(context_key=workflow_id, ...)`. After pipe execution, buffered events are drained and persisted by `act_flush_trace_events` (`pipelex/temporal/tprl_pipe/act_flush_trace_events.py`), which runs the synchronous boto3 / file writes off the workflow thread. Replay determinism (audit finding H1): the flush activity is scheduled unconditionally whenever the payload carries a `trace_context` (the activity no-ops on an empty list), and only workflow-thread emissions (inline tracer graph events, dry-run inline usage) land in the buffer — `ReportingManager` routes activity-side usage emissions to the per-process fallback even when the activity is co-located with the workflow worker, so the buffer content and the command stream are pure functions of payload + history.
- **Per-context keying** — `ReportingManager` holds a dict of `_event_log_contexts` keyed by `graph_context.lookup_key`, so concurrent workflows don't trample each other.
- **Direct mode unchanged** — `pipeline_run_setup.py:282` calls the same `set_event_log` path, so the same `EventLogProtocol` machinery runs in-process for non-Temporal execution.
- **Tracing assembly across workers (graph + cost)** — `pipelex/pipe_run/tracing_assembly.py` (`assemble_tracing` / `assemble_tracing_on_output`) and `pipelex/temporal/tprl_pipe/act_assemble_tracing.py` read all events for a `pipeline_run_id` from the configured backend **once** and feed them into both `GraphSpecAssembler` (when `--graph`) and `UsageAggregator` (when `--costs`), setting `PipeOutput.graph_spec` and `PipeOutput.tokens_usages` respectively. (Renamed from `graph_assembly.py` / `act_assemble_graph` when T2 landed — see below.)

## What works today

| Scenario | Captured? | How |
|---|---|---|
| Direct mode (single process) | ✅ | `pipeline_run_setup` configures event log on `ReportingManager`; events emitted in-process. |
| Single-worker Temporal (workflows + activities on same Worker bundle) | ✅ | Activity-side usage events emit through the per-process fallback — same path as split workers, never the workflow's in-sandbox buffer (replay determinism, audit finding H1). Workflow-thread emissions (dry-run inline usage, graph events) use the buffer registered by `WfPipeRouter`. |
| Parent + child workflows on different worker processes | ✅ | Each workflow's process buffers its own events and flushes its own slice. All slices land in the same NDJSON dir / DynamoDB partition keyed by `pipeline_run_id`. |
| Cross-worker **graph** assembly | ✅ | `assemble_tracing_on_output` / `act_assemble_tracing` reads all events for the `pipeline_run_id` and runs `GraphSpecAssembler`. |
| Cross-worker **cost** assembly + report | ✅ | Same single event read feeds `UsageAggregator` → `PipeOutput.tokens_usages`; the submitter renders one cost report from it. (T2 — fixed.) |

## What is broken or missing

### Issue T1 — Activities on standalone (separate-process) workers lose usage events — **FIXED (P0)**

**Severity (was)**: Blocked the whole point of distributed activity workers.

**Status**: Resolved (P0 in [the distributed-execution plan](README.md)).

The fix has two independent parts that ship together:

- **Runner-side fallback in `_emit_usage_event`.** When the activity's `ReportingManager` has no entry in `_event_log_contexts` for the workflow's `lookup_key`, it now falls back to a process-local event log built from `tracing_config`. The event log is cached per process via `pipelex.tracing.activity_event_log.get_or_create_activity_event_log` (guarded by a module-level `threading.Lock` so concurrent first-emitters from multiple activity threads agree on a single writer_id and instance). The fallback uses `graph_context.tracer_key or graph_context.graph_id` as `workflow_id` (no new `JobMetadata` field needed — `tracer_key` is already populated by `WfPipeRouter.run`). Specific exceptions (`OSError`, `MissingDependencyError`, `PipelexConfigError`, `botocore.ClientError`) are caught at WARNING — never silently dropped, never `except Exception`. A one-shot warning per process records that the fallback engaged.
- **Writer-id disambiguation in `TraceEvent`.** A new `writer_id: str = "primary"` field makes `(workflow_id, sequence)` collisions impossible across writers. NDJSON file naming becomes `wf_{workflow_id}__w_{writer_id}.ndjson` for non-primary writers; the `(pipeline_run_id, workflow_id, writer_id)` cache key prevents two writers from sharing a stale file handle. Read-side dedup key is `(workflow_id, writer_id, type, sequence)`; sort key is `(workflow_id, sequence, writer_id)` — sequence primary so a runner-side `UsageReportEvent` does not sort before earlier router events. DynamoDB SK becomes `EVENT#{workflow_id}#{writer_id}#{sequence:010d}`.

The `_get_registry` orphan-accumulation TODO at `reporting_manager.py` is moot: T2 removed the submitter-side `UsageRegistry` entirely (see below), so there is no longer any per-run registry to accumulate or leak. The four `_report_*_job` methods now only emit a `UsageReportEvent` onto the event log; nothing buffers usage in the manager.

The known retry-related over-counting case (R2) is documented and pinned by `test_retried_activity_emits_duplicate_usage_event_documenting_r2`. A `tracing_config.strict_mode` flag (raise instead of WARNING + drop) is deferred — see [the plan, §P0.2](README.md).

### Issue T2 — Cross-worker cost report assembly — **FIXED (P1)**

**Status**: Resolved. Usage now rides on `PipeOutput` exactly like the graph spec, and the submitter renders the cost report from that field — so a cross-worker run produces a single, complete report.

> **Design note (as resolved):** T2/P1 was the same lifecycle as the `UsageRegistry` success-path leak — the leak was the missing *close*, T2 was the missing *replay-populate*, of one per-run cost-aggregation buffer. **Option B (locked) resolved both by removal:** usage is assembled from the trace-event stream at the end of the run and rides back on `PipeOutput.tokens_usages`; with nothing populating a submitter-side registry, the registry was deleted and the leak became structurally impossible. The unified model and the locked decision are explained in [the registry overview](../registry/cost-reporting-overview.html); the feature index is [`../registry/README.md`](../registry/README.md).

**As built:**

- The single event read in `assemble_tracing` / `act_assemble_tracing` (see "What shipped" above) now feeds `UsageAggregator.aggregate(events) → list[AnyTokensUsage]` (`pipelex/tracing/usage_aggregator.py`) when `--costs` is on, setting `PipeOutput.tokens_usages` in both direct and Temporal modes.
- The submitter renders it via `CostRegistry.generate_report(tokens_usages=...)` — fed from `pipe_output.tokens_usages`, never from a process-local registry. The main CLI path goes through `pipelex/reporting/cost_report_renderer.py::render_run_cost_report`.
- The decoupling that made this safe: a dedicated `--costs` / `is_generate_costs` switch (default on) gates usage events + `UsageAggregator` over the shared event-log transport, independent of `--graph`. Previously usage events only emitted when `--graph` was on.
- The retired surface: `ReportingManager.inject_tokens_usages` / `generate_report` / `open_registry` / `close_registry` and the `UsageRegistry` model are **gone** — there is no submitter-side registry left to populate.

Net effect: usage events emitted by runner/worker processes are now aggregated into one cross-worker cost report. Validated without spend by `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py` (read-back aggregation), `test_mock_inference_temporal.py` (`--mock-inference` cross-process), and the direct-mode `test_direct_tracing_assembly.py` / `test_cost_report_rendering.py`.

### Issue T3 — `set_event_log` is on a process-singleton `ReportingManager`

**Status**: Partially mitigated by P0. The runner-side fallback now bypasses `_event_log_contexts` entirely when the lookup misses, so the singleton-+-context-dict pattern no longer blocks standalone activity workers. The deeper "request-scoped tracing data instead of process-scoped state" refactor remains open and is the natural follow-up alongside P1.

**Severity**: Design smell that magnifies T1.

`ReportingManager` is a process-singleton accessed via `hub.get_report_delegate()`. The per-context `_event_log_contexts` dict + `lookup_key` scheme now serves only workflow-thread and direct-mode emissions: activity-side emissions always take the per-process fallback, whether the activity is co-located or remote (the H1 determinism fix made co-location irrelevant to the emit path). The deeper shape issue stands — request-scoped tracing data (e.g., `JobMetadata` / `TracingContext`) would be a better home than a process-local dict.

---

## How this connects to the plan

- T1 was the **top priority** in the [distributed-execution plan](README.md) — resolved.
- T2 is **resolved** — usage rides on `PipeOutput` (assembled from the same event read as the graph spec) and the submitter renders one cross-worker report. The wiring chosen was *not* `read events → inject_tokens_usages → generate_report` but the leaner Option B: `read events → UsageAggregator → PipeOutput.tokens_usages → CostRegistry.generate_report(tokens_usages=...)`, which let the submitter-side registry be deleted outright.
- T3 is the architectural shape; the T1 fix mitigated the immediate impact and T2's removal of the submitter-side registry shrank the singleton's surface further. The deeper "request-scoped tracing state instead of process-singleton" refactor remains the open follow-up (see Deferred / [the registry tracker](../registry/README.md)).

---

## Deferred items

Items related to the event log and graph tracing system that are explicitly out of scope for now.

### Event log backends

| Item | Status | Context |
|---|---|---|
| DynamoDB backend | **Shipped** | `pipelex/tracing/dynamodb_event_log.py` (+ `TEMPORAL_DYNAMODB` variant). Schema-compatible with `pipelex-api-infra`'s `TraceEventDynamoDBAdapter`. Selected via `[pipelex.tracing] backend = "dynamodb"`. |
| SQLite backend | **Not planned** — NDJSON + DynamoDB cover the matrix | Not built. Re-evaluate only if a use case appears that NDJSON can't serve and DynamoDB is overkill. |

### Event log protocol extensions

| Item | Status | Context |
|---|---|---|
| `subscribe()` on EventLogProtocol | **Deferred** — no consumer exists yet | Polling-based reads are sufficient for now; add when a real-time consumer exists. |
| Real-time progress consumer | **Deferred** — no consumer exists yet | The protocol supports it; build when needed. |
| TraceSinkProtocol abstraction | **Deferred** — EventLogProtocol is sufficient | The higher-level sink abstraction can wait for the cloud backend. |
| Large data externalization | **Deferred** — inline data is sufficient for now | Add StorageProvider offloading when traces grow too large. |

### Tracing architecture

| Item | Status | Context |
|---|---|---|
| Unified code path (event log everywhere) | **Effectively unified** | `pipeline_run_setup.py:282` wires `set_event_log()` on the report delegate for direct mode too (using `workflow_id="direct"`). The same `EventLogProtocol` machinery runs in both modes; only the in-process vs. Temporal lifecycle differs. |
| Auto-cleanup of traces | **Deferred** — manual cleanup is safer for now | NDJSON traces persist on disk until manually deleted. Safer for debugging and allows usage reporting to run after graph generation. DynamoDB cleanup follows TTL on the table. |

### Known issues

| Item | Status | Context |
|---|---|---|
| Causal event ordering in assembler | **Known limitation** — works for current topologies | `read_events()` sorts by `(workflow_id, sequence)` which groups by lexicographic workflow ID, not execution order. In parent/child workflow topologies, this can cause `_stuff_producer_map` overwrites in the wrong order during `GraphSpecAssembler.pass_one()`, producing incorrect DATA edge sources. Consider sorting by timestamp or processing events in a topology-aware order. |
| PipeCondition SELECTED_OUTCOME wiring | **Deferred** — no production use yet | PipeCondition has no tracer calls in production code currently. If SELECTED_OUTCOME edges are needed, that's a separate change. |
