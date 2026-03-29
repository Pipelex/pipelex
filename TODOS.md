phase 4.5 of wip/00-master-plan.md

# Distributed Tracing & Reporting — Local Version

> Implementation plan for the NDJSON-file-based event log that enables graph tracing and cost reporting across Temporal workers.
> Design rationale and cloud architecture (DynamoDB) in [wip/distributed-tracing-and-reporting.md](wip/distributed-tracing-and-reporting.md).

---

## Overview

Add a **file-based event log** to the existing `GraphTracer`, for use when running with Temporal distributed workers. The in-memory path is preserved unchanged for direct mode (no Temporal) — it's already optimal for single-process execution.

**Approach: dual-write in GraphTracer.** When an `EventLogProtocol` is provided, `GraphTracer` emits events as a side effect alongside its existing in-memory accumulation. No new tracer class, no new hub functions, no call site changes. `pipe_abstract.py` and controllers continue calling `GraphTracerManager` as before.

**Two modes, selected at tracer open time:**

| Mode | What happens in GraphTracer | Reporting | When |
|---|---|---|---|
| **In-memory only** (default) | Existing accumulation, `teardown()` → `GraphSpec` | Existing `ReportingManager` | Direct execution (no Temporal) |
| **In-memory + event log** | Same accumulation + `emit()` to NDJSON per method call | `ReportingManager` + event emission from activities | Temporal distributed execution |

In direct mode, `open_tracer()` is called without an event log → `GraphTracer` works as today. In Temporal mode, `WfPipeRouter` creates an `NdjsonEventLog` and passes it to `open_tracer()` → `GraphTracer` dual-writes. After all workflows complete, `runner.py` reads events from all files and assembles a cross-worker `GraphSpec`.

**Event log backend**: NDJSON files. One file per workflow (or per activity for usage events), organized in a directory per pipeline run:
```
{traces_dir}/{pipeline_run_id}/
  ├── wf_{workflow_id_A}.ndjson
  ├── wf_{workflow_id_B}.ndjson
  ├── act_{activity_id_X}.ndjson      # Usage events from activities
  └── ...
```

Each line is a JSON-serialized `TraceEvent`. Workflow files have exactly one writer. Activity files have one writer per activity execution.

**Protocol**: `EventLogProtocol` with `emit()` / `read_events()`. The NDJSON backend is the local implementation. Cloud implementation (DynamoDB) will implement the same protocol later.

**Key design invariant**: `emit()` MUST be synchronous (file append + flush). This guarantees all events are flushed before a child workflow returns. If emit were async or batched, the assembler could read incomplete files. This invariant must be preserved in any future backend implementation.

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

Change from `{graph_id}:node_{sequence}` to `{graph_id}:{workflow_id}:node_{sequence}`.

`workflow_id` is the full Temporal workflow ID, or `"direct"` for in-process mode. Combined with the per-writer sequence counter, this guarantees globally unique node IDs without coordination. Using the full workflow ID avoids collision — the last 8 chars of Temporal workflow IDs often come from the base ID (e.g. `pipe_router`) and repeat across workflows.

Edge IDs follow the same scheme: `{graph_id}:{workflow_id}:edge_{sequence}`.

The sequence counter is **per-writer** (per workflow/file), starting at 0. No need to coordinate across workers.

**Renderer impact**: Mermaid/ReactFlow renderers that parse node IDs by splitting on `:` must handle the additional segment. Node IDs are opaque strings in most code — only renderers and test assertions need updating.

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
- `TokensUsage` is the existing union type `LLMTokensUsage | ImgGenTokensUsage | ExtractTokensUsage | SearchTokensUsage` from `reporting_manager.py`. Reuse it. It needs a discriminated union wrapper for deserialization: `AnyTokensUsage = Annotated[TokensUsage, Field(discriminator="model_type")]`. **Prerequisite**: each TokensUsage model's `model_type` field must be changed from `str` to `Literal` (e.g., `model_type: Literal["llm"] = "llm"` instead of `model_type: str = "llm"`). This is a one-line change per model in `llm_report.py`, `img_gen_report.py`, `extract_report.py`, `search_report.py`.
- `TraceEventKind` inherits from `StrEnum` (imported from `pipelex.types`).

### Checklist

- [x] Define `TraceEventKind` enum with all event kinds
- [x] Define `TraceEvent` base model with shared fields
- [x] Define all event subclasses (`PipeStartEvent`, `PipeEndSuccessEvent`, `PipeEndErrorEvent`, `EdgeEvent`, `ControllerOutputEvent`, `BatchItemEvent`, `BatchAggregateEvent`, `ParallelCombineEvent`, `UsageReportEvent`)
- [x] Define discriminated union type `AnyTraceEvent` for deserialization
- [x] Write serialization round-trip tests for each event type
- [x] Write test for discriminated union deserialization (JSON → correct subclass)
- [x] Verify `IOSpec`, `ErrorSpec`, `TimingSpec` survive JSON round-trip within events
- [x] Fix `model_type` field to `Literal` on `LLMTokensUsage`, `ImgGenTokensUsage`, `ExtractTokensUsage`, `SearchTokensUsage`
- [x] Define `AnyTokensUsage` discriminated union using `Field(discriminator="model_type")`
- [x] Verify `TokensUsage` union survives round-trip with discriminated union deserialization
- [x] `make agent-check` passes

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

**Critical invariant**: `emit()` must remain synchronous with an explicit file flush. This guarantees all events are written before a child workflow returns to its parent. If emit were async or batched, the assembler could read incomplete files from child workflows. This invariant must be preserved in any future backend implementation (DynamoDB, etc.).

`read_events()` returns all events for a pipeline run, ordered by `(workflow_id, sequence)`. Used by the assembler post-execution.

`cleanup()` removes the run's directory. Called after graph outputs are generated.

### NDJSON implementation: `NdjsonEventLog`

**Write path** (`emit`):
1. Determine file path: `{traces_dir}/{event.pipeline_run_id}/wf_{event.workflow_id}.ndjson`
2. Create directory if needed (`os.makedirs(..., exist_ok=True)`)
3. Open file in append mode, write `kajson.dumps(event) + "\n"`, flush

File handle caching: keep a `dict[str, IO]` of open file handles keyed by `(pipeline_run_id, workflow_id)`. Close handles on `cleanup()` or when the writer is garbage-collected. This avoids repeated `open()` calls for high-frequency events.

**Read path** (`read_events`):
1. Glob `{traces_dir}/{pipeline_run_id}/*.ndjson` (includes `wf_*` and `act_*` files)
2. For each file, read all lines, parse each as `AnyTraceEvent` (discriminated union)
   - **Corrupt line handling**: Wrap each line parse in `try/except JSONDecodeError`. Log a warning with the file path and line number, then skip the corrupt line. This handles crash-mid-write scenarios where NDJSON has no journaling.
3. Deduplicate by `(workflow_id, sequence)` — handles Temporal replay re-emission. When duplicates exist, keep the first occurrence (they are identical for correct replays).
4. Sort by `(workflow_id, sequence)` for deterministic ordering
5. Return flat list

**Replay growth note**: When Temporal replays a workflow, events are re-appended with the same `(workflow_id, sequence)` pairs. The NDJSON file grows with each replay. This is functionally correct (dedup on read handles it) but wastes disk. This is an accepted tradeoff for the simplicity of append-only writes. SQLite's `INSERT OR IGNORE` would prevent duplicate writes entirely, but NDJSON is simpler and sufficient for local dev.

**Cleanup path** (`cleanup`):
1. Close any cached file handles for this run
2. `shutil.rmtree({traces_dir}/{pipeline_run_id})`

**Important**: Traces are never auto-deleted after graph assembly. Cleanup must be explicitly called by the user or a separate cleanup command. This ensures traces are available for debugging if assembly fails, and for usage reporting which may run after graph generation.

### InMemoryEventLog

For unit tests and direct mode (optional — direct mode can also use NDJSON):
- `emit()` appends to `list[TraceEvent]`
- `read_events()` returns the list filtered by pipeline_run_id
- No file I/O

### Files to create

| File | Contents |
|---|---|
| `pipelex/tracing/event_log_protocol.py` | `EventLogProtocol` |
| `pipelex/tracing/ndjson_event_log.py` | `NdjsonEventLog` implementation |
| `pipelex/tracing/in_memory_event_log.py` | `InMemoryEventLog` for tests |
| `tests/unit/pipelex/tracing/test_ndjson_event_log.py` | Emit/read/cleanup/dedup tests |

### Checklist

- [x] Define `EventLogProtocol`
- [x] Implement `NdjsonEventLog` write path (emit with file handle caching)
- [x] Implement `NdjsonEventLog` read path (glob, parse, deduplicate, sort)
- [x] Implement `NdjsonEventLog` cleanup
- [x] Implement `InMemoryEventLog`
- [x] Test: emit events, read them back, verify order and content
- [x] Test: emit duplicate events (same workflow_id + sequence), verify deduplication
- [x] Test: emit from "multiple workers" (different workflow_ids), verify all events returned
- [x] Test: cleanup removes directory
- [x] Test: read from nonexistent run returns empty list
- [x] Test: corrupt NDJSON line (truncated JSON) is skipped with warning
- [x] Test: multiprocess concurrent writes — spawn workers writing to the same traces_dir (different files), verify no corruption or directory race conditions
- [x] `make agent-check` passes
- [x] `make agent-test` passes (existing tests unaffected)

---

## Step 2: GraphSpec Assembler

> Reconstructs a `GraphSpec` from trace events. This is the core algorithm — equivalent to `GraphTracer.teardown()` but working from events instead of in-memory state.

### What

The assembler reads a flat list of `TraceEvent` objects and produces a `GraphSpec`. It must reproduce the same graph that the current `GraphTracer` produces for identical executions. This is the correctness benchmark.

### Algorithm outline

The assembler uses a **two-pass** approach, mirroring `GraphTracer.teardown()` which builds all nodes first, then generates edges. This is critical for cross-worker correctness: events from different workflows arrive in arbitrary order (sorted by `(workflow_id, sequence)` which is alphabetical, not causal). The two-pass approach ensures the complete producer map is built before any edge generation, regardless of which workflow produced or consumed a given stuff.

**Pass 1 — Build nodes and producer map** (process all events):

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
   - Pass-through detection: skip if output digest matches an input digest (must mirror `GraphTracer.on_pipe_end_success()` lines 477-488 exactly)

4. **Collect batch/parallel metadata** from `BatchItemEvent`, `BatchAggregateEvent`, `ParallelCombineEvent`:
   - Store for edge generation in Pass 2

**Pass 2 — Generate all edges** (using the complete producer map):

5. **Generate DATA edges** from producer map + node inputs:
   - Same algorithm as `GraphTracer._generate_data_edges()` — for each node's inputs, find the producer by digest, create DATA edge

6. **Generate BATCH_ITEM edges** from `BatchItemEvent`:
   - Same algorithm as `GraphTracer._generate_batch_item_edges()`

7. **Generate BATCH_AGGREGATE edges** from `BatchAggregateEvent`:
   - Same algorithm as `GraphTracer._generate_batch_aggregate_edges()`

8. **Generate PARALLEL_COMBINE edges** from `ParallelCombineEvent`:
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
   - Path A: current `GraphTracer` (in-memory only, no event log)
   - Path B: `GraphTracer` with event log enabled → emit events → assembler → GraphSpec
3. Compare the two GraphSpecs using **structural equivalence**:
   - Same number of nodes, same `NodeStatus` per node, same `pipe_code` per node
   - Same number of edges, same `EdgeKind` between corresponding nodes
   - Same `IOSpec` digests on inputs/outputs
   - **Normalize IDs**: Strip the workflow_id segment from node/edge IDs (e.g., `graph_1:wf_abc:node_0` → `graph_1:node_0`) for comparison
   - **Ignore `TimingSpec`**: Timestamps will differ between the two paths
   - **Ignore edge ordering**: Compare edges as sets (by kind + source + target after ID normalization)

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
- [ ] Test: cross-workflow producer map — producer in alphabetically-later workflow_id, consumer in earlier one (validates two-pass assembly ordering)
- [ ] Test: usage aggregation collects all UsageReportEvent records
- [ ] Equivalence test: compare assembler output with current GraphTracer output using structural equivalence (normalized IDs, ignored TimingSpec)
- [ ] `make agent-check` passes

---

## Step 3: Emit Integration (Dual-Write in GraphTracer)

> Add event emission to the existing GraphTracer. Zero changes to call sites.

### What

Add an optional `EventLogProtocol` to `GraphTracer`. When set, every tracing method (`on_pipe_start`, `on_pipe_end_success`, etc.) emits a `TraceEvent` as a side effect **in addition to** the existing in-memory accumulation. No new tracer class, no new hub functions, no call site changes.

### Why this approach (not a separate EventLogTracerManager)

The original plan proposed a parallel `EventLogTracerManager` class matching `GraphTracerManager`'s interface. The engineering review identified that this was overbuilt:
- `GraphTracer` already maintains `_stuff_producer_map` — the `ParallelCombineEvent` snapshotting comes for free
- `GraphTracer` already has the pass-through detection logic — no risk of drift
- No need for a `TracerManagerProtocol` — `GraphTracerManager` is the only manager
- No need for `get_tracer_manager()` hub function — `GraphTracerManager.get_instance()` works as before
- `pipe_abstract.py` and all controllers: **zero changes**

### Changes to `GraphTracer`

Add two new fields:
```python
class GraphTracer(GraphTracerProtocol):
    _event_log: EventLogProtocol | None   # None = no event emission (direct mode)
    _workflow_id: str                      # "direct" for direct mode, full Temporal workflow ID otherwise
```

In `setup()`: accept optional `event_log` and `workflow_id` params. Store them.

In each tracing method, add event emission **after** the existing in-memory logic:

| Method | Existing logic (unchanged) | Event emission (new, when `_event_log is not None`) |
|---|---|---|
| `on_pipe_start()` | Create `_MutableNodeData`, add CONTAINS edge, return `(node_id, child_context)` | Emit `PipeStartEvent` + `EdgeEvent(CONTAINS)` if parent |
| `on_pipe_end_success()` | Update node status/timing, register producer, pass-through detection | Emit `PipeEndSuccessEvent` |
| `on_pipe_end_error()` | Update node status/timing/error | Emit `PipeEndErrorEvent` |
| `add_edge()` | Create `EdgeSpec`, append to `_edges` | Emit `EdgeEvent` |
| `register_controller_output()` | Append output_spec, update `_stuff_producer_map` | Emit `ControllerOutputEvent` |
| `register_batch_item_extraction()` | Update `_batch_item_map` | Emit `BatchItemEvent` |
| `register_batch_aggregation()` | Update `_batch_aggregate_map` | Emit `BatchAggregateEvent` |
| `register_parallel_combine()` | Snapshot producers, update `_parallel_combine_map` | Emit `ParallelCombineEvent` with snapshotted branch producer IDs |

The `ParallelCombineEvent` carries the snapshotted branch producer node IDs directly from `_stuff_producer_map`, which `GraphTracer` already maintains. No additional state needed.

### Node ID generation in Temporal mode

When `_workflow_id` is not `"direct"`, node IDs are generated as `{graph_id}:{workflow_id}:node_{seq}` instead of `{graph_id}:node_{seq}`. The `_node_sequence` counter is per-tracer (per-workflow), starting at 0. Combined with the full `workflow_id`, this guarantees globally unique node IDs without coordination.

Edge IDs follow the same scheme.

### Changes to `GraphTracerManager`

`open_tracer()` gains two optional params:
```python
def open_tracer(
    self,
    graph_id: str,
    data_inclusion: DataInclusionConfig,
    pipeline_ref_domain: str | None = None,
    pipeline_ref_main_pipe: str | None = None,
    event_log: EventLogProtocol | None = None,     # NEW
    workflow_id: str = "direct",                     # NEW
) -> GraphContext:
```

These are passed through to `GraphTracer.setup()`. In direct mode, callers omit them (defaults apply). In Temporal mode, `WfPipeRouter` provides them.

### How pipe_abstract.py changes

**It doesn't.** The existing code continues to call `GraphTracerManager.get_instance()`, which routes to the `GraphTracer` for the current `graph_id`. The `GraphTracer` internally decides whether to emit events based on `_event_log`. Call sites are completely unaware of event emission.

### Reporting integration (usage events from activities)

Usage events (`UsageReportEvent`) are emitted from inference workers (e.g., `llm_worker_abstract.py:334`), which run as Temporal **activities**, not inside the workflow. Activities run on specific worker processes and do NOT share the workflow's async context or ContextVars.

**Approach for local filesystem**: Activities receive the event_log config (`traces_dir`, `pipeline_run_id`) as part of their input. Each activity creates its own `NdjsonEventLog` instance and emits `UsageReportEvent` to its own file (keyed by a unique activity identifier, e.g., `act_{activity_id}.ndjson`). The assembler reads all `*.ndjson` files in the pipeline run directory, including activity files.

**Changes to ReportingManager**: Add an optional `event_log` field. When set, `report_inference_job()` emits a `UsageReportEvent` in addition to the existing local accumulation. For activities, the `event_log` is set from the activity input config.

### Files to modify

| File | Change |
|---|---|
| `pipelex/graph/graph_tracer.py` | Add `_event_log`, `_workflow_id` fields; emit events in all tracing methods |
| `pipelex/graph/graph_tracer_manager.py` | Add `event_log`, `workflow_id` params to `open_tracer()` |
| `pipelex/reporting/reporting_manager.py` | Add optional `event_log` field, emit `UsageReportEvent` in `report_inference_job()` |

**What does NOT change**:
- `pipelex/core/pipes/pipe_abstract.py` — zero changes
- `pipelex/pipe_controllers/parallel/pipe_parallel.py` — zero changes
- `pipelex/pipe_controllers/batch/pipe_batch.py` — zero changes
- `pipelex/hub.py` — no new ContextVars needed

### Checklist

- [ ] Add `_event_log` and `_workflow_id` fields to `GraphTracer`
- [ ] Update `GraphTracer.setup()` to accept `event_log` and `workflow_id` params
- [ ] Add event emission to `on_pipe_start()` (PipeStartEvent + EdgeEvent for CONTAINS)
- [ ] Add event emission to `on_pipe_end_success()` (PipeEndSuccessEvent)
- [ ] Add event emission to `on_pipe_end_error()` (PipeEndErrorEvent)
- [ ] Add event emission to `add_edge()` (EdgeEvent)
- [ ] Add event emission to `register_controller_output()` (ControllerOutputEvent)
- [ ] Add event emission to `register_batch_item_extraction()` (BatchItemEvent)
- [ ] Add event emission to `register_batch_aggregation()` (BatchAggregateEvent)
- [ ] Add event emission to `register_parallel_combine()` (ParallelCombineEvent with snapshotted producers)
- [ ] Update node ID generation when `_workflow_id != "direct"` to include workflow_id segment
- [ ] Update edge ID generation similarly
- [ ] Update `GraphTracerManager.open_tracer()` to accept and pass through `event_log`, `workflow_id`
- [ ] Add optional `event_log` to `ReportingManager`, emit `UsageReportEvent` in `report_inference_job()`
- [ ] Test: GraphTracer with event_log emits correct events for a pipe start/end cycle
- [ ] Test: CONTAINS edge event emitted when parent_node_id is present
- [ ] Test: GraphTracer without event_log (direct mode) works exactly as before
- [ ] Test: controller output registration emits `ControllerOutputEvent`
- [ ] Test: parallel combine emits `ParallelCombineEvent` with correct snapshotted producer IDs
- [ ] Test: ReportingManager emits `UsageReportEvent` when event_log is set
- [ ] `make agent-check` passes

---

## Step 4: Wire into Pipeline Lifecycle

> Connect event log initialization/finalization to the pipeline run lifecycle and Temporal workflow lifecycle.

### What

The event log must be created at the start of a Temporal pipeline run and read/assembled at the end. In direct mode, nothing changes — `GraphTracer` works without an event log as before.

### Direct mode flow — UNCHANGED

**No event log is initialized in direct mode.** The existing code path is preserved exactly:
- `pipeline_run_setup.py` calls `GraphTracerManager.open_tracer()` as today (no `event_log` param → defaults to None)
- `pipe_abstract.py` calls `GraphTracerManager.get_instance()` as today
- `runner.py` calls `GraphTracerManager.close_tracer()` in the `finally` block as today
- `ReportingManager` accumulates in memory as today (no `event_log` set → no emission)

All existing tests pass without modification because the direct mode code path is identical.

### Temporal mode flow

**API process** (`pipeline_run_setup.py`):
- When Temporal mode + graph enabled: create `NdjsonEventLog(traces_dir=tracing_config.traces_dir)`
- Pass to `GraphTracerManager.open_tracer(event_log=event_log, workflow_id=...)`
- The API process itself doesn't need the event_log on a ContextVar — it doesn't execute pipes

**Worker process** (`WfPipeRouter.run()`):
- Create `NdjsonEventLog` from tracing config (read from `pipelex.toml`, same pattern as other config)
- Call `GraphTracerManager.get_or_create_instance()` then `open_tracer(event_log=event_log, workflow_id=workflow.info().workflow_id)`
- Pipe execution proceeds as normal — `GraphTracer` dual-writes (in-memory + events)
- No assembly on the worker — that's the API process's job

**Assembly** (`runner.py` finally block):
- After the Temporal workflow completes (or fails), the runner reads events and assembles:

```python
# runner.py finally block
if graph_tracer_manager is not None:
    graph_spec_result = graph_tracer_manager.close_tracer(pipeline_run_id)

if is_temporal_mode and event_log is not None:
    try:
        events = event_log.read_events(pipeline_run_id)
        graph_spec_result = GraphSpecAssembler.assemble(events)
        usage_data = UsageAggregator.aggregate(events)
    except Exception as exc:
        log.error(f"Failed to assemble graph from events: {exc}")
        # graph_spec_result stays as whatever close_tracer returned (local worker graph, or None)
```

**Key**: Both API and workers point to the same `traces_dir`. For local dev (same machine), this is a local filesystem path. For cloud, this would be replaced by DynamoDB (different backend, same protocol).

### How `WfPipeRouter.run()` changes

Current code opens a per-workflow library. Add event log setup in the same block:

```python
# After library crate setup, before pipe execution:
if workflow_arg.job_metadata.graph_context is not None:
    try:
        event_log = NdjsonEventLog(traces_dir=tracing_config.traces_dir)
        graph_tracer_manager = GraphTracerManager.get_or_create_instance()
        graph_tracer_manager.open_tracer(
            graph_id=workflow_arg.job_metadata.graph_context.graph_id,
            data_inclusion=...,
            event_log=event_log,
            workflow_id=workflow.info().workflow_id,
        )
    except Exception as exc:
        log.warning(f"Failed to initialize event log tracing: {exc}")
        # Continue without event emission — tracing is a diagnostic tool,
        # it should not crash the workflow
```

**Important**: This must happen before `pipe.run_pipe()` but within the `workflow.unsafe.imports_passed_through()` block. Library setup must complete first (to have config available), then event log setup. The event log writes are side effects that happen during execution — Temporal replay will re-execute them, but the deduplication in `read_events()` handles this.

### Usage events from activities

Activities receive event_log config (`traces_dir`, `pipeline_run_id`) as part of their input (e.g., in `JobMetadata` or a dedicated config field). Each activity:
1. Creates its own `NdjsonEventLog` instance
2. Emits `UsageReportEvent` to its own file (e.g., `act_{activity_id}.ndjson`)
3. The assembler reads all `*.ndjson` files in the pipeline run directory

### Tracing config propagation

Workers read `traces_dir` from `pipelex.toml` config (already loaded at worker startup). Same pattern as other config. The `pipeline_run_id` comes from `JobMetadata` (already available).

### Graph output generation

After assembly, the existing graph output pipeline (`graph_factory.py`, `generate_graph_outputs()`) works unchanged — it takes a `GraphSpec` and produces Mermaid/ReactFlow files. Renderers that parse node IDs must be updated to handle the `{graph_id}:{workflow_id}:node_{seq}` format (additional colon-separated segment).

### Traces are never auto-deleted

Traces persist on disk until explicitly removed by the user or a cleanup command. This ensures:
- Traces are available for debugging if assembly fails
- Usage reporting can run after graph generation (both read from the same event files)
- No risk of deleting the only durable source of cross-worker data

### Files to modify

| File | Change |
|---|---|
| `pipelex/temporal/tprl_pipe/wf_pipe_router.py` | Create NdjsonEventLog, call `open_tracer(event_log=..., workflow_id=...)` |
| `pipelex/pipeline/runner.py` | After Temporal workflow completes/fails: read events, assemble, defensive try/except |
| `pipelex/pipeline/pipeline_run_setup.py` | Create NdjsonEventLog when Temporal mode + graph enabled, pass to `open_tracer()` |
| `pipelex/system/configuration/configs.py` | Add `TracingConfig` with `traces_dir`, `enabled` |
| `pipelex/pipelex.toml` | Add `[pipelex.tracing]` section |
| Mermaid/ReactFlow renderers | Handle `{graph_id}:{workflow_id}:node_{seq}` node ID format |

### Checklist

- [ ] Define `TracingConfig` and wire into main config
- [ ] Add `[pipelex.tracing]` to `pipelex.toml`
- [ ] Create NdjsonEventLog in `pipeline_run_setup.py` when Temporal mode + graph enabled
- [ ] Pass `event_log` and `workflow_id` to `GraphTracerManager.open_tracer()` in `pipeline_run_setup.py`
- [ ] Create NdjsonEventLog in `WfPipeRouter.run()`, call `open_tracer()` with event_log + workflow_id
- [ ] Defensive try/except around event log init in `WfPipeRouter` — continue without tracing on failure
- [ ] Read events + assemble GraphSpec in `runner.py` after Temporal workflow completes (or fails)
- [ ] Defensive try/except around assembly in `runner.py` — don't mask pipeline errors
- [ ] Feed assembled GraphSpec into existing graph output generation (`generate_graph_outputs()`)
- [ ] Read events + aggregate usage via `UsageAggregator`
- [ ] Wire activity-level usage event emission (pass event_log config to activities)
- [ ] Update Mermaid/ReactFlow renderers to handle new node ID format
- [ ] Verify direct mode is completely unchanged — no event log initialized, `GraphTracer` works as today
- [ ] Test (Temporal): `pipelex run pipe --graph` with Temporal produces correct GraphSpec via event log
- [ ] Test: usage report generated correctly from events across workers
- [ ] Test: assembly failure is caught and logged, does not mask pipeline result
- [ ] Test: event log init failure in WfPipeRouter does not crash the workflow
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
| Usage reporting | Token costs aggregated across workers (via activity-emitted events) |
| Two-pass assembly ordering | Producer in alphabetically-later workflow, consumer in earlier one — validates the assembler doesn't depend on event file ordering |
| Dry-run with graph | Same structure but with StuffArtefact (if fixed) or xfail |

### Reuse existing test infrastructure

The `tests/integration/pipelex/temporal/library_crate/` directory already has `.mthds` bundles and test infrastructure for Temporal integration tests. Extend with graph tracing assertions.

### Checklist

- [ ] Test: PipeSequence through Temporal produces correct GraphSpec (nodes, CONTAINS, DATA edges)
- [ ] Test: PipeParallel through Temporal produces correct PARALLEL_COMBINE edges
- [ ] Test: events from multiple workers are in separate NDJSON files
- [ ] Test: deduplication handles Temporal replay (emit same events twice, assembler produces correct graph)
- [ ] Test: pipeline failure produces partial graph with FAILED/CANCELED nodes
- [ ] Test: usage reporting works across Temporal workers (activity-emitted events)
- [ ] Test: usage aggregation matches expected token counts
- [ ] Test: graph output files (Mermaid, ReactFlow) generated correctly from assembled GraphSpec
- [ ] Test: two-pass assembly handles cross-workflow producer/consumer in arbitrary workflow_id order
- [ ] Test: event log init failure in WfPipeRouter does not crash the workflow
- [ ] Test: assembly failure in runner.py is caught and logged
- [ ] `make agent-check` passes
- [ ] `make agent-test` passes

---

## Non-Goals (Deferred)

These are explicitly out of scope for this plan. They're documented in [wip/distributed-tracing-and-reporting.md](wip/distributed-tracing-and-reporting.md).

| Item | Why deferred |
|---|---|
| DynamoDB backend | Cloud-only — implement when deploying to AWS with remote workers. The `EventLogProtocol` abstraction allows swapping the backend without changing the rest of the system. |
| Real-time progress consumer | No consumer exists yet — the protocol supports it, build when needed |
| `subscribe()` on EventLogProtocol | Polling-based reads are sufficient for now; add when real-time consumer exists |
| Large data externalization | Inline data in events for now; add StorageProvider offloading when traces grow too large |
| TraceSinkProtocol abstraction | The EventLogProtocol is sufficient; the higher-level sink abstraction can wait for the cloud backend |
| Unified code path (event log everywhere) | Direct mode uses in-memory GraphTracer only; event log is Temporal-only. Two code paths for now. Unify if the assembler proves reliable and the dual-path maintenance cost becomes painful. |
| PipeCondition SELECTED_OUTCOME wiring | PipeCondition has no tracer calls in production code currently. If SELECTED_OUTCOME edges are needed, that's a separate change. |
| Auto-cleanup of traces | Traces persist on disk until manually deleted. Safer for debugging and allows usage reporting to run after graph generation. |
| SQLite backend | NDJSON is simpler and sufficient for local dev. SQLite could replace it if deduplication at write time or queryability becomes important. |
