# Tier 2 Live: Crate Propagation to Content Generation Activities

**Status:** Ready for implementation (supersedes v2)
**Branch:** `fix/Temporal-Img`
**Date:** 2026-04-01

---

## What v2 got wrong

v2 assumed:

> "The activity runs in the same process as its parent workflow (Temporal guarantee). The ContextVar set by `setup_workflow_library()` propagates to the activity."

This is false at two levels:

1. **No same-process guarantee.** Temporal routes activities to any worker polling the same task queue. The activity can run on a different worker, even a different server.

2. **No ContextVar propagation even on the same worker.** The Temporal Python SDK creates a fresh execution context for each activity. The `_library_id` ContextVar set in a workflow's coroutine is invisible to activities dispatched by that workflow. This is by design: workflows and activities are independent execution units.

## Temporal execution model

Understanding where ContextVars do and don't propagate:

```
WfPipeRouter.run():
  setup_workflow_library(crate)       # ContextVar set in WORKFLOW context
  pipe.run_pipe()                     # INLINE await -- same coroutine -- ContextVar VISIBLE
    PipeLLM._live_run_operator_pipe()
      get_class_registry()            # OK: finds scoped registry via ContextVar
      content_generator.make_object_direct()
        ContentGeneratorChild:
          get_current_library_crate() # OK: ContextVar visible -- retrieves crate
          ObjectAssignment(library_crate=crate)
          execute_child_workflow(WfMakeObject, arg=assignment)

WfMakeObject.run():                   # CHILD WORKFLOW -- new execution context
  setup_workflow_library(crate)       # ContextVar set in THIS workflow's context
  workflow.start_activity(act_llm_gen_object, arg=assignment)

act_llm_gen_object(assignment):       # ACTIVITY -- new execution context
  get_class_registry()                # FAILS: ContextVar is None, returns global registry
                                      # Dynamic class not found!
```

The boundary crossings where ContextVars are lost:
- Workflow -> child workflow (new workflow execution context)
- Workflow -> activity (new activity execution context, possibly different process)

The only case where ContextVars propagate is **inline awaits** within the same workflow coroutine (e.g. `pipe.run_pipe()` in WfPipeRouter).

## What needs to change vs v2

v2 correctly ships the `LibraryCrate` to the child workflow. The missing piece: **the activity must also set up its own library context**, because the workflow's ContextVar doesn't reach it.

The activity `act_llm_gen_object` receives `ObjectAssignment` which now carries `library_crate`. The activity must call `setup_workflow_library()` before doing the LLM call, and `teardown_workflow_library()` after.

### Corrected execution flow

```
WfMakeObject.run():
  # Workflow-level setup is STILL needed for any inline code that uses get_class_registry()
  # (e.g. Temporal data converter deserializing activity results)
  setup_workflow_library(crate)
  workflow.start_activity(act_llm_gen_object, arg=assignment)

act_llm_gen_object(assignment):
  # Activity-level setup -- independent of the workflow's context
  if assignment.library_crate is not None:
      wf_library_id = setup_workflow_library(
          library_crate=assignment.library_crate,
          workflow_id=activity.info().workflow_id,  # unique per activity execution
      )
  try:
      return await llm_gen_object(object_assignment=assignment)
  finally:
      if wf_library_id is not None:
          teardown_workflow_library(wf_library_id)
```

## What v2 got right (already implemented, keep)

| Component | Status |
|-----------|--------|
| `workflow_library_setup.py` helper | Done |
| `library_crate` field on `ObjectAssignment` and `TextThenObjectAssignment` | Done |
| `library_manager.load_from_crate()` crate caching | Done |
| `hub.get_current_library_crate()` | Done |
| `ContentGeneratorChild` retrieves crate, embeds in assignments | Done |
| `ContentGeneratorTop` same | Done |
| `WfMakeObject` calls `setup_workflow_library()` on entry | Done (but insufficient alone) |
| Unit tests for assignment model round-trip | Done |
| 598 existing tests pass | Verified |

## Remaining work

### Activity-level library setup

The activities that call `get_class_registry()` must set up their own library context:

**File:** `pipelex/temporal/tprl_content_generation/act_llm_generate.py`

| Activity | Assignment model | Needs setup? |
|----------|-----------------|:---:|
| `act_llm_gen_object` | `ObjectAssignment` | Yes |
| `act_llm_gen_object_list` | `ObjectAssignment` | Yes |
| `act_llm_gen_text` | `LLMAssignment` | No (text output, no class lookup) |

For `WfMakeTextThenObject` and `WfMakeTextThenObjectList`: they call `act_llm_gen_text` first (no class lookup needed), then `act_llm_gen_object` / `act_llm_gen_object_list` with a follow-up `ObjectAssignment`. The follow-up assignment must also carry the `library_crate` so the activity can set up its context.

### Follow-up ObjectAssignment in text-then-object workflows

In `wf_make_object.py`, `WfMakeTextThenObject.run()` and `WfMakeTextThenObjectList.run()` create a follow-up `ObjectAssignment` mid-workflow (after the preliminary text step). This follow-up assignment must include `library_crate=workflow_arg.library_crate` so the subsequent `act_llm_gen_object` activity can set up its own library context.

### Workflow-level setup: still needed?

Yes. Even though the activity sets up its own context, the workflow may need the scoped registry for:
- Temporal data converter deserializing activity results (the returned `BaseModel` may reference dynamic classes)
- Any inline code between activities that calls `get_class_registry()`

Keep `setup_workflow_library()` in the workflow AND add it to the activities.

## Files to change (delta from v2)

| File | Change |
|------|--------|
| `pipelex/temporal/tprl_content_generation/act_llm_generate.py` | Add setup/teardown around `act_llm_gen_object` and `act_llm_gen_object_list` |
| `pipelex/temporal/tprl_content_generation/wf_make_object.py` | Pass `library_crate` on follow-up `ObjectAssignment` in text-then-object workflows |

## Properties

| Property | Status |
|----------|--------|
| Works across worker processes | Yes -- crate is self-contained, activity sets up independently |
| Works across different servers | Yes -- no shared state dependency |
| Per-workflow isolation | Yes -- each activity creates its own scoped registry |
| Concurrent safety | Yes -- no global state mutation |
| Idempotent loading | Yes -- fingerprint-based (same crate on same worker = no-op) |

## Rejected approaches (from v1, still rejected)

### A -- Embed schema in ObjectAssignment
Reconstruct Pydantic model from JSON schema. Fragile, creates parallel class resolution path.

### B -- Header propagation
Propagate `library_id` via Temporal interceptor headers. The library_id is a pointer to process-local state -- useless across processes.

### C -- Global registry
Register dynamic classes globally. Breaks per-workflow isolation.

## Test plan

### Must pass (existing)
- All Tier 1-5 dry-run tests
- All concurrent isolation tests
- `make agent-check` + existing test suite

### The fix target
- **Tier 2 live**: `dynamic_concept_sequence.mthds` with `--temporal` (currently failing)

### How to run Tier 2 live (3-process)

```bash
# 1. Kill everything for clean slate
tmux kill-session -t temporal-worker 2>/dev/null
tmux kill-session -t temporal-server 2>/dev/null
find pipelex/temporal -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
sleep 2

# 2. Start fresh server
tmux new-session -d -s temporal-server 'temporal server start-dev'
sleep 4

# 3. Start fresh worker
tmux new-session -d -c "$PWD" -s temporal-worker \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed'
sleep 4

# 4. Run Tier 2 live
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/dynamic_concept_sequence.mthds \
  --pipe dynamic_greeting_sequence \
  --temporal --no-logo --graph
```
