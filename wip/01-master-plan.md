# Master Plan v2 — Next Phases

> **Status**: Not started
> **Date**: 2026-03-31
> **Predecessor**: [00-master-plan.md](00-master-plan.md) (Phases 0–5, LibraryCrate & Distributed Execution)

---

## Phase 4.5 Step 6: Standalone Activity Tracing

> Wire event log into activities that may run on separate processes (standalone activities).

**Goal**: Wire event log into standalone activities via Temporal interceptor, `TracingContext` on `JobMetadata`, activity-level `UsageReportEvent` emission.

### What

Currently, usage event emission from activities relies on the `ReportingManager` singleton being configured with `set_event_log()` by `WfPipeRouter.run()` on the same process. This breaks when activities run on standalone workers (separate processes) via Temporal's [standalone activities](https://docs.temporal.io/develop/python/standalone-activities) feature: the standalone process has its own `ReportingManager` with no `event_log` set.

### Approach: Temporal Activity Interceptor

Use Temporal's built-in [activity interceptor](https://docs.temporal.io/develop/python/observability#activity-interceptors) API to inject event log setup/teardown around activity execution, without modifying individual activity functions.

**1. Add `TracingContext` to `JobMetadata`:**

```python
class TracingContext(BaseModel):
    traces_dir: str
    pipeline_run_id: str
    workflow_id: str
```

Optional field on `JobMetadata`. Populated by `WfPipeRouter` (or the dispatching workflow) before calling `workflow.start_activity()`. `None` when tracing is disabled.

**2. Implement `TracingActivityInboundInterceptor`:**

```python
class TracingActivityInboundInterceptor(ActivityInboundInterceptor):
    async def execute_activity(self, input: ExecuteActivityInput) -> Any:
        tracing_ctx = _extract_tracing_context(input.args)
        if tracing_ctx is not None:
            event_log = NdjsonEventLog(traces_dir=tracing_ctx.traces_dir)
            report_delegate = get_report_delegate()
            if isinstance(report_delegate, ReportingManager):
                report_delegate.set_event_log(
                    event_log=event_log,
                    workflow_id=tracing_ctx.workflow_id,
                    pipeline_run_id=tracing_ctx.pipeline_run_id,
                )
        try:
            return await super().execute_activity(input)
        finally:
            if tracing_ctx is not None and event_log is not None:
                event_log.close()
```

The `_extract_tracing_context()` helper navigates the activity input to find `JobMetadata.tracing_context`. All activity inputs contain `JobMetadata` either directly or via `LLMAssignment.job_metadata`, `ImgGenAssignment.job_metadata`, etc.

**3. Register on Worker:**

```python
Worker(
    client=client,
    interceptors=[TracingInterceptor()],
    ...
)
```

Same pattern as OpenTelemetry instrumentation for Temporal.

**4. NDJSON file naming for activities:**

Activity events go to `act_{activity_task_id}.ndjson`. The `read_events()` glob already matches `*.ndjson`, so no backend changes needed.

### Why the interceptor approach

- No changes to individual activity functions (`act_llm_gen_text`, `act_llm_gen_object`, etc.)
- Same mechanism Temporal uses for OTel tracing — proven pattern
- Clean setup/teardown lifecycle

### Files to create/modify

| File | Change |
|---|---|
| `pipelex/pipeline/job_metadata.py` | Add `TracingContext` model and optional field on `JobMetadata` |
| `pipelex/temporal/tprl/tracing_interceptor.py` | New: `TracingActivityInboundInterceptor` |
| `pipelex/temporal/tprl_pipe/wf_pipe_router.py` | Populate `TracingContext` on `JobMetadata` before pipe execution |
| Temporal worker setup | Register the interceptor on the `Worker` |

### Done when

- [ ] Define `TracingContext` model on `JobMetadata`
- [ ] Populate `TracingContext` in `WfPipeRouter.run()` when tracing is enabled
- [ ] Implement `TracingActivityInboundInterceptor` with event log setup/teardown
- [ ] Helper to extract `TracingContext` from activity input (navigate `JobMetadata` from various assignment types)
- [ ] Register interceptor on Temporal Worker
- [ ] NDJSON file naming: use `act_{activity_task_id}.ndjson` for activity-emitted events
- [ ] Test: standalone activity emits `UsageReportEvent` to its own NDJSON file
- [ ] Test: assembled usage from activity events matches expected token counts
- [ ] Test: interceptor gracefully handles missing `TracingContext` (no-op)
- [ ] `make agent-check` passes
- [ ] `make agent-test` passes

---

## Phase 6: Cross-Package Dependencies in Crate

> **Status**: Not started

**Goal**: Include cross-package dependency content in the LibraryCrate so that Temporal workers can execute pipelines that reference concepts and pipes from other packages — without those packages being installed on the worker. Then extend to remote dependencies fetched from GitHub.

See [future-crate-first-architecture.md](future-crate-first-architecture.md) for the full crate-first architectural vision and design rationale.

### Why

Today, cross-package dependencies (`alias->domain.ConceptCode`, `alias::domain.pipe_code`) resolve through child library lookups at loading time. The `LibraryCrate` shipped to Temporal workers does NOT include dependency content — only the main package's blueprints. This means workers must have all dependency packages pre-installed on PIPELEXPATH. Phase 6 removes this requirement: the crate becomes truly self-contained.

### Phase 6a: Local Cross-Package Dependencies

**Goal**: Dependency blueprints are included in the crate. Workers can execute pipelines with cross-package deps without having the dependency packages installed.

**Key changes**:

1. **Extract blueprint collector from `_load_single_dependency`**: Split the current method into two parts:
   - **Collect**: resolve the dependency, parse its `.mthds` files into blueprints, determine exports
   - **Load**: create child Library, load domains/concepts/pipes, register aliases
   The collector produces blueprints that accumulate into `_blueprints[library_id]` alongside the main package's blueprints.

2. **Resolve cross-package aliases in the flattened crate**: Cross-package refs use alias-based syntax (`alias->domain.ConceptCode`). In a flattened crate, there are no child libraries. Options:
   - Resolve aliases during crate building (replace `alias->domain.ConceptCode` with `domain.ConceptCode` in all blueprints)
   - Carry alias mappings in the crate (`aliases: dict[str, str]`) for runtime resolution
   Decision TBD when starting implementation.

3. **Update `load_from_crate()`**: Handle dependency content in the flat crate — register domains, concepts, and pipes from deps.

**Done when**:

- [ ] `_load_single_dependency` split into collect + load
- [ ] Dependency blueprints accumulate into `_blueprints[library_id]`
- [ ] `get_crate()` produces a crate that includes dependency content
- [ ] Cross-package aliases resolved (either at crate build time or via alias map)
- [ ] `load_from_crate()` handles dependency content correctly
- [ ] Integration test: PipeSequence referencing a cross-package concept/pipe, executed on Temporal worker without the dependency package on PIPELEXPATH
- [ ] `make agent-check` passes
- [ ] `make agent-test` passes

### Phase 6b: Remote Dependencies (GitHub)

**Goal**: Dependencies can be fetched from remote addresses (e.g., `github.com/org/repo/package`). The crate becomes fully self-contained for cloud-native execution where workers are stateless.

**Key changes**:

1. **Remote resolution strategy**: Add a `REMOTE` resolution strategy to the blueprint collector extracted in 6a. Remote fetch clones/downloads the package from GitHub, parses its `.mthds` files into blueprints, and includes them in the collection.

2. **Dependency address format**: Define the address format for remote deps (e.g., `github.com/org/repo@version/path/to/package`). The address goes in the package manifest.

3. **Caching**: Cache fetched packages locally (content-addressed by address + version) to avoid redundant clones.

4. **Transitive deps**: Remote packages may themselves have dependencies (local or remote). The collector recurses.

**Done when**:

- [ ] Remote fetch strategy implemented (git clone or archive download)
- [ ] Dependency address format defined and parsed
- [ ] Remote package blueprints included in crate
- [ ] Local cache for fetched packages
- [ ] Transitive remote deps resolved
- [ ] Integration test: pipeline with remote dep from a GitHub repo, executed on Temporal worker
- [ ] `make agent-check` passes
- [ ] `make agent-test` passes

---

**Deferred & future items**: See [deferred-items.md](deferred-items.md) for future architectural vision (crate-first, stripping, fingerprinting, cross-worker cache) and known issues.

---

## Dependencies

```
Phase 4.5 Step 6 (Activity Tracing)    ← requires Phase 4.5's event log infrastructure

Phase 6a (Local cross-package deps)    ← requires Phase 2's crate propagation
    │
    ▼
Phase 6b (Remote deps from GitHub)     ← requires Phase 6a's blueprint collector
```
