# Phase 3: Deferred WorkingMemory Hydration + Scoped ClassRegistry

## Context

Phases 0-2 are complete. Phase 2 ships the `LibraryCrate` inside `PipeJob` so Temporal workers can load pipes via `load_from_crate()`. However, Phase 2 deliberately avoided custom concept classes — its test bundle uses only native `Text` concepts.

**Problem 1 — Chicken-and-egg deserialization**: When `mthds_content` introduces custom concepts with inline structures (e.g., `WeightedScore` with fields `score: float, reasoning: str`), `StructureGenerator` creates a dynamic `StructuredContent` subclass at runtime and registers it in Kajson's `ClassRegistry`. On the worker, Temporal auto-deserializes `PipeJob` via Kajson **before** the workflow code runs — so `load_from_crate()` hasn't registered the dynamic classes yet. Kajson can't resolve the `__class__`/`__module__` metadata for dynamic content types.

**Problem 2 — ClassRegistry is global (multi-tenancy)**: The `ClassRegistry` is a process-wide singleton. Multiple concurrent workflows on the same worker could define concepts with the same name but different structures. Without isolation, they'd overwrite each other's class registrations, causing data corruption or validation errors.

**Solution**: Two complementary changes:
1. **Deferred hydration** — Serialize `WorkingMemory` as a raw `dict[str, Any]` before Temporal dispatch. After `load_from_crate()` registers dynamic classes, hydrate the raw dict back into typed `WorkingMemory`.
2. **Scoped ClassRegistry** — Add a `CompositeClassRegistry` to Kajson that layers a per-workflow local registry on top of the global one. Each workflow registers dynamic classes in its isolated local registry.

---

## Design Decisions

1. **Always use `working_memory_raw` when `library_crate` is present** — avoids complex detection of which concepts are dynamic vs native. Simpler, safer.

2. **Conversion in `PipeJob.prepare_for_temporal()`** — called by `PipeRouterTop` and `PipeRouterChild` before dispatching.

3. **Hydration in `WfPipeRouter.run()`** — after `load_from_crate()`, before `pipe.run_pipe()`.

4. **`working_memory` becomes optional** (`WorkingMemory | None = None`) — direct mode sets it, Temporal mode uses `working_memory_raw`. A `get_working_memory()` helper on PipeJob provides unified access.

5. **CompositeClassRegistry in Kajson** — local-first lookup with global fallback. Registrations go to local only. Managed per-workflow via ContextVar in `KajsonManager`.

---

## Part A: Scoped ClassRegistry (Kajson changes)

### A1: New `CompositeClassRegistry` class

**File**: `kajson/kajson/composite_class_registry.py` (NEW)

A `ClassRegistryAbstract` implementation that wraps a local `ClassRegistry` + a parent (global) registry:
- `get_class(name)`: check local first, then parent
- `get_required_class(name)`: check local first, then parent
- `get_required_subclass(name, base_class)`: check local first, then parent
- `has_class(name)`: check local or parent
- `has_subclass(name, base_class)`: check local or parent
- `register_class(class_type)`: register in local only
- `register_classes(classes)`: register in local only
- `register_classes_dict(classes)`: register in local only
- `teardown()`: teardown local only (never touch parent)
- `unregister_class(class_type)`: from local only
- `unregister_class_by_name(name)`: from local only

### A2: ContextVar-based scoping in `KajsonManager`

**File**: `kajson/kajson/kajson_manager.py`

Add:
```python
from contextvars import ContextVar

_scoped_class_registry: ContextVar[ClassRegistryAbstract | None] = ContextVar(
    "_scoped_class_registry", default=None
)

class KajsonManager(metaclass=MetaSingleton):
    # ... existing code ...

    @classmethod
    def get_class_registry(cls) -> ClassRegistryAbstract:
        scoped = _scoped_class_registry.get()
        if scoped is not None:
            return scoped
        return cls.get_instance()._class_registry

    @classmethod
    def set_scoped_class_registry(cls, registry: ClassRegistryAbstract | None) -> None:
        _scoped_class_registry.set(registry)
```

### A3: Tests for CompositeClassRegistry

**File**: `kajson/tests/test_composite_class_registry.py` (NEW)

- `test_local_lookup_takes_priority`: register class A in parent, class A (different) in local → local wins
- `test_fallback_to_parent`: register class only in parent → found via composite
- `test_registration_goes_to_local_only`: register via composite → present in local, absent in parent
- `test_teardown_clears_local_only`: teardown composite → local cleared, parent untouched
- `test_has_class_checks_both`: class in parent only → `has_class()` returns True
- `test_scoped_context_var`: set scoped registry → `get_class_registry()` returns it; unset → returns global

---

## Part B: Deferred WorkingMemory Hydration (Pipelex changes)

### B1: Tests first — PipeJob raw field

**File**: `tests/unit/pipelex/pipe_run/test_pipe_job_hydration.py` (NEW)

- `test_prepare_for_temporal_moves_wm_to_raw`: PipeJob with WM + crate → after `prepare_for_temporal()`, `working_memory` is None, `working_memory_raw` is a dict
- `test_prepare_for_temporal_noop_without_crate`: PipeJob without crate → no-op
- `test_prepare_for_temporal_empty_wm`: PipeJob with empty WM + crate → raw dict is the empty WM serialization
- `test_get_working_memory_from_typed`: PipeJob with `working_memory` set → returns it
- `test_get_working_memory_from_raw_raises`: PipeJob with only `working_memory_raw` → raises (must hydrate first)
- `test_get_working_memory_both_none_returns_empty`: PipeJob with neither → returns empty WM

### B2: Tests first — hydration utility

**File**: `tests/unit/pipelex/temporal/tprl_pipe/test_hydration.py` (NEW)

- `test_hydrate_with_native_text`: raw dict with TextContent stuff → typed TextContent after hydration
- `test_hydrate_empty`: raw dict for empty WM → empty WM
- `test_hydrate_preserves_aliases`: aliases survive round-trip

### B3: Modify PipeJob model

**File**: `pipelex/pipe_run/pipe_job.py`

```python
from typing import Any
from pipelex.pipe_run.exceptions import PipeJobError

class PipeJob(BaseModel):
    pipe: PipeAbstract
    working_memory: WorkingMemory | None = None
    working_memory_raw: dict[str, Any] | None = None
    pipe_run_params: PipeRunParams
    job_metadata: JobMetadata
    output_name: str | None = None
    library_crate: LibraryCrate | None = None

    def get_working_memory(self) -> WorkingMemory:
        if self.working_memory is not None:
            return self.working_memory
        if self.working_memory_raw is not None:
            msg = "WorkingMemory is in raw form and has not been hydrated yet"
            raise PipeJobError(msg)
        return WorkingMemory()

    def prepare_for_temporal(self) -> None:
        if self.library_crate is None:
            return
        if self.working_memory is not None:
            self.working_memory_raw = self.working_memory.model_dump(serialize_as_any=True)
            self.working_memory = None
```

Add `PipeJobError` to `pipelex/pipe_run/exceptions.py`.

### B4: Create hydration utility

**File**: `pipelex/temporal/tprl_pipe/hydration.py` (NEW)

```python
from typing import Any
from pipelex.core.memory.working_memory import WorkingMemory

def hydrate_working_memory(working_memory_raw: dict[str, Any]) -> WorkingMemory:
    """Reconstruct typed WorkingMemory from a raw dict.
    Must be called AFTER load_from_crate() has registered dynamic classes
    and set the scoped ClassRegistry.
    """
    return WorkingMemory.model_validate(working_memory_raw)
```

If `model_validate()` alone doesn't resolve dynamic types (since Pydantic may not use Kajson internally), fallback to kajson round-trip:
```python
from kajson import kajson
raw_json = kajson.dumps(working_memory_raw)
return kajson.loads(raw_json)
```

Determine which approach works during implementation.

### B5: Update direct-mode PipeRouter

**File**: `pipelex/pipe_run/pipe_router.py` (line 21)

```python
# Before:
working_memory=pipe_job.working_memory,
# After:
working_memory=pipe_job.get_working_memory(),
```

### B6: Update Temporal dispatchers

**File**: `pipelex/temporal/tprl_pipe/pipe_router_top.py`

In `_run_pipe_job()`, before `executor.execute_workflow()`:
```python
pipe_job.prepare_for_temporal()
```

**File**: `pipelex/temporal/tprl_pipe/pipe_router_child.py`

In `_run_pipe_job()`, before `executor.execute_child_workflow()`:
```python
pipe_job.prepare_for_temporal()
```

### B7: Update WfPipeRouter — scoped registry + hydration

**File**: `pipelex/temporal/tprl_pipe/wf_pipe_router.py`

```python
from kajson.composite_class_registry import CompositeClassRegistry
from kajson.kajson_manager import KajsonManager

@workflow.run
async def run(self, workflow_arg: PipeJob) -> PipeOutput:
    library_crate = workflow_arg.library_crate
    wf_library_id: str | None = None

    try:
        if library_crate is not None:
            # 1. Create scoped ClassRegistry (local overlay on global)
            global_registry = KajsonManager.get_class_registry()
            scoped_registry = CompositeClassRegistry(parent=global_registry)
            KajsonManager.set_scoped_class_registry(scoped_registry)

            # 2. Load crate (registers dynamic classes into scoped registry)
            library_manager = get_library_manager()
            wf_library_id = f"wf_{workflow.info().workflow_id}"
            library_manager.open_library(library_id=wf_library_id)
            set_current_library(library_id=wf_library_id)
            library_manager.load_from_crate(library_id=wf_library_id, crate=library_crate)

            # 3. Hydrate WorkingMemory (now that classes are registered)
            if workflow_arg.working_memory_raw is not None:
                workflow_arg.working_memory = hydrate_working_memory(workflow_arg.working_memory_raw)
                workflow_arg.working_memory_raw = None

        working_memory = workflow_arg.get_working_memory()
        pipe_output = await pipe.run_pipe(
            working_memory=working_memory,
            library_crate=library_crate,
            ...
        )
    except ActivityError as exc:
        ...
    finally:
        if wf_library_id is not None:
            get_library_manager().teardown(library_id=wf_library_id)
            teardown_current_library()
        if library_crate is not None:
            KajsonManager.set_scoped_class_registry(None)

    return pipe_output
```

### B8: Integration test — dynamic concepts through Temporal

**File**: `tests/integration/pipelex/temporal/library_crate/dynamic_concept_sequence.mthds` (NEW)

A test bundle with:
- A custom concept with inline structure (e.g., `concept Greeting` with `structure: { message: str, language: str }`)
- A PipeSequence that takes input and produces output using this concept

**File**: `tests/integration/pipelex/temporal/library_crate/test_wf_deferred_hydration.py` (NEW)

Pattern (following existing Phase 2 test patterns):
- Load the dynamic concept bundle via `PipelexInterpreter.make_pipelex_bundle_blueprint()`
- Build PipeJob with WorkingMemory containing a Stuff with the dynamic concept content
- Execute via Temporal `execute_workflow(WfPipeRouter.run, arg=pipe_job, ...)`
- Assert output WM has correctly typed Stuff objects with proper StructuredContent
- Also test: two concurrent workflows with same-named but differently-structured concepts don't collide

### B9: Update test data

**File**: `tests/integration/pipelex/temporal/test_data.py`

Add test data class for deferred hydration tests (similar to `LibraryCrateTestData`).

### B10: Lint and test

```bash
make agent-check
make agent-test
```

---

## Key Files Summary

| File | Change |
|------|--------|
| **Kajson** | |
| `kajson/kajson/composite_class_registry.py` | **NEW** — `CompositeClassRegistry` with local+parent layering |
| `kajson/kajson/kajson_manager.py` | Add ContextVar scoping for `get_class_registry()` |
| `kajson/tests/test_composite_class_registry.py` | **NEW** — unit tests |
| **Pipelex** | |
| `pipelex/pipe_run/pipe_job.py` | Add `working_memory_raw`, `get_working_memory()`, `prepare_for_temporal()` |
| `pipelex/pipe_run/exceptions.py` | Add `PipeJobError` |
| `pipelex/temporal/tprl_pipe/hydration.py` | **NEW** — `hydrate_working_memory()` |
| `pipelex/temporal/tprl_pipe/wf_pipe_router.py` | Scoped registry lifecycle + hydration after crate load |
| `pipelex/temporal/tprl_pipe/pipe_router_top.py` | Call `prepare_for_temporal()` before dispatch |
| `pipelex/temporal/tprl_pipe/pipe_router_child.py` | Call `prepare_for_temporal()` before dispatch |
| `pipelex/pipe_run/pipe_router.py` | Use `get_working_memory()` |
| `tests/unit/pipelex/pipe_run/test_pipe_job_hydration.py` | **NEW** |
| `tests/unit/pipelex/temporal/tprl_pipe/test_hydration.py` | **NEW** |
| `tests/integration/pipelex/temporal/library_crate/test_wf_deferred_hydration.py` | **NEW** |
| `tests/integration/pipelex/temporal/library_crate/dynamic_concept_sequence.mthds` | **NEW** |

---

## Edge Cases

- **Empty WorkingMemory**: `prepare_for_temporal()` serializes to `{"root": {}, "aliases": {}}`. Hydration returns empty WM.
- **WM with only native concepts**: Works fine — native classes are in global registry, CompositeClassRegistry finds them via fallback.
- **WM with ListContent of dynamic items**: Items' types resolve after crate loading. CompositeClassRegistry finds them in local registry.
- **No library_crate (direct mode)**: `prepare_for_temporal()` is no-op. No scoped registry created. Everything works as before.
- **Child workflows**: `PipeRouterChild` calls `prepare_for_temporal()`. Child workflow gets its own scoped registry via `WfPipeRouter`.
- **Concurrent workflows with same concept name**: Each gets isolated local registry. No collision.
- **Scoped registry cleanup**: Always cleaned up in `finally` block, even on exception.

---

## Implementation Order

1. **Part A first** (Kajson): CompositeClassRegistry + ContextVar scoping + tests
2. **Install updated Kajson** in Pipelex's venv (editable install from `../kajson`)
3. **Part B** (Pipelex): PipeJob changes → hydration → dispatchers → WfPipeRouter → integration tests
4. **Lint + full test suite**

---

## Verification

1. **Kajson tests pass**: `test_composite_class_registry.py`
2. **PipeJob unit tests pass**: `test_pipe_job_hydration.py`
3. **Hydration unit tests pass**: `test_hydration.py`
4. **Existing Phase 2 tests still pass**: `test_wf_library_crate.py`
5. **New integration test passes**: `test_wf_deferred_hydration.py`
6. **Concurrent workflow isolation verified**: integration test with two workflows using same concept name
7. **`working_memory_raw` visible as plain JSON in Temporal dashboard**
8. **`make agent-check` passes**
9. **`make agent-test` passes**

---

## Done When (from Master Plan + scoping addition)

- [ ] Integration test: PipeSequence with `mthds_content` containing a custom concept with inline structure (dynamic class)
- [ ] `working_memory_raw` hydrates correctly after library setup
- [ ] Stuff objects have correct typed content after hydration
- [ ] `working_memory_raw` is visible as plain JSON in Temporal dashboard
- [ ] Concurrent workflows with same-named concepts don't collide (scoped ClassRegistry)
- [ ] `make agent-check` passes
- [ ] `make agent-test` passes
