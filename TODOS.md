# Distributed Tracing & Reporting — Local Version

> Implementation plan for the NDJSON-file-based event log that enables graph tracing and cost reporting across Temporal workers.
> Design rationale and cloud architecture (DynamoDB) in [wip/distributed-tracing-and-reporting.md](wip/distributed-tracing-and-reporting.md).

---

## Overview

Add a **file-based event log** as an alternative to the existing in-memory `GraphTracerManager` and `ReportingManager`, for use when running with Temporal distributed workers. The in-memory path is preserved unchanged for direct mode (no Temporal) — it's already optimal for single-process execution.

**Two modes, selected by config:**

| Mode | Tracing | Reporting | When |
|---|---|---|---|
| **In-memory** (default) | Existing `GraphTracerManager` / `GraphTracer` | Existing `ReportingManager` | Direct execution (no Temporal) |
| **Event log** | `EventLogTracerManager` → NDJSON files | `ReportingManager` + event emission | Temporal distributed execution |

The `get_tracer_manager()` hub function returns whichever is active. In direct mode, no event log is initialized → existing singleton `GraphTracerManager` is used. In Temporal mode, `WfPipeRouter` initializes an event log → `EventLogTracerManager` is used. Call sites (`pipe_abstract.py`, controllers) don't know or care which mode they're in — both managers expose the same interface.

**Event log backend**: NDJSON files. One file per workflow, organized in a directory per pipeline run:
```
{traces_dir}/{pipeline_run_id}/
  ├── wf_{workflow_id_A}.ndjson
  ├── wf_{workflow_id_B}.ndjson
  └── ...
```

Each line is a JSON-serialized `TraceEvent`. Each file has exactly one writer (the workflow that owns it) — no concurrent write issues.

**Protocol**: `EventLogProtocol` with `emit()` / `read_events()`. The NDJSON backend is the local implementation. Cloud implementation (DynamoDB) will implement the same protocol later.

---

## Step 0: Event Models

> Pure data models — no integration, no refactoring. TDD: write serialization tests first.

### What

Define the `TraceEvent` Pydantic model hierarchy that replaces the in-memory `_MutableNodeData` accumulation. Events capture the same information that `GraphTracer.on_pipe_start()`, `on_pipe_end_success()`, `on_pipe_end_error()`, and the controller-specific registration methods currently capture — but as immutable, serializable records.

### Event type inventory

Map every method on `GraphTracerManager` (see `pipelex/graph/graph_tracer_manager.py`) and `ReportingManager` (see `pipelex/reporting/reporting_manager.py`) to an event type:

| Current method | Event type | Payload (beyond base fields) |
|---|---|---|
| `on_pipe_start()` | `PipeStartEvent` | node_id, parent_node_id, pipe_code, pipe_type, node_kind, input_specs |
| `on_pipe_end_success()` | `PipeEndSuccessEvent` | node_id, ended_at, output_spec, metrics |
| `on_pipe_end_error()` | `PipeEndErrorEvent` | node_id, ended_at, error (ErrorSpec) |
| `add_edge()` | `EdgeEvent` | source_node_id, target_node_id, edge_kind, label, source/target_stuff_digest |
| `register_controller_output()` | `ControllerOutputEvent` | node_id, output_spec |
| `register_batch_item_extraction()` | `BatchItemEvent` | list_stuff_code, item_stuff_code, item_index, batch_controller_node_id |
| `register_batch_aggregation()` | `BatchAggregateEvent` | output_list_stuff_code, item_stuff_code, item_index, batch_controller_node_id |
| `register_parallel_combine()` | `ParallelCombineEvent` | combined_stuff_code, branch_stuff_codes, parallel_controller_node_id |
| `report_inference_job()` | `UsageReportEvent` | node_id (which pipe), tokens_usage (the union type) |

Base fields shared by all events:
- `pipeline_run_id: str`
- `workflow_id: str` — Temporal workflow ID or `"direct"` for in-process
- `event_kind: TraceEventKind` (discriminator)
- `timestamp: datetime` — UTC, for display/debugging only
- `sequence: int` — per-writer monotonic counter, for ordering and deduplication

### Node ID scheme

Change from `{graph_id}:node_{sequence}` to `{graph_id}:{workflow_short_id}:node_{sequence}`.

`workflow_short_id` is the last 8 characters of the Temporal workflow ID, or `"direct"` for in-process mode. Combined with the per-writer sequence counter, this guarantees globally unique node IDs without coordination.

Edge IDs follow the same scheme: `{graph_id}:{workflow_short_id}:edge_{sequence}`.

The sequence counter is **per-writer** (per workflow/file), starting at 0. No need to coordinate across workers.

### Files to create

| File | Contents |
|---|---|
| `pipelex/tracing/__init__.py` | Empty |
| `pipelex/tracing/trace_events.py` | `TraceEventKind` enum, `TraceEvent` base model, all event subclasses |
| `tests/unit/pipelex/tracing/__init__.py` | Empty |
| `tests/unit/pipelex/tracing/test_trace_events.py` | Serialization round-trip tests for each event type |

### Design notes

- Use Pydantic's discriminated union (`Annotated[... , Field(discriminator="event_kind")]`) so `TraceEvent` can be deserialized from JSON without knowing the subclass upfront.
- `IOSpec` and `ErrorSpec` from `pipelex/graph/graphspec.py` are reused as-is — they're already Pydantic models designed for JSON serialization.
- `TokensUsage` is the existing union type `LLMTokensUsage | ImgGenTokensUsage | ExtractTokensUsage | SearchTokensUsage` from `reporting_manager.py`. Reuse it. It also needs a discriminated union wrapper for deserialization.
- `TraceEventKind` inherits from `StrEnum` (imported from `pipelex.types`).

### Checklist

- [ ] Define `TraceEventKind` enum with all event kinds
- [ ] Define `TraceEvent` base model with shared fields
- [ ] Define all event subclasses (`PipeStartEvent`, `PipeEndSuccessEvent`, `PipeEndErrorEvent`, `EdgeEvent`, `ControllerOutputEvent`, `BatchItemEvent`, `BatchAggregateEvent`, `ParallelCombineEvent`, `UsageReportEvent`)
- [ ] Define discriminated union type `AnyTraceEvent` for deserialization
- [ ] Write serialization round-trip tests for each event type
- [ ] Write test for discriminated union deserialization (JSON → correct subclass)
- [ ] Verify `IOSpec`, `ErrorSpec`, `TimingSpec` survive JSON round-trip within events
- [ ] Verify `TokensUsage` union survives round-trip (may need discriminator field)
- [ ] `make agent-check` passes

---

## Step 1: EventLogProtocol & NDJSON Backend

> The write/read infrastructure. TDD: test emit/read cycle first.

### What

Define the `EventLogProtocol` and implement the NDJSON file backend. This is the storage layer — it knows nothing about graphs or reporting, only about appending and reading `TraceEvent` objects.

### EventLogProtocol

```python
class EventLogProtocol(Protocol):
    def emit(self, event: TraceEvent) -> None: ...
    def read_events(self, pipeline_run_id: str) -> list[TraceEvent]: ...
    def cleanup(self, pipeline_run_id: str) -> None: ...
```

`emit()` is **synchronous** — file append is fast and must not become a Temporal replay point. The event is durable when `emit()` returns (file flush).

`read_events()` returns all events for a pipeline run, ordered by `(workflow_id, sequence)`. Used by the assembler post-execution.

`cleanup()` removes the run's directory. Called after graph outputs are generated.

### NDJSON implementation: `NdjsonEventLog`

**Write path** (`emit`):
1. Determine file path: `{traces_dir}/{event.pipeline_run_id}/wf_{event.workflow_id}.ndjson`
2. Create directory if needed (`os.makedirs(..., exist_ok=True)`)
3. Open file in append mode, write `kajson.dumps(event) + "\n"`, flush

File handle caching: keep a `dict[str, IO]` of open file handles keyed by `(pipeline_run_id, workflow_id)`. Close handles on `cleanup()` or when the writer is garbage-collected. This avoids repeated `open()` calls for high-frequency events.

**Read path** (`read_events`):
1. Glob `{traces_dir}/{pipeline_run_id}/wf_*.ndjson`
2. For each file, read all lines, parse each as `AnyTraceEvent` (discriminated union)
3. Deduplicate by `(workflow_id, sequence)` — handles Temporal replay re-emission
4. Sort by `(workflow_id, sequence)` for deterministic ordering
5. Return flat list

**Cleanup path** (`cleanup`):
1. Close any cached file handles for this run
2. `shutil.rmtree({traces_dir}/{pipeline_run_id})`

### InMemoryEventLog

For unit tests and direct mode (optional — direct mode can also use NDJSON):
- `emit()` appends to `list[TraceEvent]`
- `read_events()` returns the list filtered by pipeline_run_id
- No file I/O

### Configuration

Add to `pipelex/pipelex.toml` under a new `[pipelex.tracing]` section:

```toml
[pipelex.tracing]
# Event log backend: "ndjson" (local files) or "in_memory" (no persistence)
backend = "ndjson"
# Base directory for NDJSON trace files
traces_dir = ".pipelex/traces"
# Whether tracing is enabled (independent of graph generation)
enabled = true
```

The `traces_dir` is relative to the working directory (like other Pipelex output dirs). Absolute paths are also supported.

### Files to create

| File | Contents |
|---|---|
| `pipelex/tracing/event_log_protocol.py` | `EventLogProtocol` |
| `pipelex/tracing/ndjson_event_log.py` | `NdjsonEventLog` implementation |
| `pipelex/tracing/in_memory_event_log.py` | `InMemoryEventLog` for tests |
| `pipelex/tracing/tracing_config.py` | `TracingConfig` model |
| `pipelex/pipelex.toml` | Add `[pipelex.tracing]` section |
| `pipelex/system/configuration/configs.py` | Add `TracingConfig` to main config |
| `tests/unit/pipelex/tracing/test_ndjson_event_log.py` | Emit/read/cleanup/dedup tests |

### Checklist

- [ ] Define `EventLogProtocol`
- [ ] Implement `NdjsonEventLog` write path (emit with file handle caching)
- [ ] Implement `NdjsonEventLog` read path (glob, parse, deduplicate, sort)
- [ ] Implement `NdjsonEventLog` cleanup
- [ ] Implement `InMemoryEventLog`
- [ ] Define `TracingConfig` and wire into main config
- [ ] Add `[pipelex.tracing]` to `pipelex.toml`
- [ ] Test: emit events, read them back, verify order and content
- [ ] Test: emit duplicate events (same workflow_id + sequence), verify deduplication
- [ ] Test: emit from "multiple workers" (different workflow_ids), verify all events returned
- [ ] Test: cleanup removes directory
- [ ] Test: read from nonexistent run returns empty list
- [ ] `make agent-check` passes
- [ ] `make agent-test` passes (existing tests unaffected)

---

## Step 2: GraphSpec Assembler

> Reconstructs a `GraphSpec` from trace events. This is the core algorithm — equivalent to `GraphTracer.teardown()` but working from events instead of in-memory state.

### What

The assembler reads a flat list of `TraceEvent` objects and produces a `GraphSpec`. It must reproduce the same graph that the current `GraphTracer` produces for identical executions. This is the correctness benchmark.

### Algorithm outline

The assembler replays the same logic currently spread across `GraphTracer.teardown()` and its `_generate_*_edges()` methods:

1. **Build nodes** from `PipeStartEvent` + `PipeEndSuccessEvent`/`PipeEndErrorEvent`:
   - `PipeStartEvent` → create `NodeSpec` with status=RUNNING, record input_specs
   - `PipeEndSuccessEvent` → update status=SUCCEEDED, set timing, record output_spec
   - `PipeEndErrorEvent` → update status=FAILED, set timing and error
   - Unmatched `PipeStartEvent` (no end event) → status=CANCELED (same as current `teardown()`)

2. **Collect explicit edges** from `EdgeEvent`:
   - CONTAINS edges (parent → child) are emitted at pipe start time
   - SELECTED_OUTCOME edges from PipeCondition

3. **Build producer map** from `PipeEndSuccessEvent` + `ControllerOutputEvent`:
   - Track `stuff_code → node_id` (same as `_stuff_producer_map` in current tracer)
   - `ControllerOutputEvent` overrides the producer (same as `register_controller_output()`)
   - Pass-through detection: skip if output digest matches an input digest

4. **Generate DATA edges** from producer map + node inputs:
   - Same algorithm as `GraphTracer._generate_data_edges()` — for each node's inputs, find the producer by digest, create DATA edge

5. **Generate BATCH_ITEM edges** from `BatchItemEvent`:
   - Same algorithm as `GraphTracer._generate_batch_item_edges()`

6. **Generate BATCH_AGGREGATE edges** from `BatchAggregateEvent`:
   - Same algorithm as `GraphTracer._generate_batch_aggregate_edges()`

7. **Generate PARALLEL_COMBINE edges** from `ParallelCombineEvent`:
   - `ParallelCombineEvent` carries the snapshotted branch producer node IDs (same as `register_parallel_combine()` snapshots `_stuff_producer_map` before override)
   - Same algorithm as `GraphTracer._generate_parallel_combine_edges()`

### Usage aggregator

Simpler — just collects `UsageReportEvent` objects:

```python
class UsageAggregator:
    @staticmethod
    def aggregate(events: list[TraceEvent]) -> list[TokensUsage]:
        return [e.tokens_usage for e in events if isinstance(e, UsageReportEvent)]
```

Per-step attribution is already available since `UsageReportEvent` carries `node_id`.

### Correctness strategy

The assembler must produce a `GraphSpec` that is **structurally identical** to what the current `GraphTracer` produces. To verify:

1. Existing unit tests for graph tracing (`tests/unit/pipelex/graph/`) produce known-good GraphSpecs
2. Write a test adapter that runs the same scenario through both paths:
   - Path A: current `GraphTracer` (in-memory)
   - Path B: emit events → assembler → GraphSpec
3. Compare the two GraphSpecs field-by-field (modulo node/edge ID prefixes which change)

This is the **most important testing step** — it catches any divergence between the event-based and in-memory paths.

### Files to create

| File | Contents |
|---|---|
| `pipelex/tracing/graphspec_assembler.py` | `GraphSpecAssembler.assemble(events) -> GraphSpec` |
| `pipelex/tracing/usage_aggregator.py` | `UsageAggregator.aggregate(events) -> list[TokensUsage]` |
| `tests/unit/pipelex/tracing/test_graphspec_assembler.py` | Hand-crafted event sequences → expected GraphSpec |
| `tests/unit/pipelex/tracing/test_usage_aggregator.py` | Usage event aggregation tests |

### Checklist

- [ ] Implement `GraphSpecAssembler.assemble()` — node construction from start/end events
- [ ] Implement CONTAINS edge reconstruction (from PipeStartEvent.parent_node_id)
- [ ] Implement producer map construction (from PipeEndSuccessEvent + ControllerOutputEvent)
- [ ] Implement pass-through detection (output digest in input digests → skip producer registration)
- [ ] Implement DATA edge generation (digest correlation, same algorithm as `GraphTracer._generate_data_edges()`)
- [ ] Implement BATCH_ITEM edge generation from `BatchItemEvent`
- [ ] Implement BATCH_AGGREGATE edge generation from `BatchAggregateEvent`
- [ ] Implement PARALLEL_COMBINE edge generation from `ParallelCombineEvent`
- [ ] Handle CANCELED nodes (PipeStartEvent without matching end event)
- [ ] Implement `UsageAggregator`
- [ ] Test: simple sequence (3 pipes in order) → correct nodes, CONTAINS edges, DATA edges
- [ ] Test: parallel branches → correct PARALLEL_COMBINE edges
- [ ] Test: batch fan-out/fan-in → correct BATCH_ITEM + BATCH_AGGREGATE edges
- [ ] Test: condition with selected outcome → correct SELECTED_OUTCOME edge
- [ ] Test: partial failure (PipeStartEvent + PipeEndErrorEvent, no end for parent) → FAILED + CANCELED nodes
- [ ] Test: events from multiple workflows (different workflow_id prefixes) assemble correctly
- [ ] Test: usage aggregation collects all UsageReportEvent records
- [ ] Equivalence test: compare assembler output with current GraphTracer output for a known scenario
- [ ] `make agent-check` passes

---

## Step 3: Emit Adapter (GraphTracerManager Wrapper)

> Bridge between existing code and the event log. Minimal changes to `pipe_abstract.py` and controllers.

### What

Create a new `EventLogTracerManager` that implements the same interface as `GraphTracerManager` but emits events to the `EventLogProtocol` instead of accumulating in memory.

The goal is to **minimize changes to call sites**. `pipe_abstract.py` and the controller pipes currently call `GraphTracerManager` methods — they should call the same methods on the new adapter with minimal signature changes.

### Approach: wrapper, not replacement

Keep `GraphTracerManager` alive. Introduce `EventLogTracerManager` that wraps an `EventLogProtocol` and provides the same method signatures. The choice of which manager to use is made at initialization time based on config.

Why wrapper instead of replacing GraphTracer internals:
- The current GraphTracer has complex state management (`_stuff_producer_map`, `_batch_item_map`, etc.) that's tightly coupled to in-memory accumulation
- The event log approach doesn't need any of that state — it just emits events
- The assembler (Step 2) handles all the correlation that currently happens in `teardown()`
- Cleaner to have a thin emit layer than to refactor GraphTracer's internals

### EventLogTracerManager interface

Must match `GraphTracerManager`'s public API so call sites don't change:

```python
class EventLogTracerManager:
    def __init__(self, event_log: EventLogProtocol, workflow_id: str):
        self._event_log = event_log
        self._workflow_id = workflow_id
        self._sequence = 0

    def on_pipe_start(self, graph_context, pipe_code, pipe_type, node_kind, started_at, input_specs=None):
        # Generate node_id with workflow-scoped prefix
        node_id = f"{graph_context.graph_id}:{self._workflow_short_id}:node_{self._sequence}"
        self._sequence += 1
        # Emit PipeStartEvent
        # Emit EdgeEvent(CONTAINS) if parent_node_id
        # Return (node_id, child_graph_context)

    def on_pipe_end_success(self, graph_id, node_id, ended_at, output_spec=None, ...):
        # Emit PipeEndSuccessEvent

    def on_pipe_end_error(self, graph_id, node_id, ended_at, error_type, error_message, error_stack=None):
        # Emit PipeEndErrorEvent

    def add_edge(self, graph_id, source_node_id, target_node_id, edge_kind, label=None, ...):
        # Emit EdgeEvent

    def register_controller_output(self, graph_id, node_id, output_spec):
        # Emit ControllerOutputEvent

    def register_batch_item_extraction(self, graph_id, list_stuff_code, item_stuff_code, item_index, ...):
        # Emit BatchItemEvent

    def register_batch_aggregation(self, graph_id, output_list_stuff_code, item_stuff_code, item_index, ...):
        # Emit BatchAggregateEvent

    def register_parallel_combine(self, graph_id, combined_stuff_code, branch_stuff_codes, ...):
        # Emit ParallelCombineEvent
        # NOTE: The current GraphTracer snapshots _stuff_producer_map here.
        # With events, the assembler handles this — it processes events in order
        # and sees ParallelCombineEvent BEFORE ControllerOutputEvent (same call order).
```

### Key difference: `register_parallel_combine` and producer map snapshotting

In the current `GraphTracer`, `register_parallel_combine()` snapshots `_stuff_producer_map` to capture branch producer node IDs **before** `register_controller_output()` overrides them. This is a subtle ordering dependency.

With the event log, the assembler processes events in emission order. If `ParallelCombineEvent` is emitted before `ControllerOutputEvent` (which it is — same call order in `pipe_parallel.py`), the assembler can snapshot the producer map at that point. **The event carries the branch_stuff_codes; the assembler looks up the current producers at processing time.**

Alternatively, the `ParallelCombineEvent` can carry the snapshotted branch producer node IDs directly (resolved at emit time). This is safer — it doesn't depend on the assembler processing order. **Recommendation: include snapshotted producer IDs in the event.** This means the emit adapter must track a local producer map (lightweight — just `dict[str, str]`).

### How pipe_abstract.py changes

Current code in `pipe_abstract.py:run_pipe()` (lines 394-396):
```python
parent_graph_context = job_metadata.graph_context
if parent_graph_context is not None:
    tracer_manager = GraphTracerManager.get_instance()
    if tracer_manager is not None:
        ...
```

New code:
```python
parent_graph_context = job_metadata.graph_context
if parent_graph_context is not None:
    tracer_manager = get_tracer_manager()  # Returns EventLogTracerManager or GraphTracerManager
    if tracer_manager is not None:
        ...  # Same calls, same signatures
```

`get_tracer_manager()` is a new hub function that returns the active tracer manager. Resolution order:
1. If an `EventLogTracerManager` is set on the ContextVar (Temporal mode) → return it
2. Else fall back to `GraphTracerManager.get_instance()` (direct mode, existing singleton)
3. If neither → return None (tracing disabled)

**Direct mode is completely unchanged.** No event log is initialized, no new code runs. The existing `GraphTracerManager` singleton handles everything as it does today.

### Reporting integration

For `UsageReportEvent`, the emit point is in the inference workers (`llm_worker_abstract.py:334`, etc.). Two options:

**(a) Emit from the existing ReportingManager**: Add event log emission to `ReportingManager.report_inference_job()`. The manager continues to accumulate locally AND emits to the event log. Dual-write.

**(b) Separate emit path**: Add `event_log.emit(UsageReportEvent(...))` directly in the inference workers. Cleaner separation but more call sites to change.

**Recommendation**: (a) — the ReportingManager already dispatches by job type and extracts `tokens_usage`. Add a single emit call there. This also means the existing local accumulation continues to work for direct mode (unchanged).

The ReportingManager needs access to the event log. Options:
- Pass via constructor (explicit)
- Read from ContextVar/hub (implicit, matches existing pattern)

**Recommendation**: Hub-based — add `get_event_log()` to the hub. ReportingManager reads it when available. When None (event log not configured), it just accumulates locally as today.

### Files to create / modify

| File | Change |
|---|---|
| `pipelex/tracing/event_log_tracer_manager.py` | **New** — `EventLogTracerManager` |
| `pipelex/tracing/tracer_factory.py` | **New** — factory that creates the right manager based on config |
| `pipelex/hub.py` | Add `get_event_log()`, `set_event_log()`, `get_tracer_manager()` |
| `pipelex/core/pipes/pipe_abstract.py` | Replace `GraphTracerManager.get_instance()` with `get_tracer_manager()` |
| `pipelex/reporting/reporting_manager.py` | Add event log emission in `report_inference_job()` |
| `pipelex/pipe_controllers/parallel/pipe_parallel.py` | Use `get_tracer_manager()` instead of `GraphTracerManager.get_instance()` |
| `pipelex/pipe_controllers/batch/pipe_batch.py` | Same |
| `pipelex/pipe_controllers/condition/pipe_condition.py` | Same |

### Checklist

- [ ] Implement `EventLogTracerManager` with all methods matching `GraphTracerManager` signatures
- [ ] Implement local producer map tracking for `ParallelCombineEvent` snapshotting
- [ ] Implement node ID generation with workflow-scoped prefix
- [ ] Implement edge ID generation with workflow-scoped prefix
- [ ] Add `get_event_log()` / `set_event_log()` to hub (ContextVar-based)
- [ ] Add `get_tracer_manager()` to hub — returns `EventLogTracerManager` when event log is active, else `GraphTracerManager`
- [ ] Update `pipe_abstract.py` to use `get_tracer_manager()`
- [ ] Update controller call sites (parallel, batch, condition) to use `get_tracer_manager()`
- [ ] Add event log emission to `ReportingManager.report_inference_job()`
- [ ] Test: `EventLogTracerManager` emits correct events for a pipe start/end cycle
- [ ] Test: CONTAINS edge emitted when parent_node_id is present
- [ ] Test: controller output registration emits `ControllerOutputEvent`
- [ ] Test: parallel combine emits `ParallelCombineEvent` with snapshotted producers
- [ ] `make agent-check` passes

---

## Step 4: Wire into Pipeline Lifecycle

> Connect event log initialization/finalization to the pipeline run lifecycle and Temporal workflow lifecycle.

### What

The event log must be opened at the start of a pipeline run and read at the end. In direct mode, this happens in `runner.py` / `pipeline_run_setup.py`. In Temporal mode, the API process opens it, and each `WfPipeRouter` connects to it.

### Direct mode flow — UNCHANGED

**No event log is initialized in direct mode.** The existing code path is preserved exactly:
- `pipeline_run_setup.py` calls `GraphTracerManager.open_tracer()` as today
- `pipe_abstract.py` calls `get_tracer_manager()` which resolves to `GraphTracerManager.get_instance()` (no ContextVar set → fallback)
- `runner.py` calls `GraphTracerManager.close_tracer()` in the `finally` block as today
- `ReportingManager` accumulates in memory as today (no event log available → no emission)

All existing tests pass without modification because the direct mode code path is identical.

### Temporal mode flow

**API process** (`PipeRouterTop._run_pipe_job()` or `pipeline_run_setup()`):
- Create event log (NdjsonEventLog pointing to shared traces dir)
- Set on hub ContextVar
- After workflow completes (or fails): read events, assemble, generate outputs

**Worker process** (`WfPipeRouter.run()`):
- Create event log client pointing to same traces dir (from config)
- Create `EventLogTracerManager` with the Temporal `workflow.info().workflow_id`
- Set on hub ContextVar
- Pipe execution emits events to the log
- No assembly on the worker — that's the API process's job

**Key**: Both API and workers point to the same `traces_dir`. For local dev (same machine), this is a local filesystem path. For cloud, this would be replaced by DynamoDB (different backend, same protocol).

### How `WfPipeRouter.run()` changes

Current code opens a per-workflow library. Add event log setup in the same block:

```python
# After library crate setup, before pipe execution:
if workflow_arg.job_metadata.graph_context is not None:
    event_log = NdjsonEventLog(traces_dir=tracing_config.traces_dir)
    set_event_log(event_log)
    tracer_mgr = EventLogTracerManager(
        event_log=event_log,
        workflow_id=workflow.info().workflow_id,
    )
    set_tracer_manager(tracer_mgr)
```

**Important**: This must happen before `pipe.run_pipe()` but within the `workflow.unsafe.imports_passed_through()` block. The event log writes are side effects that happen during execution — Temporal replay will re-execute them, but the deduplication in `read_events()` handles this.

### Tracing config propagation

The `traces_dir` path must be available on workers. Options:

**(a)** Workers read from `pipelex.toml` config (already loaded at worker startup). The traces dir is in config → workers know where to write. **This is the recommendation** — same pattern as other config.

**(b)** Pass via `GraphContext` or `PipeJob`. More explicit but adds fields.

### Graph output generation

After assembly, the existing graph output pipeline (`graph_factory.py`, `generate_graph_outputs()`) works unchanged — it takes a `GraphSpec` and produces Mermaid/ReactFlow files. No changes needed there.

### Files to modify

| File | Change |
|---|---|
| `pipelex/temporal/tprl_pipe/wf_pipe_router.py` | Initialize event log and tracer manager per workflow |
| `pipelex/pipeline/runner.py` | After Temporal workflow completes/fails: read events, assemble, generate graph outputs |
| `pipelex/temporal/tprl_pipe/pipe_router_top.py` | Initialize event log before submitting to Temporal |
| `pipelex/config.py` or `pipelex/system/configuration/configs.py` | Expose tracing config |

### Checklist

- [ ] Initialize event log in `PipeRouterTop` before Temporal submission (Temporal mode only)
- [ ] Initialize event log + `EventLogTracerManager` in `WfPipeRouter.run()` (per-workflow)
- [ ] Verify `traces_dir` is accessible from worker config
- [ ] Read events + assemble GraphSpec in `runner.py` after Temporal workflow completes (or fails)
- [ ] Feed assembled GraphSpec into existing graph output generation (`generate_graph_outputs()`)
- [ ] Read events + aggregate usage into cost report
- [ ] Handle the `finally` block: assemble even on pipeline failure (partial graph with FAILED/CANCELED nodes)
- [ ] Verify cleanup: traces dir cleaned up after outputs generated (configurable)
- [ ] Verify direct mode is completely unchanged — no event log initialized, existing in-memory path used
- [ ] Test (Temporal): `pipelex run pipe --graph` with Temporal produces correct GraphSpec via event log
- [ ] Test: usage report generated correctly from events across workers
- [ ] `make agent-check` passes
- [ ] `make agent-test` passes — all existing tests pass unchanged (direct mode untouched)

---

## Step 5: Temporal Integration Tests

> Validate that tracing works across Temporal workers. This is the end-to-end proof.

### What

Integration tests that run pipe controllers on Temporal workers and verify the assembled GraphSpec is complete and correct. These extend the existing Temporal integration tests in `tests/integration/pipelex/temporal/`.

### Test scenarios

Each test submits a pipeline to Temporal, waits for completion (or failure), reads events from the NDJSON event log, assembles a GraphSpec, and asserts on its structure.

| Scenario | What it validates |
|---|---|
| PipeSequence (LLM steps via Temporal) | Nodes from multiple workers, CONTAINS edges, DATA edges across workers |
| PipeParallel (branches on different workers) | PARALLEL_COMBINE edges, concurrent worker event files |
| PipeBatch (fan-out to workers) | BATCH_ITEM + BATCH_AGGREGATE edges across workers |
| Pipeline failure (LLM step fails) | Partial graph: FAILED node, CANCELED parent, usage still captured |
| Usage reporting | Token costs aggregated across workers |
| Dry-run with graph | Same structure but with StuffArtefact (if fixed) or xfail |

### Reuse existing test infrastructure

The `tests/integration/pipelex/temporal/library_crate/` directory already has `.mthds` bundles and test infrastructure for Temporal integration tests. Extend with graph tracing assertions.

### Checklist

- [ ] Test: PipeSequence through Temporal produces correct GraphSpec (nodes, CONTAINS, DATA edges)
- [ ] Test: PipeParallel through Temporal produces correct PARALLEL_COMBINE edges
- [ ] Test: events from multiple workers are in separate NDJSON files
- [ ] Test: deduplication handles Temporal replay (emit same events twice, assembler produces correct graph)
- [ ] Test: pipeline failure produces partial graph with FAILED/CANCELED nodes
- [ ] Test: usage reporting works across Temporal workers
- [ ] Test: usage aggregation matches expected token counts
- [ ] Test: graph output files (Mermaid, ReactFlow) generated correctly from assembled GraphSpec
- [ ] `make agent-check` passes
- [ ] `make agent-test` passes

---

## Non-Goals (Deferred)

These are explicitly out of scope for this plan. They're documented in [wip/distributed-tracing-and-reporting.md](wip/distributed-tracing-and-reporting.md).

| Item | Why deferred |
|---|---|
| DynamoDB backend | Cloud-only — implement when deploying to AWS with remote workers |
| Real-time progress consumer | No consumer exists yet — the protocol supports it, build when needed |
| `subscribe()` on EventLogProtocol | Polling-based reads are sufficient for now; add when real-time consumer exists |
| Remove `GraphTracerManager` / `GraphTracer` | Actively used in direct mode — not a removal candidate. They stay as the in-memory path. |
| Large data externalization | Inline data in events for now; add StorageProvider offloading when traces grow too large |
| TraceSinkProtocol abstraction | The EventLogProtocol is sufficient; the higher-level sink abstraction can wait for the cloud backend |
