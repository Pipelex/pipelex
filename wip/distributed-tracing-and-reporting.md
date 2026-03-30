# Distributed Tracing & Reporting Architecture

> **Status**: Pre-planning analysis — decision gates marked with ❓
> **Date**: 2026-03-29
> **Related**: [00-master-plan.md](00-master-plan.md), [phase2-crate-propagation-rationale.md](phase2-crate-propagation-rationale.md)
> **Scope**: GraphTracer (execution graph capture) + ReportingManager (AI usage/cost tracking) in Temporal distributed execution

---

## Problem Statement

Two in-memory systems silently break under Temporal distributed execution:

| System | What it does | How it breaks |
|--------|-------------|---------------|
| **GraphTracerManager** | Accumulates pipe execution events (nodes, edges, timing, I/O) into a GraphSpec for visualization | Singleton on each process — workers trace nothing because no tracer is opened; all graph events are lost |
| **ReportingManager** | Tracks AI token usage/costs per pipeline run | Workers auto-create orphaned registries that never sync back to the API process; usage data is lost |

Both systems were designed for single-process execution. The master plan (Phases 0-4) focused on library propagation and class registry scoping, but overlooked these two cross-cutting concerns.

### Requirements

| Requirement | Priority | Rationale |
|-------------|----------|-----------|
| **Survive failures** | Must-have | Cost reporting for failing workflows is not optional — we pay for those tokens |
| **Real-time progress** | Must-have | Track graph construction and cost accumulation while pipeline runs |
| **Per-step granularity** | Must-have | Each pipe execution is a distinct trace event with its own cost attribution |
| **Large graphs with data** | Must-have | Full I/O data capture (`--graph-full-data`) for debugging |
| **Local dev first** | Priority | But only if architecturally aligned with cloud — shared principles, swappable backend |

---

## Current Architecture Analysis

### GraphTracer: What Happens Today on Temporal

```
API Process                              Worker Process A                    Worker Process B
-----------                              ----------------                    ----------------
runner.execute_pipeline()
  pipeline_run_setup()
    GraphTracerManager.open_tracer()     (singleton is separate instance)    (singleton is separate instance)
    → GraphContext on JobMetadata
                                         WfPipeRouter.run(pipe_job)
                                           pipe.run_pipe()
                                             graph_context is NOT None ✓
                                             GraphTracerManager.get_instance()
                                             → returns None ✗                 (same: returns None)
                                             → tracing silently skipped       → tracing silently skipped
                                           return PipeOutput (no graph_spec)
  tracer_manager.close_tracer()
  → GraphSpec with ZERO nodes
```

**Root cause**: `GraphTracerManager` is a process-local singleton (`ABCSingletonMeta`). The API process opens a tracer, but `run_pipe()` executes on a different process where the singleton was never initialized. The guard `if tracer_manager is not None` silently skips all tracing.

**What's preserved**: `GraphContext` (graph_id, parent_node_id, node_sequence, data_inclusion) IS serialized on `JobMetadata` and correctly flows through PipeJob to workers. The context propagation infrastructure exists — only the tracer endpoint is missing.

### ReportingManager: What Happens Today on Temporal

```
API Process                              Worker Process
-----------                              ----------------
hub.set_report_delegate(reporting_mgr)
  reporting_mgr.open_registry(run_id)
                                         WfPipeRouter.run(pipe_job)
                                           pipe_operator.run_pipe()
                                             llm_worker.run()
                                               reporting_delegate.report_inference_job()
                                               → _get_registry(run_id) auto-creates orphan ✗
                                               → usage recorded in worker-local registry
                                           return PipeOutput
  reporting_mgr.generate_report(run_id)
  → report from API-side registry only
  → worker-side usage is LOST
```

**Root cause**: Workers get a `reporting_delegate` via `hub.get_report_delegate()`, which is a process-local reference. The `_get_registry()` method auto-creates registries for unknown pipeline IDs (there's already a TODO comment acknowledging this), but these registries live in the worker's memory and are never collected.

### What's Already in Place

| Infrastructure | Status | Relevance |
|---------------|--------|-----------|
| `GraphContext` serializable on `JobMetadata` | ✅ Working | Context flows to workers — can seed local tracers |
| `PipeOutput.graph_spec: GraphSpec | None` | ✅ Exists | Return channel exists but insufficient (only on success) |
| `GraphSpec` is a flat Pydantic model | ✅ Working | Easy to serialize, merge, transport |
| `TokensUsage` types are Pydantic models | ✅ Working | Easy to serialize and aggregate |
| `ObserverProtocol` + `LocalObserver` | ✅ Working | Existing event pattern — writes JSONL to shared dir |
| `StorageProviderAbstract` (Local, S3, GCP) | ✅ Working | Pluggable storage with existing backends |
| `LibraryCrate` propagation on PipeJob | ✅ Working | Pattern for adding data to PipeJob |
| StoragePayloadCodec (Phase 5) | 🔲 Planned | Would solve payload size limits |

### Why PipeOutput Piggyback Is Insufficient

The initial instinct is to return graph fragments and usage records in PipeOutput, like LibraryCrate propagation. This fails on three counts:

1. **Lost on failure**: If a workflow crashes, PipeOutput is never returned. Cost reporting for failing workflows is unacceptable to lose — those tokens were consumed and billed.
2. **No real-time visibility**: Data is only available when the entire workflow tree completes. For long pipelines, this means no progress tracking.
3. **Payload pressure**: Graph data with full I/O content can be large. Adding it to PipeOutput pushes toward Temporal's 2MB limit, making Phase 5 (StoragePayloadCodec) a hard prerequisite.

---

## Recommended Architecture: Event Log

The right abstraction is an **append-only event log**. Workers emit events as they happen. Events are durable the instant they're written. Consumers can read in real-time or after completion.

This matches the existing `LocalObserver` pattern (JSONL files in a shared directory) and generalizes cleanly to cloud backends (Redis Streams, CloudWatch, S3).

### Core Concept

```
                                    ┌──────────────┐
Worker A ──emit(PipeStartEvent)────►│              │
Worker A ──emit(UsageEvent)────────►│  Event Log   │◄────read()──── Real-time consumer
Worker B ──emit(PipeStartEvent)────►│  (per run)   │◄────read()──── Post-exec assembler
Worker B ──emit(PipeEndError)──────►│              │
                                    └──────────────┘
```

**Key properties**:
- **Fire-and-forget emit**: Workers write events and move on. No waiting for ack (local: file append; cloud: async publish).
- **Durable on write**: Events survive worker crashes because they're persisted before the worker continues.
- **Keyed by pipeline_run_id**: Each pipeline run has its own event stream.
- **Ordered per writer**: Events from a single worker are naturally ordered (sequential writes). Cross-worker ordering uses graph structure (parent_node_id), not timestamps.
- **Backend-agnostic**: The protocol is the same whether backed by SQLite, files, Redis, or S3.

### Event Types

```python
class TraceEventKind(StrEnum):
    PIPE_START = "pipe_start"
    PIPE_END_SUCCESS = "pipe_end_success"
    PIPE_END_ERROR = "pipe_end_error"
    USAGE_REPORT = "usage_report"

class TraceEvent(BaseModel):
    """Base event emitted by workers to the event log."""
    pipeline_run_id: str
    workflow_id: str             # Temporal workflow ID or "direct" for in-process
    event_kind: TraceEventKind
    timestamp: datetime          # UTC, for display only — not used for ordering
    sequence: int                # Per-writer monotonic counter for ordering

class PipeStartEvent(TraceEvent):
    event_kind: Literal[TraceEventKind.PIPE_START]
    node_id: str                 # Unique: {graph_id}:{workflow_short_id}:node_{seq}
    parent_node_id: str | None
    pipe_code: str
    pipe_type: str
    node_kind: NodeKind
    input_specs: list[IOSpec] | None = None

class PipeEndSuccessEvent(TraceEvent):
    event_kind: Literal[TraceEventKind.PIPE_END_SUCCESS]
    node_id: str
    output_spec: IOSpec | None = None
    timing: TimingSpec | None = None

class PipeEndErrorEvent(TraceEvent):
    event_kind: Literal[TraceEventKind.PIPE_END_ERROR]
    node_id: str
    error: ErrorSpec
    timing: TimingSpec | None = None

class UsageReportEvent(TraceEvent):
    event_kind: Literal[TraceEventKind.USAGE_REPORT]
    node_id: str | None = None   # Which pipe generated this cost
    tokens_usage: TokensUsage    # LLMTokensUsage | ImgGenTokensUsage | etc.
```

### Event Log Protocol

```python
class EventLogProtocol(Protocol):
    """Append-only event log for pipeline execution tracing."""

    def emit(self, event: TraceEvent) -> None:
        """Write an event to the log. Must be durable before returning.
        Non-blocking for the caller in the common case (local I/O is fast,
        cloud backends buffer and flush).
        """
        ...

    def read_events(self, pipeline_run_id: str) -> list[TraceEvent]:
        """Read all events for a pipeline run. Used by assemblers."""
        ...

    def subscribe(self, pipeline_run_id: str) -> AsyncIterator[TraceEvent]:
        """Stream events in real-time. Used by dashboards/progress trackers.
        Falls back to polling where native push isn't available.
        """
        ...

    def cleanup(self, pipeline_run_id: str) -> None:
        """Remove events for a completed pipeline run (optional, for storage hygiene)."""
        ...
```

### Backend Implementations

#### Local Dev: SQLite Event Log

SQLite is the ideal local backend because:
- Single file, zero setup, already available everywhere
- WAL mode supports concurrent readers + single writer (our workers write sequentially per pipeline)
- ACID guarantees — events are durable on commit
- Supports polling-based subscribe (query `WHERE sequence > last_seen`)
- Fast enough for local dev (microsecond writes)
- Easy to inspect with any SQLite tool

```sql
CREATE TABLE trace_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_run_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    event_kind TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    payload TEXT NOT NULL,         -- JSON serialized TraceEvent
    UNIQUE(pipeline_run_id, workflow_id, sequence)
);

CREATE INDEX idx_pipeline_run ON trace_events(pipeline_run_id);
CREATE INDEX idx_pipeline_run_id ON trace_events(pipeline_run_id, id);
```

**Concurrency model**: Multiple workers (separate processes) can write concurrently because SQLite WAL mode handles locking. Each worker gets its own connection. Writes are serialized at the SQLite level but with minimal contention (append-only, no conflicts).

**Real-time polling**: A consumer reads `SELECT * FROM trace_events WHERE pipeline_run_id = ? AND id > ? ORDER BY id` periodically (e.g., every 500ms). Simple, reliable, no complex pub/sub.

**File location**: `{pipelex_data_dir}/traces/{pipeline_run_id}.db` — one DB file per pipeline run, easy cleanup.

Alternative: single DB file with all runs, cleanup via DELETE. Simpler file management but slightly more contention.

#### Cloud: Redis Streams

Redis Streams is the natural cloud equivalent:
- `XADD pipelex:trace:{pipeline_run_id} * event_kind pipe_start payload {...}`
- `XREAD` for real-time streaming
- `XRANGE` for batch reads
- TTL for automatic cleanup
- Already used in many Temporal deployments

#### Cloud: S3/GCS (cold path)

For archival and large data (full I/O content):
- Workers write event batches to `s3://traces/{pipeline_run_id}/{workflow_id}/{sequence}.json`
- No real-time streaming, but durable and cheap
- Can be combined with Redis (hot events to Redis, data payloads to S3)

### Comparison: SQLite vs JSONL Files vs Redis

| Criterion | SQLite | JSONL files | Redis Streams |
|-----------|:------:|:-----------:|:-------------:|
| Concurrent writes | ✅ WAL mode | ⚠️ File locking needed | ✅ Native |
| Real-time reads | ✅ Poll query | ⚠️ Tail + parse | ✅ XREAD blocking |
| Atomic writes | ✅ Transaction | ❌ Partial writes possible | ✅ XADD atomic |
| Query by run_id | ✅ Index | ❌ Scan all files | ✅ Stream key |
| Inspect/debug | ✅ sqlite3 CLI | ✅ cat/jq | ⚠️ redis-cli |
| Setup | ✅ Zero (stdlib) | ✅ Zero | ❌ External service |
| Cloud-ready | ❌ Local only | ❌ Local only | ✅ Managed Redis |
| Survives worker crash | ✅ On commit | ✅ On flush | ✅ On ACK |

**Recommendation**: SQLite for local dev, Redis Streams for cloud. Both implement the same `EventLogProtocol`. JSONL files (like LocalObserver) are tempting but lack atomic concurrent writes — a real risk with parallel pipe execution.

---

## Integration Points

### Where Events Are Emitted

The event log replaces (or wraps) the existing tracer calls. The emission points already exist in the code:

| Current call site | File | Becomes |
|-------------------|------|---------|
| `tracer_manager.on_pipe_start(...)` | `pipe_abstract.py:416` | `event_log.emit(PipeStartEvent(...))` |
| `tracer_manager.on_pipe_end_success(...)` | `pipe_abstract.py:487` | `event_log.emit(PipeEndSuccessEvent(...))` |
| `tracer_manager.on_pipe_end_error(...)` | `pipe_abstract.py:460` | `event_log.emit(PipeEndErrorEvent(...))` |
| `reporting_delegate.report_inference_job(...)` | `llm_worker_abstract.py:334` | `event_log.emit(UsageReportEvent(...))` |

### How Workers Access the Event Log

Two options:

**(a) Via GraphContext on JobMetadata**: Add an `event_log_uri` field to GraphContext. Workers create a client from the URI. This is explicit and serializable.

```python
class GraphContext(BaseModel):
    graph_id: str
    parent_node_id: str | None
    node_sequence: int
    data_inclusion: DataInclusionConfig
    event_log_uri: str | None = None   # "sqlite:///tmp/traces/run123.db" or "redis://..."
```

**(b) Via hub configuration**: Workers read the event log backend from `pipelex.toml` config. The pipeline_run_id is on JobMetadata. This is simpler but less explicit.

**Recommendation**: (b) for simplicity — the backend is infrastructure config, not per-run config. The `pipeline_run_id` (already on JobMetadata) is the key.

### How the Assembler Works

After pipeline execution (or on-demand for real-time), the assembler reads all events and reconstructs:

```python
class GraphSpecAssembler:
    """Reconstructs a GraphSpec from trace events."""

    @staticmethod
    def assemble(events: list[TraceEvent]) -> GraphSpec:
        nodes: dict[str, NodeSpec] = {}
        edges: list[EdgeSpec] = []
        stuff_producer_map: dict[str, str] = {}   # digest → node_id

        for event in events:
            match event.event_kind:
                case TraceEventKind.PIPE_START:
                    # Create node, record inputs, create CONTAINS edge if parent
                    ...
                case TraceEventKind.PIPE_END_SUCCESS:
                    # Update node status, record output, register in producer map
                    ...
                case TraceEventKind.PIPE_END_ERROR:
                    # Update node status, record error
                    ...
                case TraceEventKind.USAGE_REPORT:
                    # Accumulate in usage registry (separate from graph)
                    ...

        # Generate DATA edges from producer/consumer digest correlation
        _generate_data_edges(nodes, stuff_producer_map, edges)

        return GraphSpec(
            graph_id=events[0].pipeline_run_id,
            created_at=min(e.timestamp for e in events),
            nodes=list(nodes.values()),
            edges=edges,
        )
```

**Key insight**: The assembler runs the same edge correlation logic that `GraphTracer.teardown()` currently runs. The difference is that it works on events from multiple workers, not in-memory state from one process. The algorithm is identical — correlate input digests with the producer map.

### What Changes in Direct Mode?

Nothing, if we do it right. Two strategies:

**(a) Dual-write**: In direct mode, the existing in-memory GraphTracerManager continues to work as-is. The event log is only used in Temporal mode. Simple but maintains two code paths.

**(b) Event log everywhere**: Replace the in-memory tracer with the event log even in direct mode. Use an in-memory event log backend (list of events). Assembler runs at the end. One code path for both modes.

**Recommendation**: **(b)** — one code path is always better. The in-memory backend has zero overhead compared to the current approach. This also means every integration test exercises the event log + assembler path.

### Controller-Specific Edges

PipeParallel, PipeBatch, and PipeCondition register special edges (PARALLEL_COMBINE, BATCH_ITEM, BATCH_AGGREGATE, SELECTED_OUTCOME). These require dedicated event types:

```python
class BatchItemEvent(TraceEvent):
    """Emitted when PipeBatch extracts an item from a list."""
    event_kind: Literal["batch_item"]
    source_node_id: str          # The node that produced the list
    target_node_id: str          # The batch iteration node
    source_stuff_digest: str
    target_stuff_digest: str

class ParallelCombineEvent(TraceEvent):
    """Emitted when PipeParallel combines branch outputs."""
    event_kind: Literal["parallel_combine"]
    branch_stuff_digests: list[str]
    combined_stuff_digest: str
    controller_node_id: str

class SelectedOutcomeEvent(TraceEvent):
    """Emitted when PipeCondition selects an outcome."""
    event_kind: Literal["selected_outcome"]
    source_node_id: str
    target_node_id: str
```

These are currently emitted via direct calls to `GraphTracerManager` methods like `register_parallel_combine()`, `register_batch_item_extraction()`, etc. They become event emissions.

### Node ID Scheme

Current: `{graph_id}:node_{sequence}` — collides across workers.

**New scheme**: `{graph_id}:{workflow_short_id}:node_{sequence}`

Where `workflow_short_id` is a short hash of the Temporal workflow ID (or `"direct"` for in-process). This guarantees uniqueness while remaining human-readable.

The `node_sequence` counter lives on the `GraphContext` that flows through execution. When a pipe starts, it gets the next sequence number from its context. Since contexts are copied for children (not shared), there's no cross-worker contention.

**Important**: In the current code, `node_sequence` is on the `GraphTracer` (in-memory), not on `GraphContext`. For the event log approach, we move the sequence counter to `GraphContext` so it flows with the execution. This is a behavioral change but aligns with the serializable context philosophy.

---

## Data Flow: Complete Picture

```
API Process (Submitter)                   Worker Process (any of N)
-----------------------                   -------------------------
1. pipeline_run_setup()
   - Create event log (SQLite file or Redis stream)
   - Create GraphContext with event_log config
   - Attach GraphContext to JobMetadata

2. Submit PipeJob to Temporal
   ──────────────────────────────────────►
                                          3. WfPipeRouter.run(pipe_job)
                                             pipe.run_pipe()
                                               ├── EMIT PipeStartEvent ──────► Event Log
                                               ├── (execute pipe logic)
                                               │   ├── llm_worker reports:
                                               │   │   EMIT UsageReportEvent ► Event Log
                                               │   ├── child workflow dispatched:
                                               │   │   (child worker does same)
                                               │   └── ...
                                               ├── EMIT PipeEndSuccessEvent ─► Event Log
                                               │   (or PipeEndErrorEvent)
                                               └── return PipeOutput

   ◄──────────────────────────────────────
4. Receive PipeOutput (contains working_memory only — no graph/usage)

5. Assemble: read all events from event log
   → GraphSpecAssembler.assemble() → GraphSpec
   → UsageAggregator.aggregate() → CostReport
   → Generate graph outputs (Mermaid, ReactFlow)

6. Cleanup event log (optional)
```

**On failure**: Steps 3 may fail partway. But every event emitted before the failure is already in the event log. The assembler in step 5 sees partial data (some PIPE_START without matching PIPE_END) and marks those nodes as RUNNING or CANCELED. Usage events for completed inference jobs are captured regardless.

**Real-time**: A separate consumer can poll the event log during step 3, showing live progress. For local dev, this could be a CLI progress bar or a simple web dashboard reading the SQLite file.

---

## Two Distinct Problems, Unified Solution

Graph tracing and reporting have different characteristics but share the same event log:

| Dimension | Graph Tracing | Usage Reporting |
|-----------|--------------|-----------------|
| Events | PipeStart, PipeEnd*, controller edges | UsageReport |
| Assembly | Complex — tree reconstruction, edge correlation | Simple — list concatenation, sum |
| Data volume | Potentially large (full I/O data) | Small (few KB per job) |
| Failure handling | Partial graph with RUNNING/CANCELED nodes | All completed jobs captured |
| Real-time use | Progress tree visualization | Running cost counter |
| Consumer | GraphSpecAssembler → renderers | UsageAggregator → CostReport |

Both read from the same event log. The assembler and aggregator are separate consumers — they can run independently, at different times, or concurrently.

---

## Large Data Strategy

With `--graph-full-data`, IOSpec includes full serialized content (JSON, text, HTML). A single PipeEndSuccessEvent could be megabytes.

### ❓ Decision 1: How to handle large IOSpec data in events?

**(a) Inline in events**: Full data embedded in the event payload. Simple but makes events large.
- SQLite handles large BLOBs fine (tested to GB scale)
- Redis has a 512MB value limit (more than enough)
- Makes the event log self-contained — no external references

**(b) Reference + external storage**: Events contain previews and digests only. Full data written to StorageProvider (existing system) keyed by digest. Assembler fetches when needed.
- Keeps events small and fast
- Leverages existing StorageProvider (Local, S3, GCP)
- Adds complexity: two storage systems to coordinate

**(c) Tiered**: Events contain data up to a size threshold (e.g., 100KB). Larger data goes to external storage with a reference in the event.
- Best of both worlds
- More complex to implement

**Recommendation**: Start with **(a)** — inline. SQLite handles it well for local dev. For cloud, (b) becomes important, but that's a later optimization. The event schema supports both — `IOSpec.data` can be `None` with a `digest` that references external storage.

---

## Decision Gates

### ❓ Decision 2: Event Log Backend for Local Dev

**(a) SQLite** — Structured, concurrent-safe, queryable, inspectable. Slightly more setup (schema migration).

**(b) JSONL files** — Follows existing LocalObserver pattern. Simpler but lacks atomic concurrent writes and efficient querying.

**(c) In-memory only** — No persistence. Lost on process crash. Not useful for real-time cross-process reads.

**Recommendation**: (a) SQLite. The concurrency guarantees matter for parallel pipe execution. The inspectability (sqlite3 CLI) is valuable for debugging.

### ❓ Decision 3: Direct Mode Integration

**(a) Keep existing in-memory tracer** for direct mode, event log only for Temporal. Two code paths.

**(b) Event log everywhere** — in-memory backend for direct mode, SQLite for Temporal. One code path.

**Recommendation**: (b) — one code path. Use an in-memory list as the "event log" in direct mode. Same assembler, same event types, zero overhead. Every test exercises the full path.

### ❓ Decision 4: Node ID Scheme

Current: `{graph_id}:node_{sequence}` (conflicts across workers).

**(a)** `{graph_id}:{workflow_short_id}:node_{seq}` — deterministic, debuggable, workflow-scoped prefix
**(b)** UUID-based — simple, no coordination needed
**(c)** Keep sequential with moved counter on GraphContext

**Recommendation**: (a). The workflow ID provides natural namespacing. Short hash (8 chars) keeps IDs readable.

### ❓ Decision 5: Sequence Counter Location

Currently `node_sequence` lives on GraphTracer (in-memory). For event log, it must travel with execution.

**(a) Move to GraphContext** — already serializable, flows through PipeJob. Each child context gets a copy.

**(b) Worker-local counter** — each worker starts at 0. Combined with workflow_id prefix, globally unique.

**Recommendation**: (b) — simpler. The workflow_id prefix already guarantees uniqueness. No need to coordinate sequence numbers across workers.

### ❓ Decision 6: How Do Workers Access the Event Log?

**(a) Via hub config** — workers read the backend config from `pipelex.toml`. The `pipeline_run_id` from JobMetadata is the key. Workers create a client on first use.

**(b) Via GraphContext field** — add `event_log_uri: str | None` to GraphContext. More explicit but adds a field to a serialized model.

**(c) Via PipeJob field** — add `event_log_config` to PipeJob, like `library_crate`.

**Recommendation**: (a) — config-driven, like storage providers. The event log backend is infrastructure, not per-run data. Workers need the `pipeline_run_id` (already available) and the backend config (from pipelex.toml).

---

## Pitfalls & Warnings

### From a Senior Python Engineer

1. **Don't force async on emit()**: The emit call happens inside `pipe_abstract.run_pipe()`, which is already async. But making emit truly async (with await) means it becomes a Temporal replay point in workflows. For Temporal determinism, side effects must happen inside activities. **Solution**: Make emit synchronous (SQLite writes are microseconds). For cloud backends that require network I/O, buffer events in-memory and flush via a Temporal activity or background thread.

2. **Temporal replay and side effects**: If `run_pipe()` replays on a worker restart, events will be re-emitted. The event log must handle duplicates gracefully. **Solution**: Use `(pipeline_run_id, workflow_id, sequence)` as a unique key. SQLite `INSERT OR IGNORE` / Redis conditional adds handle deduplication naturally.

3. **GraphTracer refactoring scope**: The current GraphTracer does two things: (1) accumulate events, (2) generate edges during teardown. With the event log, accumulation moves to the log. Edge generation moves to the assembler. The GraphTracer becomes a thin emit wrapper — or disappears entirely, replaced by direct event emission in `pipe_abstract.py`. Consider whether to keep the GraphTracer as a facade or remove it.

4. **ContextVar for event log client**: Similar to `_library_id`, the event log client reference should be ContextVar-scoped so each workflow/context gets the right client. For direct mode, set at `pipeline_run_setup()`. For Temporal, set at the top of `WfPipeRouter.run()`.

5. **Testing strategy**: The in-memory backend (Decision 3b) makes unit testing trivial — emit events, call assembler, assert on GraphSpec. Integration tests with SQLite validate concurrency. The cloud backend is tested separately.

### From a Senior Systems Engineer

1. **SQLite WAL + multiple processes**: SQLite WAL mode supports one writer at a time. With many workers writing concurrently, there will be brief lock contention. For local dev with a handful of workers, this is negligible. For production with dozens of workers, SQLite won't scale — that's when Redis takes over. This is fine for the layered approach.

2. **File locking on NFS/shared filesystems**: If workers run on different machines sharing an NFS mount, SQLite will NOT work correctly — NFS doesn't support the locking primitives SQLite needs. This is a known limitation. For cloud, don't use SQLite — use Redis or S3.

3. **Event log cleanup**: Without cleanup, SQLite files accumulate. Add a configurable retention policy (e.g., delete after 24h or after report generation). For cloud backends, use TTL.

4. **Temporal's own event history**: Temporal already stores a complete event history for every workflow. In theory, you could extract tracing data from Temporal's event history (workflow started, activity completed, child workflow results, etc.). In practice, this gives you workflow-level granularity, not pipe-level granularity, and requires querying Temporal's API. It's not a substitute for the event log, but it's useful for correlation and debugging.

5. **Clock skew**: Events from different workers may have slightly different timestamps. Use the event log's insertion order (autoincrement ID in SQLite, stream ID in Redis) for ordering, not timestamps. Timestamps are for display only.

6. **Backpressure**: If a pipeline generates thousands of events (e.g., batch of 1000 items), the event log must handle the throughput. SQLite WAL mode can handle ~10K writes/sec. Redis Streams can handle ~100K ops/sec. Both are well above expected throughput.

---

## Implementation Plan

### Step 1: Event Types & Protocol

Define the event models and `EventLogProtocol`. Pure model work, no integration yet.

**Key files**:
| File | Change |
|------|--------|
| `pipelex/tracing/trace_events.py` | **New** — TraceEvent models |
| `pipelex/tracing/event_log_protocol.py` | **New** — EventLogProtocol |
| `pipelex/tracing/in_memory_event_log.py` | **New** — In-memory implementation |

**Done when**:
- Event models serialize/deserialize correctly (unit tests)
- In-memory event log passes basic emit/read/subscribe tests

### Step 2: GraphSpec Assembler

Build the assembler that reconstructs GraphSpec from events. This is the core algorithm.

**Key files**:
| File | Change |
|------|--------|
| `pipelex/tracing/graphspec_assembler.py` | **New** — Event → GraphSpec reconstruction |
| `pipelex/tracing/usage_aggregator.py` | **New** — Event → usage report aggregation |

**Done when**:
- Assembler produces correct GraphSpec from hand-crafted events (unit tests)
- Assembler handles partial events (missing PIPE_END → node marked RUNNING)
- Usage aggregator sums correctly across workers
- Edge correlation (DATA edges from digest matching) works across workers

### Step 3: SQLite Event Log

Implement the SQLite backend for local dev.

**Key files**:
| File | Change |
|------|--------|
| `pipelex/tracing/sqlite_event_log.py` | **New** — SQLite implementation |
| `pipelex/tracing/tracing_config.py` | **New** — Config model for tracing backend |
| `pipelex/pipelex.toml` | Add `[pipelex.tracing]` config section |

**Done when**:
- Concurrent writes from multiple threads/processes work (integration test)
- Real-time polling reads see events from other writers
- Deduplication handles replayed events

### Step 4: Wire into Pipe Execution

Replace GraphTracerManager calls in `pipe_abstract.py` with event log emissions. Replace ReportingManager calls in inference workers.

**Key files**:
| File | Change |
|------|--------|
| `pipelex/core/pipes/pipe_abstract.py` | Replace tracer calls with event emission |
| `pipelex/cogt/inference/inference_worker_abstract.py` | Emit UsageReportEvent |
| `pipelex/pipe_controllers/parallel/pipe_parallel.py` | Emit ParallelCombineEvent |
| `pipelex/pipe_controllers/batch/pipe_batch.py` | Emit BatchItemEvent, BatchAggregateEvent |
| `pipelex/pipe_controllers/condition/pipe_condition.py` | Emit SelectedOutcomeEvent |
| `pipelex/pipeline/runner.py` | Open event log, run assembler after execution |
| `pipelex/pipeline/pipeline_run_setup.py` | Initialize event log, set on ContextVar |
| `pipelex/temporal/tprl_pipe/wf_pipe_router.py` | Initialize event log client from config |

**Done when**:
- Direct mode: `pipelex run pipe --graph` produces identical GraphSpec as before
- Temporal mode: `pipelex run pipe --graph` produces correct GraphSpec across workers
- Usage reporting works in both modes
- All existing graph-related tests pass

### Step 5: Real-Time Consumer

Build a consumer that polls the event log and shows live progress.

**Key files**:
| File | Change |
|------|--------|
| `pipelex/tracing/live_progress.py` | **New** — Real-time progress from event log |

**Done when**:
- CLI shows live pipe execution progress during Temporal runs
- Cost accumulation displayed in real-time

### Future: Cloud Backends

| Backend | When | Why |
|---------|------|-----|
| Redis Streams | When deploying to cloud with remote workers | Concurrent writes, real-time streaming, TTL |
| S3/GCS | When archiving traces for compliance or analytics | Cheap, durable, queryable (Athena/BigQuery) |

These are new implementations of `EventLogProtocol`. No changes to emission or assembly code.

---

## Relationship to Master Plan

This is a **parallel track**, not a new phase:

```
Master Plan                          This Track
-----------                          ----------
Phase 4 (ClassRegistry) ← Complete
                                     Step 1: Event Types & Protocol
                                     Step 2: GraphSpec Assembler
Phase 5 (StoragePayloadCodec)        Step 3: SQLite Event Log
                                     Step 4: Wire into Pipe Execution
                                     Step 5: Real-Time Consumer
```

**No dependency on Phase 5**: Unlike the PipeOutput piggyback approach, the event log doesn't add to Temporal payloads. Large IOSpec data goes to the event log (SQLite/Redis), not through Temporal's wire.

**No dependency on other phases**: The event log is orthogonal to library crate propagation, deferred hydration, and ClassRegistry scoping.

---

## Open Questions

1. **GraphTracer's fate**: The event log approach may make `GraphTracerManager` and `GraphTracer` obsolete. Should we keep them as a compatibility layer (wrapping event emission), or remove them and emit directly from `pipe_abstract.py`? Keeping them as a facade reduces the diff but adds indirection.

2. **Controller-specific edge events**: PipeParallel's `register_parallel_combine()` currently mutates the tracer's internal `_stuff_producer_map` to override which node is the "producer" of a data item. With the event log, this becomes a `ParallelCombineEvent` that the assembler interprets. Need to verify this works for all controller types.

3. **Content generator activities**: `ContentGeneratorChild` wraps LLM/extract/imggen activities. These run as Temporal activities, not workflows. Do activities have access to the event log? If the hub config is available on the worker process (it should be — workers load pipelex config at startup), then activities can emit events directly. Need to verify.

4. **IOSpec data lifecycle**: If we inline large data in events (Decision 1a), the SQLite file for a single run could be very large. Should we add a configurable size threshold where data is stripped from events and written to the existing StorageProvider? This is Decision 1c but deferred.

5. **Backwards compatibility**: Existing graph output consumers (Mermaid renderer, ReactFlow generator) expect a GraphSpec. The assembler produces a GraphSpec. No change needed for consumers. But the `GraphSpec.to_json()` output should be identical for regression testing — verify field ordering, alias handling, etc.
