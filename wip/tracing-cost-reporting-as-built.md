# Tracing & Cost Reporting — As Built

> **Status**: Shipped via `feature/dynamodb-tracer` (supersedes the original Phase 4.5 Step 6 design from `archive/00-master-plan.md`).
> **Last updated**: 2026-05-04
> **Related**: [02-master-plan.md](02-master-plan.md), [distributed-tracing-and-reporting.md](distributed-tracing-and-reporting.md) (pre-implementation analysis — design choices superseded), [archive/phase4.5-distributed-tracing-implementation.md](archive/phase4.5-distributed-tracing-implementation.md).

This file documents what actually shipped, plus the known gaps that 02-master-plan addresses.

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

### Issue T1 — Activities on standalone (separate-process) workers lose usage events

**Severity**: Blocks the whole point of distributed activity workers.

`tasks.py` currently bundles workflows + activities into the same `TaskPack`, so this issue is latent. But the explicit design intent is to split activities onto standalone Worker pools (separate processes from the workflow Worker pool). When that split happens:

- The activity's process never runs `WfPipeRouter.run()`, so its `ReportingManager` has no entry in `_event_log_contexts` for the workflow's `lookup_key`.
- `ReportingManager._emit_usage_event` returns silently when the context lookup misses (`reporting_manager.py:211-213`).
- `ReportingManager._get_registry` auto-creates a worker-local `UsageRegistry` (with the explicit TODO at `reporting_manager.py:111-117`: *"Auto-create registry for unknown pipeline IDs. This happens when Activities report inference jobs on a Temporal worker where open_registry() was never called (it runs on the API process). TODO: replace with proper distributed reporting system"*).
- The worker-local registry is never read back by anyone — usage data is lost on the activity worker.

**Note**: The `BufferingEventLog` + `act_flush_trace_events` pattern is structurally tied to a workflow lifecycle; it cannot serve standalone activity workers as-is. A different mechanism is needed (the original interceptor design, or per-activity event log construction from tracing config + JobMetadata).

### Issue T2 — Cross-worker cost report assembly is not wired

**Severity**: High — events are persisted but never turned into a report.

The pieces all exist:

- `UsageAggregator.aggregate(events) → list[AnyTokensUsage]` (`pipelex/tracing/usage_aggregator.py`).
- `ReportingManager.inject_tokens_usages(pipeline_run_id, tokens_usages)` whose docstring literally says: *"Used after assembling usage data from distributed trace events, so that generate_report() can produce a complete cost report across all workers."* (`reporting_manager.py:191`).
- `ReportingManager.generate_report(pipeline_run_id)` (`reporting_manager.py:247`).

But **nothing in the runtime calls them**. The graph assembly path (`graph_assembly.py`, `act_assemble_graph.py`) reads events back, but only feeds them into `GraphSpecAssembler` — never into `UsageAggregator`. `generate_report()` has zero runtime callers; only integration tests invoke it.

Net effect: even when usage events ARE captured (i.e., the same-worker case in the table above), the captured events sit in NDJSON / DynamoDB and never become a cross-worker cost report.

### Issue T3 — `set_event_log` is on a process-singleton `ReportingManager`

**Severity**: Design smell that magnifies T1.

`ReportingManager` is a process-singleton accessed via `hub.get_report_delegate()`. The per-context `_event_log_contexts` dict + `lookup_key` scheme works because the workflow process is the same process that emits events from activities (today). The moment activity execution moves off-process, the singleton + context-dict pattern stops being the right shape — the activity needs to pull its event log from request-scoped data (e.g., `JobMetadata` / `TracingContext`), not from a process-local dict that was never populated on its process.

---

## How this connects to 02-master-plan

- T1 is the **top priority** in [02-master-plan.md](02-master-plan.md) — the whole point of distributed execution is to allow activities on standalone Worker pools.
- T2 is the **second priority** — once T1 is solved, the assembly wiring is the small remaining step that makes cost reporting actually report.
- T3 is the architectural shape that the T1 + T2 work will refactor.
