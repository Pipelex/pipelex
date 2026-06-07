# Deferred: rename `GraphContext` → `TraceContext`

**Status: DECIDED, DEFERRED.** Direction approved (Option 1 below). Not done in this PR — capture-only, to land as its own clean rename change.

## The problem

`GraphContext` (`pipelex/graph/graph_context.py`) was born graph-only — its docstring still opens with *"This context enables building a GraphSpec"*. The distributed cost-reporting work (this `wip/registry/` track) added usage/cost reporting as a *second* event stream over the same object: the reporting manager reads `emit_usage_events`, `lookup_key`, `tracer_key`, `graph_id`, and `parent_node_id` off it (`pipelex/reporting/reporting_manager.py`). The name now under-describes the object — a cost concern rides on something called "Graph".

## The correction to the framing

Usage is **not** a free-rider on an unrelated struct. `UsageReportEvent.node_id` (`pipelex/tracing/trace_events.py`) is stamped from `graph_context.parent_node_id` — cost is **attributed to a node in the execution tree**. Graph events and cost events are two *projections of one substrate*: the per-execution node tree. So the right move is not to pull usage away from the graph; it is to recognize the object as the shared **trace context**, of which "graph" and "cost" are two consumers.

## Field taxonomy

Shared per-execution trace identity (both consumers):

- `graph_id` — really the run id (typically `pipeline_run_id`); the name is a secondary misnomer.
- `tracer_key` / `lookup_key` — registry plumbing.
- `parent_node_id` — the node anchor; read by graph (edges) and cost (attribution), written by graph traversal.
- `emit_graph_events` / `emit_usage_events` — stream-emit policy. `emit_usage_events` is the one genuinely-misplaced field (a usage toggle on a "Graph" object).

Graph-construction mechanics (graph only):

- `node_sequence`, `make_node_id()`, `copy_for_child()` — node-id minting and tree traversal.
- `data_inclusion` — controls which node-IO data formats are captured.

## The constraint that bounds how much a split buys

The node tree is **always built**, even in `--no-graph --costs` mode: per D5 (`pipelex/pipeline/pipeline_run_setup.py`), costs-only mode hands the tracer `event_log=None` but it still mints node ids and accumulates the in-memory tree, precisely so usage can attribute to `parent_node_id`. There is therefore **no runtime configuration with a "trace context but no graph."** The graph substrate is mandatory. A type split could not drop any graph machinery for cost-only runs — it would only narrow what the reporting boundary is allowed to *see*.

## Options considered

**Option 1 — rename, keep one type (CHOSEN).** `GraphContext` → `TraceContext` (or `ExecutionTraceContext`). Re-document graph and cost as two streams over one transport hung off the shared node tree. Node-minting methods stay because the tree is the shared substrate. Fold the `graph_id → run_id` rename into the same pass. One mechanical change, no behavior change, kills the "usage on a Graph object" smell.

**Option 2 — layered split (`TraceContext` base + `GraphContext(TraceContext)`) — ON THE SHELF.** Base = run id + `parent_node_id` + stream toggles + registry key; subclass adds the node-minting/`data_inclusion` mechanics; reporting types its params as the base. More "correct" on paper, but because of the constraint above the runtime object is always the full subclass — the only gain is intent-revealing parameter types at the reporting seam. Revisit only if reporting grows more graph-independent consumers.

**Option 3 — extract the toggles into an `EmitPolicy` / `TraceStreams` value object — ON THE SHELF.** Smallest fix for the one truly-misplaced field. Two bools likely don't earn their own type yet; keep in mind if a third stream appears.

Do **not** touch `UsageReportEvent.node_id` — cost-per-node is a deliberate feature, and that coupling to the tree is correct.

## Scope / blast radius when executing

- Rename the `GraphContext` type (referenced across roughly a dozen modules) and the `graph_context` attribute (used throughout pipe execution, including the `JobMetadata.graph_context` field). Broad but mechanical.
- Optional same-pass nit: `graph_id → run_id`.
- Wire format is a non-issue: the object serializes across the Temporal boundary, but Temporal is not shipped to prod, so there is no version-skew concern. See [[project_temporal_not_shipped]].
- This is a design-tradeoff cleanup, not a bug fix — land it as its own change, not folded into #967.

## Provenance

Surfaced during PR #967 review (the fast-path best-effort emit fix in `reporting_manager.py`), when the reviewer's comment exposed that the registered-context emit path — backed in direct mode by the same DynamoDB event log the graph stream uses — was carrying usage events through a "Graph"-named context.
