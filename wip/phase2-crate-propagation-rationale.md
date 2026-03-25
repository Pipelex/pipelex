# Design Rationale: LibraryCrate Propagation in Distributed Execution

> **Status**: Decided
> **Date**: 2026-03-25
> **Related**: [00-master-plan.md](00-master-plan.md)

---

## Problem

Phase 2 ships a `LibraryCrate` to Temporal workers so they can load the library and resolve child pipes via `get_required_pipe()`. The master plan v2 proposed adding `library_crate` to `PipeJob` and using an `act_library_setup` activity to load it.

Two gaps in that design:

1. **Child workflow propagation**: Pipe controllers (PipeSequence, PipeParallel, etc.) dispatch child pipes through `SubPipe.run_pipe()` → `PipeRouterChild` → new `WfPipeRouter` child workflow. Each child workflow is a separate Temporal workflow that **can land on a different worker**. The crate must be on each child `PipeJob`, or the child worker won't have the library.

2. **Activity necessity**: The plan called for an `act_library_setup` activity. But loading a crate is pure in-memory work — deserializing Pydantic models into dicts. Activities are for I/O-bound or side-effectful operations that need retry semantics. An activity adds latency and complexity for no benefit here.

---

## The Fundamental Constraint

In Temporal distributed execution, **the only data channel between parent and child workflow is the serialized workflow argument**. There is no shared memory, no shared process, no ContextVar, no singleton that crosses the workflow boundary. Child workflows can run on any available worker in the task queue.

This means the crate cannot be stashed in a ContextVar, a library manager singleton, or any other in-process state and expected to be available in child workflows. It must travel in the `PipeJob`.

---

## Decision: `library_crate` on `PipeJob`, threaded through the signature chain

### Where the crate lives

`library_crate: LibraryCrate | None = None` is added to `PipeJob`.

### How it propagates

The crate must flow from `WfPipeRouter` (which has the `PipeJob`) down to `SubPipe` (which builds child `PipeJob`s). The call chain is:

```
WfPipeRouter.run(pipe_job: PipeJob)
  → pipe.run_pipe(job_metadata, working_memory, pipe_run_params, output_name, library_crate)
    → _live_run_pipe(job_metadata, working_memory, pipe_run_params, output_name, library_crate)
      → [PipeController] _live_run_controller_pipe(..., library_crate)
        → SubPipe.run_pipe(..., library_crate)
          → PipeJobFactory.make_pipe_job(..., library_crate)  # child PipeJob carries the crate
            → PipeRouterChild → new WfPipeRouter(child_pipe_job)
```

`library_crate` is added as an optional parameter (default `None`) at each level. Pipe operators (PipeLLM, PipeExtract, etc.) receive it but ignore it — they have no child pipes.

### How loading works

At the top of `WfPipeRouter.run()`, if `pipe_job.library_crate` is present, call `library_manager.load_from_crate()` inline (no activity). The load is idempotent via fingerprint — if the crate was already loaded on this worker, it's a no-op.

---

## Alternatives Considered and Rejected

### Put the crate on `PipeRunParams`

`PipeRunParams` already threads through the entire execution tree — `SubPipe` receives it and passes it to `PipeJobFactory`. No signature changes needed.

**Rejected because**: `PipeRunParams` is about *how to run* a pipe (run mode, stack limit, multiplicity, batch params). It gets copied and mutated at every nesting level. The crate is immutable static context. Mixing execution parameters with library content is semantically wrong and makes `PipeRunParams` a grab-bag.

### Put the crate on `JobMetadata`

`JobMetadata` also threads through the entire tree. Since it's inside `PipeJob`, we could avoid the `PipeJob`-level field entirely.

**Rejected because**: `JobMetadata` carries observability and identity data (user_id, pipeline_run_id, OTel context, graph context). Adding library content to it is semantically wrong — metadata is about *who* and *when*, not *what to load*.

### ContextVar / library manager stash

Store the crate in a `ContextVar` or on the library manager after loading. `SubPipe` reads it when building child `PipeJob`s. Zero signature changes.

**Rejected because**: This is fundamentally broken in distributed execution. ContextVars and singletons are per-process state. Temporal child workflows can land on different workers — different processes, different servers. The only data channel is the serialized `PipeJob`. This was the key insight that ruled out all in-process state approaches.

### `act_library_setup` activity

Use a Temporal activity to load the crate before pipe execution.

**Rejected because**: Loading a crate is pure in-memory work — iterating over Pydantic model dicts and populating the library manager. It involves no I/O, no network calls, no file reads. Activities exist for operations that need Temporal's retry/timeout/heartbeat semantics. Using an activity here adds unnecessary latency (activity scheduling overhead) and complexity for zero benefit.

### Put the crate only on `PipeController` (not `PipeAbstract`)

Since only controllers have child pipes, add the parameter only at the `PipeController` level.

**Rejected because**: `PipeAbstract.run_pipe()` is the entry point called by `WfPipeRouter`. It calls `_live_run_pipe()` internally. If `_live_run_pipe` has a different signature on `PipeController` than on `PipeAbstract`, the override breaks. The crate must cross the `run_pipe()` boundary, which means `PipeAbstract` must accept it.

---

## Blast Radius

The signature change touches the following layers:

| Layer | File | Change |
|-------|------|--------|
| `PipeAbstract.run_pipe()` | `pipelex/core/pipes/pipe_abstract.py` | Add optional `library_crate` param |
| `PipeAbstract._live_run_pipe()` | `pipelex/core/pipes/pipe_abstract.py` | Add optional `library_crate` param |
| `PipeOperator._live_run_pipe()` | `pipelex/pipe_operators/pipe_operator.py` | Add param, ignore it |
| `PipeController._live_run_pipe()` | `pipelex/pipe_controllers/pipe_controller.py` | Add param, forward to `_live_run_controller_pipe()` |
| `PipeController._live_run_controller_pipe()` | `pipelex/pipe_controllers/pipe_controller.py` | Add param (abstract) |
| PipeSequence | `pipelex/pipe_controllers/sequence/pipe_sequence.py` | Forward to `SubPipe.run_pipe()` |
| PipeBatch | `pipelex/pipe_controllers/batch/pipe_batch.py` | Forward to child pipe execution |
| PipeCondition | `pipelex/pipe_controllers/condition/pipe_condition.py` | Forward to child pipe execution |
| PipeParallel | `pipelex/pipe_controllers/parallel/pipe_parallel.py` | Forward to `SubPipe.run_pipe()` |
| `SubPipe.run_pipe()` | `pipelex/pipe_controllers/sub_pipe.py` | Add param, set on child `PipeJob` |
| `PipeJob` | `pipelex/pipe_run/pipe_job.py` | Add `library_crate` field |
| `PipeJobFactory` | `pipelex/pipe_run/pipe_job_factory.py` | Accept and forward `library_crate` |
| `WfPipeRouter` | `pipelex/temporal/tprl_pipe/wf_pipe_router.py` | Load crate, pass to `run_pipe()` |
| `PipeRouter` (direct) | `pipelex/pipe_run/pipe_router.py` | Pass `library_crate` from `PipeJob` to `run_pipe()` |

Every change is mechanical: add one optional parameter, forward it. The crate is never modified, only carried.
