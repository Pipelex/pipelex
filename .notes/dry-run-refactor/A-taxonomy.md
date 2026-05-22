# Runtime Classes Taxonomy: PipeRouter, PipeRun, and Temporal Variants

## Section 1: Four Classes Side by Side

### PipeRouter (`pipelex/pipe_run/pipe_router.py:9`)
**What it does:** Direct-execution router; calls `pipe.run_pipe()` inline (with all modes—LIVE and DRY—baked into the pipe's logic).

**Public interface:**
```python
async def _run_pipe_job(self, pipe_job: PipeJob) -> PipeOutput
async def run(self, pipe_job: PipeJob) -> PipeOutput  # inherited from protocol
```

**Execution:** Calls `pipe.run_pipe()` at line 18, passing `pipe_job` and delegating to the pipe's implementation. No redirection; the pipe itself interprets `pipe_run_params.run_mode`.

---

### PipeRun (`pipelex/pipe_run/pipe_run.py:21`)
**What it does:** Orchestrator for direct execution; wraps `PipeRouter.run()` with delivery, graph assembly, and error handling.

**Public interface:**
```python
async def run(self, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None = None) -> PipeOutput
```

**Execution:** At line 40, calls `self._pipe_router.run(pipe_job)`, then executes delivery at line 71 if assignment is provided. Centralizes tracing cleanup (lines 47–58) and graph assembly (line 61).

---

### WfPipeRouter (`pipelex/temporal/tprl_pipe/wf_pipe_router.py:26`)
**What it does:** Temporal workflow that executes the pipe; dispatched as a child workflow by `TemporalPipeRouter`. Handles per-workflow library setup, tracing, and event flushing.

**Public interface:**
```python
@workflow.run
async def run(self, workflow_arg: PipeJob) -> PipeOutput
```

**Execution:** At line 126, calls `pipe.run_pipe()` directly (same as `PipeRouter`). All the heavyweight setup (library hydration, tracing manager, event buffering) wraps it, then the workflow dehydrates the output for transit (line 180).

---

### WfPipeRun (`pipelex/temporal/tprl_pipe/wf_pipe_run.py:22`)
**What it does:** Parent workflow orchestrating pipe execution + delivery; runs `WfPipeRouter` as a child, then runs delivery as an activity. Failure-safe: delivery fires even if pipe fails.

**Public interface:**
```python
@workflow.run
async def run(self, workflow_arg: PipeRunArg) -> PipeOutput
```

**Execution:** At line 53, executes `WfPipeRouter.run()` as a child workflow; at line 83, runs graph assembly as an activity; at line 116, runs delivery as an activity. Preserves original error for correct failure attribution (line 132).

---

### DryPipeRouter (`pipelex/pipe_run/dry_pipe_router.py:9`)
**What it does:** Dead code; calls `pipe.dry_run_pipe()` at line 18. No production usage.

**Public interface:**
```python
async def _run_pipe_job(self, pipe_job: PipeJob) -> PipeOutput
```

---

### Protocols

**`PipeRouterProtocol` (`pipelex/pipe_run/pipe_router_protocol.py:11`):**
```python
observer: ObserverProtocol
async def run(self, pipe_job: PipeJob) -> PipeOutput
async def _run_pipe_job(self, pipe_job: PipeJob) -> PipeOutput  # abstract
```

Implemented by `PipeRouter`, `DryPipeRouter`, and `TemporalPipeRouter`.

**`PipeRunProtocol` (`pipelex/pipe_run/pipe_run_protocol.py:12`):**
```python
async def run(
    self,
    pipe_job: PipeJob,
    delivery_assignment: DeliveryAssignment | None = None,
) -> PipeOutput
```

Implemented by `PipeRun` and `TemporalPipeRun`.

---

## Section 2: Call Chains

### Local (Direct) Mode

```
PipelexRunner.execute_pipeline()
  → pipeline_run_setup()  [builds PipeJob]
  → effective_pipe_run.run(pipe_job, delivery_assignment)
      [calls get_pipe_run() if not overridden; PipeRun instance]

PipeRun.run() [pipelex/pipe_run/pipe_run.py:29–91]
  → self._pipe_router.run(pipe_job)  [line 40]
  
    PipeRouter.run() [from PipeRouterProtocol.run]
      → self._before_run(pipe_job)  [observer hook, line 52]
      → self._run_pipe_job(pipe_job)  [line 55]
      
        PipeRouter._run_pipe_job() [pipelex/pipe_run/pipe_router.py:14–24]
          → pipe_job.pipe.run_pipe()  [line 18]
          
            PipeAbstract.run_pipe() [pipelex/core/pipes/pipe_abstract.py:409]
              → pipe_run_params.push_pipe_to_stack()  [line 421]
              → self._run_pipe_traced()  [line 423]
              
                PipeAbstract._run_pipe_traced() [pipelex/core/pipes/pipe_abstract.py:434]
                  → validate_before_run()  [line 501]
                  → match pipe_run_params.run_mode:  [line 504]
                      case PipeRunMode.LIVE: live_run_pipe()  [line 506]
                      case PipeRunMode.DRY: dry_run_pipe()   [line 514]
              → pipe_run_params.pop_pipe_from_stack()  [line 431]
      
      → self._after_successful_run()  [observer hook, line 74]
  
  → self._delivery_executor.execute()  [line 71]
  → assemble_graph_on_output()  [line 61]
  → GraphTracerManager.close_tracer()  [line 50]
```

**Key:** The `run_mode` decision point is inside `pipe._run_pipe_traced()` at line 514, not at the router level. `DryPipeRouter` is an **unreachable alternative.**

---

### Temporal Mode

```
PipelexRunner.execute_pipeline()
  → pipeline_run_setup()
  → effective_pipe_run.run(pipe_job, delivery_assignment)
      [calls make_temporal_pipe_run(); TemporalPipeRun instance]

TemporalPipeRun.run() [pipelex/temporal/tprl_pipe/temporal_pipe_run.py:49–81]
  → stamp_submitter_session_id()  [line 57]
  → WorkflowExecutorFactory.create_executor()  [line 64]
  → executor.execute_workflow(workflow_class=WfPipeRun, ...)  [line 69]

    [Temporal server executes WfPipeRun]
    
    WfPipeRun.run() [pipelex/temporal/tprl_pipe/wf_pipe_run.py:31–139]
      → workflow.execute_child_workflow(WfPipeRouter.run, pipe_job)  [line 53]
      
        [Temporal server executes WfPipeRouter]
        
        WfPipeRouter.run() [pipelex/temporal/tprl_pipe/wf_pipe_router.py:29–183]
          [library hydration, tracing setup, per-workflow state initialization]
          → pipe.run_pipe() [line 126]
              [SAME pipe execution logic as local mode; run_mode baked in]
          [event flushing, tracer close]
      
      → workflow.execute_activity(act_assemble_graph)  [line 83]
      → workflow.execute_activity(act_deliver)  [line 116]

  → rehydrate_pipe_output_with_crate()  [line 81]
```

**What swaps:**
- `PipeRun` ↔ `TemporalPipeRun`: delivery orchestration layer (hub selection at line 456–461 in `pipelex.py`)
- `PipeRouter` ↔ `TemporalPipeRouter`: pipe dispatch mechanism (hub selection at line 447–452 in `pipelex.py`)
- **Graph assembly, delivery:** move from direct sync calls → Temporal activities (lines 83, 116 in `WfPipeRun`)
- **Per-workflow tracing:** added inside the workflow (lines 72–123 in `WfPipeRouter`)

**What stays the same:**
- `pipe.run_pipe()` still dispatches to `PipeRunMode.DRY` vs `.LIVE` at the pipe level (no router-level decision)
- `pipe_job` structure and semantics

---

## Section 3: The Hub Swap

### Config Check
`Pipelex.setup()` at `pipelex/pipelex.py:162`, checks temporal enablement at line 189:
```python
# Line 188–192
if temporal_enabled is not None:
    config = get_config()
    updated_temporal = config.temporal.model_copy(update={"is_enabled": temporal_enabled})
    config.temporal = updated_temporal
```

Then at line 428:
```python
if get_config().temporal.is_enabled:
    # [Temporal task manager setup]
```

### Pipe Router Registration
**Lines 443–452** (`pipelex.py`):
```python
# --- Pipe Router -----------------------------------------------------------------------

if pipe_router:
    self.pipelex_hub.set_pipe_router(pipe_router)
elif get_config().temporal.is_enabled:
    from pipelex.temporal.tprl_pipe.temporal_pipe_router import make_temporal_pipe_router  # noqa: PLC0415
    self.pipelex_hub.set_pipe_router(make_temporal_pipe_router())
else:
    self.pipelex_hub.set_pipe_router(PipeRouter(observer=multi_observer))
```

**Injection order:** explicit parameter > temporal enabled > default (direct).

### Pipe Run Registration
**Lines 454–461** (`pipelex.py`):
```python
# --- Pipe Run --------------------------------------------------------------------------

if get_config().temporal.is_enabled:
    from pipelex.temporal.tprl_pipe.temporal_pipe_run import make_temporal_pipe_run  # noqa: PLC0415
    self.pipelex_hub.set_pipe_run(make_temporal_pipe_run())
else:
    self.pipelex_hub.set_pipe_run(PipeRun(pipe_router=self.pipelex_hub.get_required_pipe_router()))
```

**Note:** `PipeRun` takes the already-registered router as a constructor parameter (line 461).

---

## Section 4: DryPipeRouter Verification

### Question
When `PipeRouter.run()` calls `pipe.run_pipe()` with `pipe_run_params.run_mode == PipeRunMode.DRY`, does the pipe execute its dry-run path anyway?

### Answer: YES (Confirmed Dead Code)

The decision happens inside the pipe, not at the router.

**`PipeAbstract._run_pipe_traced()` at `pipelex/core/pipes/pipe_abstract.py:504–520`:**
```python
match pipe_run_params.run_mode:
    case PipeRunMode.LIVE:
        pipe_output = await self.live_run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
            library_crate=library_crate,
        )
    case PipeRunMode.DRY:
        pipe_output = await self.dry_run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
            library_crate=library_crate,
        )
```

**Therefore:**
- `PipeRouter` with `run_mode=DRY` → `pipe.run_pipe()` → `dry_run_pipe()` ✓ Works
- `DryPipeRouter` → `pipe.dry_run_pipe()` → Bypasses the pipe's own mode dispatch

### Usage of DryPipeRouter

Search results for non-test production code:
```
/Users/thomashebrardevotis/dev/pipelex-workspace/pipelex/pipelex/pipe_run/dry_pipe_router.py:class DryPipeRouter(PipeRouterProtocol):
```

**No production instantiation found.** Only appears in its own definition. **Dead code confirmed.**

---

## Section 5: Per-Request Runner Injection

### Can We Inject Per-Request Runners?

Yes. `PipelexRunner` accepts an optional `pipe_run` parameter.

**`PipelexRunner.__init__()` at `pipelex/pipeline/runner.py:53–72`:**
```python
def __init__(
    self,
    library_id: str | None = None,
    library_dirs: list[str] | None = None,
    bundle_uris: list[str] | None = None,
    pipe_run_mode: PipeRunMode | None = None,
    search_domain_codes: list[str] | None = None,
    user_id: str | None = None,
    execution_config: PipelineExecutionConfig | None = None,
    pipe_run: PipeRunProtocol | None = None,  # <-- HERE
):
    # ...
    self._pipe_run = pipe_run
```

**Usage at line 152:**
```python
effective_pipe_run = self._pipe_run or get_pipe_run()
pipe_output = await effective_pipe_run.run(pipe_job, delivery_assignment=delivery_assignment)
```

### Implication
The hub design **is compatible** with per-request injection. A user can:
1. Create a `PipelexRunner` with `pipe_run=direct_runner` while temporal is globally enabled
2. That call uses the injected direct runner, not the temporal one from the hub

**Limitation:** The router is not similarly injectable into `PipelexRunner`. Only the top-level `PipeRun` is. To swap the router per-request, you'd need to either:
- Inject the entire `PipeRun` (which carries a router)
- Or extend `PipelexRunner` to accept `pipe_router` and pass it to `PipeRun` construction

---

## Section 6: Smells and Inconsistencies

1. **Naming asymmetry: `Wf` prefix**
   - `WfPipeRouter` and `WfPipeRun` are Temporal workflows; `TemporalPipeRouter` and `TemporalPipeRun` are submitter-side executors.
   - The naming does not reflect this tier distinction. `Wf*` blurs whether you're looking at a workflow (server-side) or an executor (client-side).
   - **Suggestion:** Rename `WfPipeRouter` → `WorkflowPipeRouter` and `WfPipeRun` → `WorkflowPipeRun` for clarity; or rename the temporal executors to make the distinction explicit.

2. **Protocol enforcement gap**
   - `PipeRouterProtocol` and `PipeRunProtocol` exist but are not enforced as boundaries. Both protocols have implementations in direct and temporal tracks, yet there's no factory abstraction to select between them.
   - Swap logic is hardcoded in `Pipelex.setup()` (lines 447–461) rather than delegated to a factory that respects the protocol.
   - **Suggestion:** Add `RouterFactory` and `RunFactory` protocols that return `PipeRouterProtocol` and `PipeRunProtocol` based on config.

3. **DryPipeRouter is unreachable**
   - Dead code sitting in the codebase; no path calls it.
   - Run mode is a pipe-level concern, not a router-level one.
   - **Suggestion:** Delete it or move the logic into a test-only module.

4. **Library and tracing setup scattered**
   - Library hydration lives in `WfPipeRouter` (lines 51–65).
   - Tracing setup lives in `WfPipeRouter` (lines 72–123).
   - Graph assembly lives in `WfPipeRun` (lines 83–97).
   - These are orthogonal concerns (library, tracing, graph) but their setup/teardown is mixed into the pipe execution workflow.
   - **Suggestion:** Extract library and tracing setup into reusable context managers (e.g., `async with setup_workflow_library()`, `async with setup_workflow_tracing()`).

5. **Observable inconsistency**
   - `PipeRun` receives `self._pipe_router` as a constructor dependency (line 24).
   - `TemporalPipeRun` does not receive a router; it hardcodes `WfPipeRouter` (line 54 in temporal_pipe_run).
   - This breaks symmetry: if you want to swap the router in temporal mode, you can't without rewriting `TemporalPipeRun`.
   - **Suggestion:** `TemporalPipeRun` should accept a workflow class parameter (defaulting to `WfPipeRouter`).

6. **`PipelexRunner` vs. hub coupling**
   - `PipelexRunner` can inject `pipe_run` but not `pipe_router`.
   - The router is chosen at the hub level, not at the runner level.
   - Per-request router swapping (e.g., dry-runs stay local even when temporal is global) requires injecting the entire `PipeRun`, not just the router.
   - **Suggestion:** Add `pipe_router` parameter to `PipelexRunner.__init__()` and construct `PipeRun` locally if either is overridden.

7. **Magic string comparison in delivery**
   - Both `PipeRun` and `WfPipeRun` check `if delivery_assignment is not None` to decide whether to deliver.
   - This is ad-hoc; there's no delivery mode enum (e.g., `DeliveryMode.ENABLED` vs `DeliveryMode.SKIPPED`).
   - **Suggestion:** Add a delivery mode parameter to `PipeRunParams` or `PipeJob` for consistency with `run_mode`.
