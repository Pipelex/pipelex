# Tracing & Cost Reporting — As Built

> **Status**: Shipped — the current tracing & cost-reporting implementation (supersedes an earlier distributed-tracing design, now retired).
> **Last updated**: 2026-05-04
> **Related**: [the distributed-execution plan](README.md).

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
- **Workflow → activity flush, not interceptor.** `WfPipeRouter.run()` (`pipelex/temporal/tprl_pipe/wf_pipe_router.py`) wires a `BufferingEventLog` into the per-workflow `GraphTracerManager` and into the `ReportingManager` via `set_event_log(context_key=workflow_id, ...)`. After pipe execution, buffered events are drained and persisted by `act_flush_trace_events` (`pipelex/temporal/tprl_pipe/act_flush_trace_events.py`), which runs the synchronous boto3 / file writes off the workflow thread.
- **Per-context keying** — `ReportingManager` holds a dict of `_event_log_contexts` keyed by `graph_context.lookup_key`, so concurrent workflows don't trample each other.
- **Direct mode unchanged** — `pipeline_run_setup.py:282` calls the same `set_event_log` path, so the same `EventLogProtocol` machinery runs in-process for non-Temporal execution.
- **Graph assembly across workers** — `pipelex/pipe_run/graph_assembly.py` (`assemble_graph_on_output`) and `pipelex/temporal/tprl_pipe/act_assemble_graph.py` read all events for a `pipeline_run_id` from the configured backend and feed them into `GraphSpecAssembler` to build the cross-worker `GraphSpec`.

## What works today

| Scenario | Captured? | How |
|---|---|---|
| Direct mode (single process) | ✅ | `pipeline_run_setup` configures event log on `ReportingManager`; events emitted in-process. |
| Single-worker Temporal (workflows + activities on same Worker bundle) | ✅ | Activities share the workflow's process; usage events emit through the singleton `ReportingManager` whose `set_event_log` was configured by `WfPipeRouter`. |
| Parent + child workflows on different worker processes | ✅ | Each workflow's process buffers its own events and flushes its own slice. All slices land in the same NDJSON dir / DynamoDB partition keyed by `pipeline_run_id`. |
| Cross-worker **graph** assembly | ✅ | `assemble_graph_on_output` / `act_assemble_graph` reads all events for the `pipeline_run_id` and runs `GraphSpecAssembler`. |

## What is broken or missing

### Issue T1 — Activities on standalone (separate-process) workers lose usage events — **FIXED (P0)**

**Severity (was)**: Blocked the whole point of distributed activity workers.

**Status**: Resolved (P0 in [the distributed-execution plan](README.md)).

The fix has two independent parts that ship together:

- **Runner-side fallback in `_emit_usage_event`.** When the activity's `ReportingManager` has no entry in `_event_log_contexts` for the workflow's `lookup_key`, it now falls back to a process-local event log built from `tracing_config`. The event log is cached per process via `pipelex.tracing.activity_event_log.get_or_create_activity_event_log` (guarded by a module-level `threading.Lock` so concurrent first-emitters from multiple activity threads agree on a single writer_id and instance). The fallback uses `graph_context.tracer_key or graph_context.graph_id` as `workflow_id` (no new `JobMetadata` field needed — `tracer_key` is already populated by `WfPipeRouter.run`). Specific exceptions (`OSError`, `MissingDependencyError`, `PipelexConfigError`, `botocore.ClientError`) are caught at WARNING — never silently dropped, never `except Exception`. A one-shot warning per process records that the fallback engaged.
- **Writer-id disambiguation in `TraceEvent`.** A new `writer_id: str = "primary"` field makes `(workflow_id, sequence)` collisions impossible across writers. NDJSON file naming becomes `wf_{workflow_id}__w_{writer_id}.ndjson` for non-primary writers; the `(pipeline_run_id, workflow_id, writer_id)` cache key prevents two writers from sharing a stale file handle. Read-side dedup key is `(workflow_id, writer_id, type, sequence)`; sort key is `(workflow_id, sequence, writer_id)` — sequence primary so a runner-side `UsageReportEvent` does not sort before earlier router events. DynamoDB SK becomes `EVENT#{workflow_id}#{writer_id}#{sequence:010d}`.

The `_get_registry` orphan-accumulation TODO at `reporting_manager.py` is gone: the method was split into `_get_registry_strict` (used by `_report_*_job` — runner processes silently skip the registry add) and `_get_or_create_registry` (used by `inject_tokens_usages`, the console cost-report path, and `generate_report`).

The known retry-related over-counting case (R2) is documented and pinned by `test_retried_activity_emits_duplicate_usage_event_documenting_r2`. A `tracing_config.strict_mode` flag (raise instead of WARNING + drop) is deferred — see [the plan, §P0.2](README.md).

### Issue T2 — Cross-worker cost report assembly is not wired

**Status**: Still open. P0 (T1 above) ensures the events now land in the same backend partition from every worker; P1 is the remaining plumbing change to read them back into a cost report.

**Severity**: High — events are persisted but never turned into a report.

The pieces all exist:

- `UsageAggregator.aggregate(events) → list[AnyTokensUsage]` (`pipelex/tracing/usage_aggregator.py`).
- `ReportingManager.inject_tokens_usages(pipeline_run_id, tokens_usages)` whose docstring literally says: *"Used after assembling usage data from distributed trace events, so that generate_report() can produce a complete cost report across all workers."* (`reporting_manager.py:223`).
- `ReportingManager.generate_report(pipeline_run_id)` (`reporting_manager.py:365`).

But **the cross-worker assembly chain is not wired up**. The graph assembly path (`graph_assembly.py`, `act_assemble_graph.py`) reads events back, but only feeds them into `GraphSpecAssembler` — never into `UsageAggregator`. `generate_report()` does have a runtime caller (the CLI run path, `_run_core.py:224`), but it reports only the local, in-process usage registries; `UsageAggregator.aggregate()` and `inject_tokens_usages()` still have zero runtime callers, so the events emitted by runner/worker processes never get assembled into the cost report.

Net effect: even when usage events ARE captured (i.e., the same-worker case in the table above), the captured events sit in NDJSON / DynamoDB and never become a cross-worker cost report.

### Issue T3 — `set_event_log` is on a process-singleton `ReportingManager`

**Status**: Partially mitigated by P0. The runner-side fallback now bypasses `_event_log_contexts` entirely when the lookup misses, so the singleton-+-context-dict pattern no longer blocks standalone activity workers. The deeper "request-scoped tracing data instead of process-scoped state" refactor remains open and is the natural follow-up alongside P1.

**Severity**: Design smell that magnifies T1.

`ReportingManager` is a process-singleton accessed via `hub.get_report_delegate()`. The per-context `_event_log_contexts` dict + `lookup_key` scheme works because the workflow process is the same process that emits events from activities (today). The moment activity execution moves off-process, the singleton + context-dict pattern stops being the right shape — the activity needs to pull its event log from request-scoped data (e.g., `JobMetadata` / `TracingContext`), not from a process-local dict that was never populated on its process.

---

## How this connects to the plan

- T1 was the **top priority** in the [distributed-execution plan](README.md) — now resolved.
- T2 is the **next priority** — events now land in the same partition from every worker; the small remaining step is wiring `read events → UsageAggregator → inject_tokens_usages → generate_report`.
- T3 is the architectural shape; the T1 fix mitigates the immediate impact, the deeper refactor will land alongside T2 / further follow-ups.

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
