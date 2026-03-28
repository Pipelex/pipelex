# Phase 3 Regression: Deferred Hydration Fails in 3-Process Mode

## Problem Statement

Temporal Phase 3 (Deferred WorkingMemory Hydration) passes all tests in Mode 1
(pytest with in-process worker) but fails in Mode 2 (true 3-process: server + worker
+ submitter) with:

```
KajsonDecoderError: Class 'dynamic_concept_test__Greeting' not found in module 'builtins'
```

This is a regression because Phase 3 was marked complete in `wip/00-master-plan.md:208`.

## How to Reproduce

Use the `/temporal-e2e-validate` skill (defined in `.claude/skills/temporal-e2e-validate/`).
It has two modes:

- **Mode 1** (pytest): All tests pass — confirms Phase 3 logic works in-process.
- **Mode 2** (3-process): Tier 2 (deferred hydration) hangs, worker shows the error above.

Quick reproduction of Mode 2 failure (assumes Temporal dev server on localhost:7233):

```bash
# Terminal 1: Temporal server
temporal server start-dev

# Terminal 2: Worker (no PIPELEXPATH — bundles arrive only via crate)
.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed

# Terminal 3: Submitter — this hangs because the worker fails to deserialize
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/dynamic_concept_sequence.mthds \
  --pipe dynamic_greeting_sequence \
  --temporal --dry-run --mock-inputs --no-logo
```

The worker log will show `KajsonDecoderError: Class 'dynamic_concept_test__Greeting'
not found in module 'builtins'` during child workflow result deserialization.

## Root Cause Analysis

### The deserialization chain

When a parent WfPipeRouter dispatches a child WfPipeRouter (for each step in a
PipeSequence), the child returns a `PipeOutput` containing `StructuredContent` with
a dynamically generated class (e.g. `dynamic_concept_test__Greeting`).

Temporal serializes this return value via `kajson.dumps()`, which records
`__class__: "dynamic_concept_test__Greeting"` and `__module__: "builtins"`.
The `__module__` is `"builtins"` because dynamically generated classes (created via
`type()` in ConceptFactory) get `builtins` as their module by default.

The parent workflow then deserializes via the data converter:

```
_apply_resolve_child_workflow_execution  (Temporal SDK internal callback)
  → _convert_payloads
    → BaseModelPayloadConverter.from_payload()
      → kajson.loads(data, class_registry=get_class_registry())
```

### Why Mode 1 works but Mode 2 fails

The data converter calls `pipelex.hub.get_class_registry()`, which checks the
`_library_id` ContextVar:

```python
# pipelex/hub.py:381-392
def get_class_registry() -> ClassRegistryAbstract:
    library_id = _library_id.get()
    if library_id is not None:
        registry = get_library_manager().get_library_class_registry(library_id)
        if registry is not None:
            return registry
    return KajsonManager.get_class_registry()
```

**The critical problem**: `_apply_resolve_child_workflow_execution` is a callback
invoked by the Temporal SDK's internal event processor, NOT from within the workflow
coroutine's `run()` method. The `_library_id` ContextVar was set inside `run()`,
but Temporal's event processing does not execute in the same ContextVar scope. So
`_library_id.get()` returns `None`, and `get_class_registry()` falls back to the
global KajsonManager registry.

**Mode 1 (in-process)**: The test fixture `pipe_job_from_bundle()`
(`tests/integration/pipelex/fixtures/pipe_job_helpers.py:73-85`) loads the bundle
into a Library. During loading, ConceptFactory registers dynamic classes via
`hub.get_class_registry()`. The Library created by `open_library()` has no
ClassRegistry set (unlike the workflow which explicitly calls
`wf_library.set_class_registry()`), so `get_library_class_registry()` returns None,
and classes are registered in the **global** KajsonManager registry. When the data
converter falls back to the global registry, it finds the classes. **The test fixture
masks the bug by pre-populating the global registry.**

**Mode 2 (3-process)**: The worker process starts with no bundles loaded. The global
KajsonManager registry has no dynamic classes. WfPipeRouter creates a per-workflow
ClassRegistry and loads the crate into it, but the data converter can't access it
(ContextVar not set in Temporal's event processing context). The global registry
lookup fails, then `sys.modules["builtins"]` lookup fails → `KajsonDecoderError`.

### Why the ContextVar approach doesn't work here

The Temporal Python SDK's `_workflow_instance.py` processes events (activity results,
child workflow results) via internal callbacks. These callbacks call `_convert_payloads`
which invokes the data converter. This call chain runs in the SDK's internal context,
not in the coroutine context of the workflow's `run()` method where `set_current_library()`
was called. Python ContextVars set inside a coroutine are not automatically visible
to SDK-internal callbacks that run outside that coroutine's execution frame.

## What Was Planned vs What Was Implemented

The original execution plan (`wip/phase3-execution-plan.md`) specified two mechanisms
that were not implemented:

### 1. CompositeClassRegistry (plan step A1-A3)

**Planned**: A new `ClassRegistryAbstract` implementation in kajson that wraps a local
registry + parent registry. Lookups check local first, fall back to parent. Mutations
go to local only.

**Actual**: Not implemented. The file `kajson/kajson/composite_class_registry.py` does
not exist. Instead, the workflow creates a plain `ClassRegistry` and pre-seeds it from
the global registry's entries:

```python
# wf_pipe_router.py:37-41
global_registry = KajsonManager.get_class_registry()
workflow_registry = ClassRegistry()
if isinstance(global_registry, ClassRegistry):
    workflow_registry.register_classes_dict(dict(global_registry.root))
```

This pre-seeding approach works for isolation but doesn't help with the data converter
problem — the data converter still can't reach the workflow-scoped registry.

### 2. ContextVar scoping in KajsonManager (plan step A2)

**Planned**: A `_scoped_class_registry` ContextVar in KajsonManager itself, checked
by `KajsonManager.get_class_registry()` before returning the global registry. This
would allow setting a scoped registry that kajson's decoder would automatically use.

**Actual**: Not implemented. `KajsonManager.get_class_registry()` in the kajson repo
(`kajson/kajson/kajson_manager.py`) has no ContextVar — it always returns the singleton's
global registry. The scoping was implemented at the pipelex hub level via `_library_id`
ContextVar, which doesn't work for Temporal's internal data converter calls.

## Key Files

| File | Role in the problem |
|------|---------------------|
| `pipelex/temporal/tprl_pipe/wf_pipe_router.py` | Sets up per-workflow registry, loads crate, hydrates WM |
| `pipelex/temporal/temporal_data_converter.py:77` | Calls `get_class_registry()` during deserialization |
| `pipelex/hub.py:381-392` | `get_class_registry()` uses `_library_id` ContextVar |
| `pipelex/hub.py:462-467` | `_library_id` ContextVar + `set_current_library()` |
| `pipelex/pipe_run/pipe_job.py:34-49` | `prepare_for_temporal()` serializes WM to raw dict |
| `pipelex/temporal/tprl_pipe/hydration.py` | `hydrate_working_memory()` — works correctly |
| `/Users/lchoquel/repos/Pipelex/kajson/kajson/kajson_manager.py` | Global registry, no ContextVar scoping |
| `/Users/lchoquel/repos/Pipelex/kajson/kajson/json_decoder.py:141-161` | Decoder: explicit registry → sys.modules → error |
| `tests/integration/pipelex/fixtures/pipe_job_helpers.py:73-85` | Test fixture that masks the bug |
| `wip/phase3-execution-plan.md` | Original plan with CompositeClassRegistry + KajsonManager ContextVar |

## Scope of Impact

All bundles with dynamic concept classes (inline `structure` in `.mthds`) fail in
3-process mode. Bundles using only native types (Text) work fine. Affected tests:

- Tier 2: `dynamic_concept_sequence.mthds` — direct Phase 3 validation
- Tier 3: `temporal_parallel.mthds` — uses ToneAnalysis/LengthAnalysis concepts
- All concurrent concept isolation tests — use conflicting Result/Profile/Summary concepts

PipeParallel with native text works. Concurrent pipe isolation (native text) works.

## Fix Applied During This Session

A separate fixture ordering bug was fixed in `tests/integration/pipelex/temporal/conftest.py`:
`boot_temporal` could run before `reset_pipelex_config_fixture` when using `--temporal-server local`,
because `_session_owns_pipelex()` caused the module-scoped fixture to skip initialization while
the session-scoped `env` fixture (which was supposed to init Pipelex) is not autouse. Fixed by
always initializing Pipelex in the module-scoped fixture. This fix is uncommitted.
