# Done: rename `GraphContext` → `TraceContext`

**Status: DONE (Option 1).** Landed on branch `refactor/Renamings` as its own change, separate from #967. As-built:

- `GraphContext` → `TraceContext`; file `pipelex/graph/graph_context.py` → `pipelex/graph/trace_context.py`; attribute `graph_context` → `trace_context` everywhere (incl. `JobMetadata.trace_context`). Class + module docstrings re-document the object as the shared per-execution trace transport with graph and usage as two streams over one node tree.
- Companion gate rename: `PipelineExecutionConfig.is_generate_costs` → `is_generate_usage` (+ key in all three `pipelex.toml` files), and the override param `with_execution_overrides(generate_costs=…)` → `generate_usage=…`, plus the `pipeline_run_setup.py` / `runner.py` reads. The **cost-domain renderer stays cost-named**: `render_run_cost_report(is_generate_costs=…)` and `cost_report_renderer.py` are untouched — the seam is `render_run_cost_report(is_generate_costs=execution_config.is_generate_usage)` ("if usage was generated, render the cost view"). The public `--costs` CLI flag is unchanged; it maps to `generate_usage=costs`.
- **Deferred (NOT done this pass):** the optional `graph_id` → `run_id` nit. It ripples into the deliberately graph-named `GraphTracerManager.open_tracer(graph_id=…)` plumbing and the `make_node_id` format; left for a focused follow-up. The `GraphTracer` / `GraphTracerManager` / `GraphTracerProtocol` family stays graph-named (they own the graph stream).
- Published doc `docs/under-the-hood/execution-graph-tracing.md` updated to the new identifiers. `make agent-check`, `make tb`, and the suite are green.

Original decision record (preserved below).

A companion rename rides along in the same pass: align the internal usage-gate flag to the layer it gates (`is_generate_costs` → `is_generate_usage`). See "Companion rename" below.

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

## Companion rename: align the gate flag to the layer it gates

Same species of smell as the `GraphContext` one, surfaced while reviewing the flag layer: a flag named for the downstream *deliverable* (cost) controls the upstream *measurement* stream (usage). The event/data layer already committed to "usage" everywhere — `emit_usage_events`, `UsageReportEvent`, `TokensUsage` / `LLMTokensUsage` / `AnyTokensUsage`, the `cogt/usage/` package. The gate flag never followed: `is_generate_costs` feeds straight into `emit_usage_events`. A "costs" switch turning on "usage" emission is the drift.

**The narrow, genuinely-correct fix.** Rename the internal gate to match the stream it gates:

- `PipelineExecutionConfig.is_generate_costs` → `is_generate_usage` (and the matching key in `pipelex/pipelex.toml`).
- `PipelineExecutionConfig.with_execution_overrides(generate_costs=...)` → `generate_usage=...`.
- The local `is_generate_costs` in `pipeline_run_setup.py` and the `execution_config.is_generate_costs` reads in `pipeline_run_setup.py` / `runner.py`.

After the rename the gating reads cleanly at every layer: `is_generate_usage` → `emit_usage_events` (usage gates usage), and the cost report is correctly a *view* gated on usage being present ("if we generated usage, render the cost view") rather than a same-named thing gating itself.

**Leave alone — deliberately:**

- **The public `--costs` / `--no-costs` CLI flag.** It is a public surface, and from the user's seat "costs" is the deliverable they asked for (the run emits a cost report: console log + `cost_report` in JSON + CSV). At the CLI boundary the `--costs` value simply maps to the renamed internal `generate_usage` override param. Renaming the public flag to `--usage` is a *capability* question, not a naming one — tracked separately in [`usage-reporting-without-cost.md`](usage-reporting-without-cost.md).
- **The whole cost-computation / reporting cluster.** `CostRegistry`, `TokenCostReport`, `CostCategory`, `costs_per_token.py`, `cost_report_renderer.py`, and the `ReportingConfig` fields (`is_log_costs_to_console`, `cost_report_dir_path`, `cost_report_unit_scale`, …) genuinely compute money. They are correctly named; renaming them to "usage" would both lie about what they do and collide with the existing `TokensUsage` vocabulary. A *partial* rename (flag → usage, report stays cost) would create a new, worse mismatch than today's — so the rule is: align the gate, leave the cost domain.

This rides along with the `GraphContext` → `TraceContext` pass because it is the same kind of cleanup and touches the same files (`pipeline_run_setup.py`, `runner.py`, `configs.py`, plus `pipelex.toml`). Pure mechanical rename, no behavior change.

## Scope / blast radius when executing

- Rename the `GraphContext` type (referenced across roughly a dozen modules) and the `graph_context` attribute (used throughout pipe execution, including the `JobMetadata.graph_context` field). Broad but mechanical.
- Companion flag rename: `is_generate_costs` → `is_generate_usage` (`configs.py` + `pipelex.toml`), the `generate_costs` override param → `generate_usage`, and the reads in `pipeline_run_setup.py` / `runner.py`. Narrow; the public `--costs` CLI flag and the cost-computation/reporting cluster stay as-is (see "Companion rename" above). Run `make tb` after touching the config to confirm the boot/config-load still passes.
- Optional same-pass nit: `graph_id → run_id`.
- Wire format is a non-issue: the object serializes across the Temporal boundary, but Temporal is not shipped to prod, so there is no version-skew concern. See [[project_temporal_not_shipped]].
- This is a design-tradeoff cleanup, not a bug fix — land it as its own change, not folded into #967.

## Provenance

Surfaced during PR #967 review (the fast-path best-effort emit fix in `reporting_manager.py`), when the reviewer's comment exposed that the registered-context emit path — backed in direct mode by the same DynamoDB event log the graph stream uses — was carrying usage events through a "Graph"-named context.
