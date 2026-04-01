# Tier 2 Live: Crate Propagation to Content Generation Workflows

**Status:** Ready for implementation
**Branch:** `fix/Temporal-Img`
**Date:** 2026-04-01

---

## Problem

Content generation child workflows (`WfMakeObject`, `WfMakeObjectList`, `WfMakeTextThenObject`, `WfMakeTextThenObjectList`) run in their own Temporal execution contexts where the `_library_id` ContextVar is not set. The dynamic concept class registered in `WfPipeRouter`'s scoped `ClassRegistry` is invisible to these child workflows and their activities.

```
WfPipeRouter.run(pipe_job)
  set_current_library(wf_library_id)           # ContextVar set
  load_from_crate(crate)                       # dynamic classes registered in workflow-scoped registry
  pipe.run_pipe(library_crate=crate)
    PipeOperator._live_run_pipe(library_crate)  # crate received but NOT forwarded
      PipeLLM._live_run_operator_pipe(...)      # no crate parameter
        content_generator.make_object_direct()
          ContentGeneratorChild → WfMakeObject  # NEW workflow context — ContextVar is None
            act_llm_gen_object                  # NEW activity context — ContextVar is None
              get_class_registry()              # → global registry → class not found
```

The `library_crate` threads through the pipe controller chain (Sequence → SubPipe → PipeJob → WfPipeRouter) but **stops at the operator boundary**. `PipeOperator._live_run_pipe()` receives it but does not pass it to `_live_run_operator_pipe()`. From there, the content generator and its child workflows have no library context.

---

## Design

Extend the crate propagation pattern into the content generation chain. Every Temporal workflow that needs dynamic classes carries its own `LibraryCrate` and loads it on entry — the same principle that already works for `WfPipeRouter`.

### Crate-loading helper (new shared module)

Extract the crate-loading boilerplate from `WfPipeRouter` into a reusable helper. Both `WfPipeRouter` and the content generation workflows use it.

```python
# pipelex/temporal/tprl/workflow_library_setup.py

def setup_workflow_library(
    workflow_id: str,
    library_crate: LibraryCrate,
) -> str:
    """Set up a per-workflow library from a crate. Returns the library_id."""
    global_registry = KajsonManager.get_class_registry()
    workflow_registry = ClassRegistry()
    if isinstance(global_registry, ClassRegistry):
        workflow_registry.register_classes_dict(dict(global_registry.root))

    library_manager = get_library_manager()
    wf_library_id = f"wf_{workflow_id}"
    _wf_library_id, wf_library = library_manager.open_library(library_id=wf_library_id)
    wf_library.set_class_registry(workflow_registry)
    set_current_library(library_id=wf_library_id)
    library_manager.load_from_crate(library_id=wf_library_id, crate=library_crate)
    return wf_library_id


def teardown_workflow_library(library_id: str) -> None:
    """Tear down a per-workflow library."""
    try:
        get_library_manager().teardown(library_id=library_id)
    finally:
        teardown_current_library()
```

### Assignment models

`ObjectAssignment` and `TextThenObjectAssignment` gain an optional `library_crate` field:

```python
class ObjectAssignment(BaseModel):
    object_class_name: str
    llm_assignment_for_object: LLMAssignment
    library_crate: LibraryCrate | None = None

class TextThenObjectAssignment(BaseModel):
    object_class_name: str
    llm_assignment_for_text: LLMAssignment
    llm_assignment_factory_to_object: LLMAssignmentFactory
    library_crate: LibraryCrate | None = None
```

### Content generation workflows

`WfMakeObject` (and siblings) load the crate before starting their activity:

```python
@workflow.defn(name="wf_make_object")
class WfMakeObject(WorkflowClass[ObjectAssignment, BaseModel]):
    @workflow.run
    async def run(self, workflow_arg: ObjectAssignment) -> BaseModel:
        library_crate = workflow_arg.library_crate
        wf_library_id: str | None = None
        try:
            if library_crate is not None:
                wf_library_id = setup_workflow_library(
                    workflow_id=workflow.info().workflow_id,
                    library_crate=library_crate,
                )
            obj = await workflow.start_activity(
                activity=act_llm_gen_object,
                arg=workflow_arg,
                ...
            )
        finally:
            if wf_library_id is not None:
                teardown_workflow_library(library_id=wf_library_id)
        return obj
```

The activity runs in the same process as its parent workflow (Temporal guarantee). The ContextVar set by `setup_workflow_library()` propagates to the activity — `get_class_registry()` finds the scoped registry.

### Threading chain

```
PipeOperator._live_run_pipe(library_crate)           # already receives it
  → _live_run_operator_pipe(library_crate)            # NEW param
    → PipeLLM._live_run_operator_pipe(library_crate)
      → _llm_gen_object_stuff_content(library_crate)  # NEW param
        → content_generator.make_object_direct(library_crate=library_crate)
          → ContentGeneratorChild.make_object_direct(library_crate)
            → ObjectAssignment.make_for_class(library_crate=library_crate)
              → WfMakeObject.run(object_assignment)
                # object_assignment.library_crate is set → setup_workflow_library()
```

### ContentGeneratorProtocol changes

Object-producing methods gain an optional `library_crate` parameter:

- `make_object_direct(library_crate=...)`
- `make_text_then_object(library_crate=...)`
- `make_object_list_direct(library_crate=...)`
- `make_text_then_object_list(library_crate=...)`

`ContentGeneratorDry` and `ContentGeneratorDirect` accept and ignore it. Only `ContentGeneratorChild` uses it to populate the assignment model.

---

## Affected workflows

| Workflow | Assignment model | Needs crate? | Why |
|----------|-----------------|:---:|-----|
| `WfMakeObject` | `ObjectAssignment` | Yes | `llm_gen_object` looks up `object_class_name` |
| `WfMakeObjectList` | `ObjectAssignment` | Yes | `llm_gen_object_list` looks up `object_class_name` |
| `WfMakeTextThenObject` | `TextThenObjectAssignment` | Yes | Delegates to `act_llm_gen_object` |
| `WfMakeTextThenObjectList` | `TextThenObjectAssignment` | Yes | Delegates to `act_llm_gen_object_list` |
| `WfMakeLLMText` | `LLMAssignment` | No | Text output — native concept, always in global |
| `WfMakeImages` | `ImgGenAssignment` | No | No class registry lookup |
| `WfMakeJinja2Text` | `TemplatingAssignment` | No | No class registry lookup |
| `WfMakeExtract` | `ExtractAssignment` | No | No class registry lookup |
| `WfRenderPageViews` | `RenderPageViewsAssignment` | No | No class registry lookup |

---

## Properties

| Property | Status |
|----------|--------|
| Works across worker processes | Yes — crate is self-contained |
| Per-workflow isolation | Yes — each workflow has its own scoped registry |
| Concurrent safety | Yes — no global state mutation |
| Idempotent loading | Yes — fingerprint-based (same crate on same worker = no-op) |
| Payload overhead | Crate serialized once more per structured output call |
| Dashboard transparency | Crate visible as JSON in WfMakeObject input |
| Phase 5 compatible | Yes — StoragePayloadCodec offloads large payloads transparently |

---

## Files to change

| File | Change |
|------|--------|
| `pipelex/temporal/tprl/workflow_library_setup.py` | **New** — `setup_workflow_library()` / `teardown_workflow_library()` |
| `pipelex/temporal/tprl_pipe/wf_pipe_router.py` | Refactor to use shared helper |
| `pipelex/temporal/tprl_content_generation/wf_make_object.py` | Crate loading + teardown in all workflow classes |
| `pipelex/cogt/content_generation/assignment_models.py` | Add `library_crate` field to `ObjectAssignment` and `TextThenObjectAssignment` |
| `pipelex/cogt/content_generation/content_generator_protocol.py` | Add `library_crate` param to object methods |
| `pipelex/temporal/tprl_content_generation/content_generator_child.py` | Pass `library_crate` into assignment models |
| `pipelex/cogt/content_generation/content_generator_direct.py` | Accept and ignore `library_crate` |
| `pipelex/cogt/content_generation/content_generator_dry.py` | Accept and ignore `library_crate` |
| `pipelex/pipe_operators/pipe_operator.py` | Add `library_crate` param to `_live_run_operator_pipe()`, pass it through |
| `pipelex/pipe_operators/llm/pipe_llm.py` | Accept `library_crate`, thread to content generator |
| `pipelex/pipe_operators/img_gen/pipe_img_gen.py` | Accept `library_crate` (unused) |
| `pipelex/pipe_operators/extract/pipe_extract.py` | Accept `library_crate` (unused) |
| `pipelex/pipe_operators/compose/pipe_compose.py` | Accept `library_crate` (unused) |

---

## Test plan

### Unit tests

- `ObjectAssignment` round-trip with `library_crate` field
- `ObjectAssignment.make_for_class()` accepts and stores `library_crate`
- `setup_workflow_library()` / `teardown_workflow_library()` helper correctness

### Regression (existing, must keep passing)

- All Tier 1-5 dry-run tests
- All Tier 1 live tests (text output, no dynamic classes)
- Tier 3-5 tests (parallel, image)

### New

- **Tier 2 live**: `dynamic_concept_sequence.mthds` with `--temporal` (currently failing)
- Concurrent dynamic concept test: two workflows with different dynamic concepts on the same worker

---

## Implementation order

1. Extract `setup_workflow_library()` / `teardown_workflow_library()` from `WfPipeRouter`
2. Add `library_crate` field to `ObjectAssignment` and `TextThenObjectAssignment`
3. Wire crate loading into `WfMakeObject` and siblings
4. Thread `library_crate` through PipeOperator → PipeLLM → ContentGenerator → Assignment
5. Update `ContentGeneratorProtocol` and all implementations
6. Run existing tests (no regressions)
7. Run Tier 2 live test (the fix)
8. `make agent-check` + `make agent-test`

---

## Rejected alternatives

### A — Embed schema in ObjectAssignment

Reconstruct Pydantic model from JSON schema at the activity level. Bypasses the LibraryCrate/Library/ClassRegistry architecture. Schema-to-model reconstruction is fragile (inheritance, validators, custom types) and creates a parallel class resolution path.

### B — Header propagation

Propagate `library_id` via Temporal interceptor headers. The `library_id` is a pointer to process-local `LibraryManager` state — useless across Temporal boundaries. Any fix that makes B work (shipping the crate alongside) collapses into approach D with extra infrastructure.

### C — Global registry

Register dynamic classes in the global `KajsonManager` registry alongside the scoped one. Breaks per-workflow isolation: concurrent workflows with same-named concepts silently corrupt each other's schemas, teardown races cause class-not-found errors, and non-deterministic replay becomes possible. Every mitigation (workflow-prefixed names, ref counting, conflict detection) either degrades the system or doesn't solve the core problem.
