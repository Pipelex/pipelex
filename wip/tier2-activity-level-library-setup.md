# Activity-Level Library Setup for Temporal Crate Propagation

**Status:** Implemented and validated (Tier 2 live PASS)
**Branch:** `fix/Temporal-Img`
**Date:** 2026-04-01
**Supersedes:** tier2-live-registry-propagation-v3.md (which identified the problem; this doc records the solution)

---

## The problem

When a Temporal workflow dispatches an activity, the activity runs in a **fresh execution context** — a separate thread pool slot, possibly on a different worker or even a different server. Python `ContextVar` values set in the workflow's coroutine are invisible to the activity.

This means `get_class_registry()` inside an activity returns the **global registry**, which does not contain the dynamic concept classes loaded by `setup_workflow_library()` in the parent workflow.

Concrete failure path:

```
WfMakeObject.run():
  setup_workflow_library(crate)          # ContextVar set in WORKFLOW context
  workflow.start_activity(act_llm_gen_object, arg=assignment)

act_llm_gen_object(assignment):          # ACTIVITY — new execution context
  llm_gen_object(assignment)
    get_class_registry()                 # Returns GLOBAL registry — no dynamic classes
    registry.get_required_base_model("DynamicConcept")  # KeyError!
```

The workflow-level setup is necessary (for deserializing activity results via the data converter), but **not sufficient** — the activity must also set up its own library context.

## The solution

Each object-generating activity sets up and tears down its own scoped library from the `LibraryCrate` already carried in its `ObjectAssignment` argument.

### What changed

#### 1. `pipelex/temporal/tprl_content_generation/act_llm_generate.py`

Added setup/teardown around `act_llm_gen_object` and `act_llm_gen_object_list`:

```python
@activity.defn
async def act_llm_gen_object(object_assignment: ObjectAssignment) -> BaseModel:
    log.dev("act_llm_gen_object")
    wf_library_id: str | None = None
    if object_assignment.library_crate is not None:
        act_info = activity.info()
        wf_library_id = setup_workflow_library(
            library_crate=object_assignment.library_crate,
            workflow_id=act_info.activity_id,
        )
    try:
        return await llm_gen_object(object_assignment=object_assignment)
    finally:
        if wf_library_id is not None:
            teardown_workflow_library(wf_library_id=wf_library_id)
```

Same pattern for `act_llm_gen_object_list`.

**No change to `act_llm_gen_text`** — text generation does not look up dynamic classes.

**`activity_id` only (not `workflow_id`):** The activity MUST use `activity.info().activity_id` — NOT `workflow_id`. Using `workflow_id` causes a collision: the parent workflow (`WfMakeObject`) already created a library with `wf_{workflow_id}`, so when the activity tries to create another with the same ID:
1. `open_library()` returns the existing library object
2. The activity's fresh `ClassRegistry` overwrites the workflow's populated one via `set_class_registry()`
3. `load_from_crate()` fingerprint check sees the crate was already loaded under this library_id → **skips the load**
4. Result: activity has an empty registry → `ClassRegistryNotFoundError`

Using `activity_id` guarantees a unique library_id per activity execution.

#### 2. `pipelex/temporal/tprl_content_generation/wf_make_object.py`

The text-then-object workflows (`WfMakeTextThenObject`, `WfMakeTextThenObjectList`) create a **follow-up** `ObjectAssignment` mid-workflow after the preliminary text step. These were missing `library_crate`, so the subsequent `act_llm_gen_object` activity had no crate to set up from.

Fixed both locations:

```python
# WfMakeTextThenObject — was missing library_crate
fup_obj_assignment = ObjectAssignment(
    llm_assignment_for_object=fup_llm_assignment,
    object_class_name=workflow_arg.object_class_name,
    library_crate=workflow_arg.library_crate,        # added
)

# WfMakeTextThenObjectList — same fix
object_assignment = ObjectAssignment(
    object_class_name=workflow_arg.object_class_name,
    llm_assignment_for_object=llm_assignment_for_object,
    library_crate=workflow_arg.library_crate,        # added
)
```

## Additional bugs found during Tier 2 live validation

### Bug 2: `load_from_crate()` doesn't cache the crate object

`ContentGeneratorChild.make_object_direct()` calls `get_current_library_crate()` to pass the crate to child workflows. This calls `get_library_manager().get_crate(library_id)`, which checks `_crate_cache`. But `load_from_crate()` loads the crate's *contents* (domains, concepts, pipes) into the library without caching the crate object itself.

**Fix:** Added `cache_crate()` method to `LibraryManager` and call it from `setup_workflow_library()` after `load_from_crate()`. Cannot cache inside `load_from_crate()` directly because `load_from_blueprints()` calls it too, and that would conflict with blueprint accumulation (each `load_from_blueprints` call builds a partial crate, but `get_crate()` should return the accumulated result).

**Files changed:**
- `pipelex/libraries/library_manager_abstract.py` — added `cache_crate()` method
- `pipelex/libraries/library_manager.py` — implemented `cache_crate()`
- `pipelex/temporal/tprl/workflow_library_setup.py` — calls `cache_crate()` after `load_from_crate()`

### Bug 3: Temporal data converter runs outside workflow's ContextVar scope

The Temporal SDK's data converter deserializes activity return values during **activation processing** — not inside the workflow coroutine. The `_library_id` ContextVar set by `setup_workflow_library()` in the workflow's `run()` method is invisible during activation. So `get_class_registry()` in the data converter returns the global registry, which lacks dynamic classes.

**Fix:** Maintain a global `_workflow_registries` dict (keyed by `wf_library_id`) in `workflow_library_setup.py`. The data converter's `_get_effective_class_registry()` checks:
1. ContextVar-based registry (works in activities and inline workflow code)
2. Fallback: any active workflow's registry from the global dict
3. Global KajsonManager registry (baseline)

**Files changed:**
- `pipelex/temporal/tprl/workflow_library_setup.py` — added `_workflow_registries` dict, `get_any_workflow_registry()`, registers/unregisters in setup/teardown
- `pipelex/temporal/temporal_data_converter.py` — added `_get_effective_class_registry()` with fallback chain

## How `setup_workflow_library()` now works

1. Creates a **scoped `ClassRegistry`** pre-seeded from the global registry
2. Opens a per-execution library in `LibraryManager`
3. Attaches the scoped registry to the library
4. Sets the `_library_id` ContextVar so `get_class_registry()` returns the scoped registry
5. Calls `load_from_crate()` which:
   - Loads domains
   - Loads concepts in topological order via `ConceptFactory` (generates Pydantic classes, registers them)
   - Resolves forward references with `model_rebuild()`
   - Loads pipes
6. Caches the crate in `LibraryManager._crate_cache` for later retrieval by `get_current_library_crate()`
7. Registers the scoped registry in the global `_workflow_registries` dict for the data converter fallback

The crate is **fingerprinted** — `load_from_crate()` is idempotent. If the same crate was already loaded on this worker (same fingerprint), it's a no-op.

## Execution flow after the fix

```
WfMakeObject.run():
  setup_workflow_library(crate)              # Workflow-level: for data converter + crate cache
  workflow.start_activity(act_llm_gen_object, arg=assignment)

act_llm_gen_object(assignment):              # ACTIVITY — new execution context
  setup_workflow_library(assignment.crate)   # Activity-level: registers dynamic classes HERE
  try:
    llm_gen_object(assignment)
      get_class_registry()                   # Returns SCOPED registry — dynamic classes present
      registry.get_required_base_model(...)  # Found!
      llm_worker.gen_object(schema=...)      # LLM generates valid structured output
  finally:
    teardown_workflow_library(...)            # Cleanup

# Back in workflow: data converter deserializes the returned BaseModel
# using _workflow_registries fallback (ContextVar not available during activation)
```

## Why both workflow-level AND activity-level setup are needed

| Context | Why needed |
|---------|-----------|
| **Workflow** | 1. The Temporal data converter needs the scoped registry to deserialize activity return values (via `_workflow_registries` fallback). 2. `get_current_library_crate()` needs the crate cached for propagation to child workflows. |
| **Activity** | The activity code calls `get_class_registry()` to look up the target class schema before passing it to the LLM. Without its own setup, it gets the global registry which lacks the dynamic classes. |

## Properties

| Property | Status |
|----------|--------|
| Works across worker processes | Yes — crate is self-contained, activity sets up independently |
| Works across different servers | Yes — no shared state dependency |
| Per-workflow isolation | Yes — each activity creates its own scoped registry |
| Concurrent safety | Yes — ContextVar is per-coroutine for activities; `_workflow_registries` uses threading.Lock |
| Idempotent loading | Yes — fingerprint-based (same crate on same worker = no-op) |
| Backward compatible | Yes — `library_crate` is optional, activities without it behave as before |

## Test verification

- All targeted tests pass (424 temporal + cogt tests)
- `make agent-check` passes (pyright, ruff, mypy, plxt)
- Tier 2 live (3-process: server + worker + submitter) is the real validation target — see wip/tier2-live-registry-propagation-v3.md doc for the test procedure
