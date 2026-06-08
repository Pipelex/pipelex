# Bug: `/validate` dry-run leaks nested controller sub-pipes to Temporal

> ## ✅ RESOLVED (branch `fix/Temporal-dry-run`)
>
> Fixed with the `scoped_pipe_router` approach below — **no** Temporal validation activity or leaf run-mode-mock follow-up was needed. The sweep was always meant to run fully in-process (per `BundleValidator`'s own docstring); the leak was simply that the in-process router was built but never installed as the active `get_pipe_router()` override, so nested controllers fell through to the hub-default Temporal router. The fix mirrors the existing DIRECT-mode precedent in `runtime_bridge/bridge.py::_run_direct`.
>
> **Changed:**
>
> - `pipelex/pipeline/bundle_validator.py` — keep the in-process `PipeRouter` as `self._pipe_router`; wrap the per-pipe sweep loop in `with scoped_pipe_router(self._pipe_router)`.
> - `tests/integration/pipelex/pipeline/test_bundle_validator.py` — regression test `test_standalone_batch_sweep_scopes_in_process_router`: installs a raising hub-default router and asserts a standalone-`PipeBatch` sweep classifies SUCCESS without ever touching it (verified it fails without the scope).
>
> **Verified:** `make agent-check` clean; targeted pipeline/pipe_run/pipes/graph suites + full `make agent-test` green. The two deferred follow-ups (`wip/dry-run-refactor/followup-temporal-validation-activity.md`, `followup-leaf-run-mode-mock.md`) remain validly deferred — distributed-execution evolutions, not prerequisites for this fix.
>
> ### ⚠️ Correction to the "Secondary issue" section below — it was MISDIAGNOSED
>
> The secondary section claims `dry_run_pipeline()` (the best-effort graph step in `validate.py`) has "the same leak." **It does not.** The graph step does a **single** top-level dispatch of the main pipe — no concurrent same-id collision — so under Temporal it dispatches the one workflow to the worker, which (tracing enabled, `backend = "temporal_dynamodb"`) assembles the `GraphSpec` and returns it on `PipeOutput`. That is the intended distributed design: `pipelex-api` runs with `[pipelex.tracing_config] is_enabled = false` (thin submitter, does not trace); the **worker** owns tracing + graph assembly.
>
> An attempt to "fix" this by forcing `dry_run_pipeline` in-process (scoped in-process router + injected `PipeRun`) was **reverted** — it broke graph generation: forced into the API process where tracing is off, `assemble_tracing` early-returns empty → `graph_spec` None → the route logs `"dry-run did not produce a graph (PipelexError)"` and drops the graph. The graph step is left dispatching to Temporal (worker assembles + returns the graph). If a `/validate` graph is wanted **without** a worker, the real lever is enabling tracing in the API (`[pipelex.tracing_config] is_enabled = true` with an in-process backend like `ndjson`), not changing the router — a separate deployment decision, not part of this bug.

**Where the fix belongs:** `pipelex` core (the runtime), **not** `pipelex-api`. Paths below are relative to the `pipelex` repo (locally the editable `_search` worktree on branch `feature/PipeSearch-Temporal`). No change is needed in `pipelex-api`.

## Symptom

With the API running Temporal-enabled (`.pipelex/pipelex_override.toml` → `[temporal] is_enabled = true`, task queue `pipelex_dev`) and a worker up:

- `make bundle-validate BUNDLE=.../fashion_moodboard` → **HTTP 422**
- `make bundle-validate BUNDLE=.../joke_judge` → **OK**
- `make bundle-run BUNDLE=.../fashion_moodboard` (full run) → **OK**
- `pipelex validate bundle .../fashion_moodboard` (CLI) → **OK**

The 422 body:

```
ValidateBundleError (error_domain=input), 422
detail: "Dry run failed with 1 unexpected pipe failure(s):
  'fashion_moodboard.create_moodboards': ... status=DryRunStatus.FAILURE
  error_message=\"Dry run failed for pipe 'fashion_moodboard.create_moodboards':
  Failed to execute workflow WfPipeRouter\""
```

The string **"Failed to execute workflow WfPipeRouter"** (no trailing detail) is produced only at `pipelex/temporal/tprl/workflow_caller.py:136`, the `(WorkflowAlreadyStartedError, RPCError)` branch of `WorkflowExecutor.execute_workflow` — i.e. a **top-level** Temporal workflow dispatch from the submitter side. A dry run should never reach that code.

## Root cause

The `/validate` path runs an **in-process** dry-run sweep, but nested controller sub-pipes leak out to the Temporal router.

Flow: `api/routes/pipelex/validate.py` → `validate_bundle()` (`pipelex/pipeline/validate_bundle.py`) → `BundleValidator.validate_pipes()` (`pipelex/pipeline/bundle_validator.py`).

`BundleValidator` deliberately builds a **local, in-process** execution primitive so the sweep never touches Temporal — its own module docstring says so:

```python
# pipelex/pipeline/bundle_validator.py  (__init__)
self._pipe_run: PipeRunProtocol = PipeRun(pipe_router=PipeRouter(observer=ObserverNoOp()))
```

> "The per-pipe execution primitive is a **locally-constructed** `PipeRun` — explicitly **not** the hub's `get_pipe_run()`, which under a Temporal hub would spawn a workflow per pipe."

**But that local router is only used for the _top-level_ pipe.** Every controller dispatches its nested sub-pipes through the **hub's** `get_pipe_router()`, not the injected router. This is broad — it is **not** specific to `PipeBatch`:

```python
# pipelex/pipe_controllers/batch/pipe_batch.py  (_live_run_controller_pipe)
return await get_pipe_router().run(pipe_job=PipeJobFactory.make_pipe_job(...))

# pipelex/pipe_controllers/sub_pipe.py  (SubPipe.run_pipe — used by EVERY PipeSequence step;
# also the inline `batch_over` path and the PipeCondition path)
pipe_output = await get_pipe_router().run(pipe_job=PipeJobFactory.make_pipe_job(...))
```

`get_pipe_router()` (`pipelex/hub.py`) returns a contextvar override **if one is set**, else the hub default:

```python
def get_pipe_router() -> "PipeRouterProtocol":
    override = _current_pipe_router.get()
    if override is not None:
        return override
    return get_pipelex_hub().get_required_pipe_router()
```

In the Temporal-enabled API process the hub default is the **`TemporalPipeRouter`** (wired in `pipelex/pipelex.py` ~L452). Called from the API process — i.e. **outside** any Temporal workflow (`is_in_temporal_workflow()` is False) — `TemporalPipeRouter._run_pipe_job` (`pipelex/temporal/tprl_pipe/temporal_pipe_router.py`) takes the **top-level dispatch** branch → `executor.execute_workflow(WfPipeRouter, ...)` → fails → "Failed to execute workflow WfPipeRouter". The per-pipe dry run is marked `FAILURE`, `BundleValidator._aggregate` raises `DryRunError`, `validate_bundle` translates it to `ValidateBundleError`, and the global handler renders 422.

`BundleValidator` builds the in-process router but **never installs it as the `scoped_pipe_router(...)` override**, so the nested controllers fall through to the hub default (Temporal).

## FAIL vs. FALSE-PASS — the leak happens always; only some shapes 422

The leak (nested dispatch → `TemporalPipeRouter`) happens for **every** bundle with a controller. Whether the dry run **fails** depends on a Temporal **workflow-id collision**:

- `make_top_workflow_id` (`pipelex/temporal/temporal_manager.py`) is `f"{prefix}{pipeline_run_id}"` — derived from `pipeline_run_id` **alone** (prefix empty in NORMAL mode). The whole sweep shares **one** `dry_run_pipeline_id` (set once in `validate_pipes`, passed as every pipe's `pipeline_run_id`). So **every** top-level Temporal dispatch in a sweep computes the **same** workflow id.
- `WorkflowExecutor.execute_workflow` **waits for completion**, and no `id_reuse_policy` is set → Temporal's default `ALLOW_DUPLICATE` (reuse allowed once the prior run has *closed*). So **serial** dispatches reusing that id are fine; only **concurrent** same-id dispatches collide → `WorkflowAlreadyStartedError` → caught at `workflow_caller.py:136` → `WorkflowExecutionError("Failed to execute workflow WfPipeRouter")`. (`WorkflowExecutionError` is a `PipelexError`, so `_classify_pipe` records it as a dry-run `FAILURE` → 422, not a 500.)

The deciding structural factor is **standalone batch/parallel vs. batch-reached-as-a-sub-pipe**:

- A **standalone top-level `PipeBatch`/`PipeParallel`** that the sweep dry-runs *directly* runs its top level on the local in-process router, but its **fan-out loop executes in the API process** (`_live_run_controller_pipe` → `gather_bounded`) and fires **N concurrent top-level Temporal dispatches** with the same id → collision → **FAILURE**. A mocked "multiple" list yields `nb_stuffs = 3` (`working_memory_factory.py:232`), so N≥2.
- A **batch reached as a sub-pipe** (inline `batch_over` step, or a batch nested under a sequence/parallel) is dispatched as a **single** top-level workflow — the fan-out into branches then happens **inside the worker** as child workflows (legal). Sequence steps run serially, so it's one dispatch at a time → **no concurrent collision** → it **passes** (still round-tripping Temporal, just not colliding).

## Why each observed case behaves as it does

- **`joke_judge` via API:** simple pipe, no nested controller dispatch → never calls `get_pipe_router()` → stays in-process. ✅ (genuinely correct)
- **`fashion_moodboard` via API → 422:** `create_moodboards` is a **standalone `PipeBatch`** (`inputs = { inspirations = "FashionInspiration[]" }`). Swept directly → fan-out of 3 mock items → 3 concurrent same-id top-level dispatches → `WorkflowAlreadyStartedError`. This is also why **only** `create_moodboards` was reported failing and **not** `create_collection_moodboards` (the sequence that has it as a step): as a step the batch is one top-level dispatch (no collision); only the standalone direct sweep fans out concurrently in-process. ❌
- **`cv_batch_screening` via API → passes, but FALSE PASS:** no standalone `PipeBatch`; its only batch is the inline `batch_over` on the `process_cv` step (`main_pipe` is a `PipeSequence`). Every batch is reached as a sub-pipe → single top-level dispatch, serial → no collision. It still **round-trips nested pipes through Temporal** for a "no-inference, no-cost" dry run, and would 422 if the worker were down (→ `RPCError`, same `except` branch) or if any standalone batch/parallel were ever swept. ⚠️
- **`fashion_moodboard` full run (`make bundle-run`):** goes through Temporal on purpose; the top level runs as a workflow on the worker, where `is_in_temporal_workflow()` is True → controllers do **child-workflow** dispatch (legal). ✅
- **CLI `pipelex validate bundle`:** Temporal disabled → hub default router *is* the in-process `PipeRouter`. ✅

The `scoped_pipe_router` fix below removes the Temporal round-trip for the whole sweep, fixing both the real `create_moodboards`-style failure **and** the silent false-pass leak.

## The fix (mirror an existing, already-correct pattern)

The codebase already solved this exact leak for DIRECT mode in `pipelex/runtime_bridge/bridge.py::_run_direct`, with a comment describing the precise failure mode:

```python
# DIRECT mode forces in-process execution even inside a Temporal-enabled worker.
# Scope the in-process router as the active router for the WHOLE run so nested
# controller sub-pipes — which dispatch through get_pipe_router() — resolve THIS
# router rather than falling back to the hub default. Without the scope, the hub
# default in a Temporal-enabled worker is the Temporal router, so a DIRECT-mode
# sequence/batch would leak its nested pipes to Temporal, defeating the point of DIRECT.
direct_router = PipeRouter()
with scoped_pipe_router(direct_router):
    pipe_run = PipeRun(pipe_router=direct_router)
    ...
```

`BundleValidator` needs the same guard around its dry-run sweep:

1. In `__init__`, keep the router instance (don't discard it inside `PipeRun(...)`):
   ```python
   self._pipe_router = PipeRouter(observer=ObserverNoOp())
   self._pipe_run: PipeRunProtocol = PipeRun(pipe_router=self._pipe_router)
   ```
2. In `validate_pipes`, wrap the **per-pipe dry-run sweep loop** (step 4 — the `for pipe in sweepable_pipes: ... _classify_pipe(...)`) in:
   ```python
   from pipelex.hub import scoped_pipe_router  # add to the existing hub import block

   with scoped_pipe_router(self._pipe_router):
       for pipe in sweepable_pipes:
           results[pipe.pipe_ref] = await self._classify_pipe(...)
   ```
   Wrapping `validate_pipes` covers all entry points (`acquire_and_validate`, `validate_current_library`, and the direct `validate_bundle` path all funnel through it). Steps 1–3 (wiring check, signature pre-pass, telemetry) don't run pipes, so they don't need the scope.

### Why this is safe
- `scoped_pipe_router` is **contextvar-scoped** and restores the prior value on exit, so concurrent `/validate` requests don't leak into each other.
- `PipeBatch` fans branches out via `gather_bounded` → `asyncio.gather`, whose Tasks copy the current context at creation (and creation happens inside the `with` scope), so each branch task inherits the override and resolves the in-process router too.

## Secondary issue (related, lower priority)

The best-effort **graph** step in `validate.py` — `dry_run_pipeline()` (`pipelex/pipe_run/dry_run_pipeline.py`) → `PipelexRunner(...).execute_pipeline(...)` — has the **same leak**: with Temporal enabled, the runner's `_pipe_run` defaults to the hub's `get_pipe_run()` (Temporal), so nested controllers/graph generation also try to hit Temporal. It does not 422 because `validate.py` wraps it in `try/except PipelexError` and just logs a warning, **but it means `/validate` silently never returns a `graph_spec` in Temporal mode.** Same root cause, same style of fix (run the dry run in-process / scope an in-process router). Worth fixing in the same change so the validate response actually carries the graph.

## How to verify after fixing (local setup)

API on :8081 (`make run`), Temporal server + worker up (from `pipelex-worker`), both on the editable `pipelex` checkout.

```bash
# was failing → should now 200 with validated bundle (+ graph if the secondary issue is fixed too)
make bundle-validate BUNDLE=/Users/lchoquel/repos/Pipelex/pipelex-demos/mthds-wip/fashion_moodboard
# regression guard → still 200
make bundle-validate BUNDLE=/Users/lchoquel/repos/Pipelex/pipelex-demos/mthds-wip/joke_judge
```

Add a regression test in `pipelex`: a `BundleValidator.validate_pipes` sweep of a bundle containing a controller pipe (PipeBatch/PipeParallel) under a Temporal-enabled hub must **not** invoke the Temporal router — assert the scoped in-process router handles the nested dispatch (e.g. spy that `get_pipe_router()` resolves to the in-process router inside the controller branch, or that no `execute_workflow` is called).
```
