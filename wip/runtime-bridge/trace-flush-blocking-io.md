# `flush_trace_events_to_backend` — async with blocking I/O

**Status:** ✅ **RESOLVED — false positive / by-design.** No code change. The `asyncio.to_thread` offload below is kept on file for if/when Temporal ships and we profile activity-worker contention.
**Source:** PR #959 review — cubic-dev-ai (P2, `pipelex/runtime_bridge/primitives/trace_flush.py:14`).

## The finding

> `async def` with `# noqa: RUF029` but contains synchronous blocking I/O — the emit loop calls `DynamoDBEventLog.emit()` (boto3 `put_item` — synchronous HTTP call) and `NdjsonEventLog.emit()` (synchronous file write+flush) without yielding the event loop. Because the caller `act_flush_trace_events` is an `async def` Temporal activity that awaits this coroutine, the blocking I/O holds Temporal's async activity worker event loop for the aggregate duration of all `emit()` calls.

## Why this is acceptable (the activity vs workflow distinction)

The facts are correct, but the conclusion ("holds the event loop") is the *intended and correct* place for blocking I/O in a Temporal app.

- The function is **designed to run in an activity**, never a workflow. Its module docstring (`trace_flush.py:1-6`) says so: *"Called from a host-runtime activity (Temporal / Mistral) after a workflow's `BufferingEventLog` has drained, since synchronous I/O (boto3, file writes) cannot run inside a workflow thread."*
- The emit loop is synchronous on purpose (`trace_flush.py:26-32`): `make_event_log(...)` then `for event in events: event_log.emit(event)`. The `# noqa: RUF029` (`trace_flush.py:14`) documents the deliberate async-with-no-await.
- Workflows must stay deterministic and I/O-free, so they buffer in memory via `BufferingEventLog` and hand the drained events to this activity:
  - `pipelex/temporal/tprl_pipe/wf_pipe_router.py:152-167` — drains `event_log` and `await workflow.execute_activity(act_flush_trace_events, ... start_to_close_timeout=30s, retry_policy=max 3)`.
- The activity is a thin wrapper: `pipelex/temporal/tprl_pipe/act_flush_trace_events.py:22-25` — `@activity.defn(name="act_flush_trace_events")` / `async def act_flush_trace_events(arg)` → `await flush_trace_events_to_backend(arg.events)`.
- `DynamoDBEventLog.emit` even warns against being called from a workflow (its docstring says the synchronous boto3 HTTP call would block the workflow thread and trip the deadlock detector) and points callers to exactly this `BufferingEventLog` + `act_flush_trace_events` pattern.

Activities are the part of Temporal that is *allowed* to block — that's their whole purpose. So this is the textbook pattern, not a bug.

## The kernel of truth (only if throughput ever matters)

Temporal's **async** activities share the worker's event loop. A blocking call inside one async activity does stall *sibling* async activities on the same worker for its duration. Temporal's own guidance: an async activity doing blocking I/O should either be registered as a **sync** activity (runs in a thread-pool executor) or offload the blocking part via `asyncio.to_thread` / `run_in_executor`.

For trace flushing this is negligible today: best-effort, bounded (30s `start_to_close_timeout`, ≤3 retries), batched per workflow, low volume, and Temporal isn't in prod. So **no change now.**

If/when activity throughput becomes a real concern, the minimal mitigation is:

```python
# trace_flush.py — offload the blocking emit loop off the event loop
import asyncio

async def flush_trace_events_to_backend(events: list[TraceEvent]) -> None:
    ...
    def _emit_all() -> None:
        try:
            for event in events:
                event_log.emit(event)
        finally:
            event_log.close()
    await asyncio.to_thread(_emit_all)
```

(That also lets the `# noqa: RUF029` go away, since the function would then genuinely await.)

## Recommendation

Reply on the thread as a **false positive / by-design**, citing the activity-vs-workflow distinction, and resolve it. Keep the `asyncio.to_thread` mitigation above on file here for if/when Temporal goes to prod and we profile activity-worker contention.

## Related

- The other two PR #959 forks are real bugs: `direct-mode-nested-router-leak.md` (#1), `graph-context-temporal-contract.md` (#3). This one is the only "false positive" of the three.
