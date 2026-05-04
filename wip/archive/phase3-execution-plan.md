# Phase 3 Execution Plan: Deferred WorkingMemory Hydration + Scoped ClassRegistry

## Context

Phase 3 solves two problems for Temporal workers with custom concepts:
1. **Chicken-and-egg deserialization** — WorkingMemory contains dynamic StructuredContent subclasses that don't exist yet when Temporal deserializes PipeJob on the worker
2. **Global ClassRegistry collision** — concurrent workflows on the same worker could overwrite each other's class registrations

The eng review resolved the hydration approach: use `smart_dump()` → `dict[str, Any]` with concept-based reconstruction (not kajson round-trip).

---

## Implementation Order

### Part A: Kajson (separate repo at `/Users/lchoquel/repos/Pipelex/kajson/`)

#### A1: CompositeClassRegistry
**New file**: `kajson/kajson/composite_class_registry.py`

A `ClassRegistryAbstract` implementation wrapping local `ClassRegistry` + parent registry:
- Constructor takes `parent: ClassRegistryAbstract`; creates internal `_local: ClassRegistry`
- **Getters** (local-first, parent-fallback): `get_class()`, `get_required_class()`, `get_required_subclass()`, `get_required_base_model()`, `has_class()`, `has_subclass()`
- **Mutators** (local-only): `register_class()`, `register_classes()`, `register_classes_dict()`, `unregister_class()`, `unregister_class_by_name()`
- **Lifecycle**: `setup()` → no-op, `teardown()` → `_local.teardown()` (never touch parent)

Reference: `kajson/kajson/class_registry.py` for all method signatures and behaviors.

#### A2: ContextVar scoping in KajsonManager
**Modify**: `kajson/kajson/kajson_manager.py`

```python
from contextvars import ContextVar

_scoped_class_registry: ContextVar[ClassRegistryAbstract | None] = ContextVar(
    "_scoped_class_registry", default=None
)

class KajsonManager(metaclass=MetaSingleton):
    # existing __init__, get_instance, teardown...

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

#### A3: Tests for CompositeClassRegistry
**New file**: `kajson/tests/unit/test_composite_class_registry.py`

Tests (single TestClass):
- `test_local_lookup_takes_priority` — same name in both, local wins
- `test_fallback_to_parent` — name only in parent, found via composite
- `test_registration_goes_to_local_only` — register via composite, parent unchanged
- `test_teardown_clears_local_only` — teardown, parent untouched
- `test_has_class_checks_both` — name in parent, `has_class()` returns True
- `test_unregister_from_local_only` — unregister from composite, parent unaffected
- `test_get_required_base_model_delegation` — local-first, parent-fallback
- `test_scoped_context_var` — set/unset scoped registry on KajsonManager

#### A4: Install updated Kajson
```bash
cd /Users/lchoquel/repos/Pipelex/_temporal
pip install -e ../kajson
```

---

### Part B: Pipelex (at `/Users/lchoquel/repos/Pipelex/_temporal/`)

#### B1: Add PipeJobError
**Modify**: `pipelex/pipe_run/exceptions.py`

```python
class PipeJobError(PipelexError):
    pass
```

#### B2: Modify PipeJob model
**Modify**: `pipelex/pipe_run/pipe_job.py`

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

    @property
    def pipe_type(self) -> str:
        return self.pipe.__class__.__name__

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
            self.working_memory_raw = self.working_memory.smart_dump()
            self.working_memory = None
```

#### B3: Unit tests for PipeJob
**New file**: `tests/unit/pipelex/pipe_run/test_pipe_job_hydration.py`

Tests using simple TextContent stuffs (no dynamic classes needed):
- `test_prepare_for_temporal_moves_wm_to_raw`
- `test_prepare_for_temporal_noop_without_crate`
- `test_prepare_for_temporal_empty_wm`
- `test_get_working_memory_from_typed`
- `test_get_working_memory_from_raw_raises`
- `test_get_working_memory_both_none_returns_empty`

Needs a minimal PipeJob fixture — use existing PipeAbstract subclass (e.g., PipeLLM) with mock data, and a LibraryCrate fixture.

#### B4: Hydration utility
**New file**: `pipelex/temporal/tprl_pipe/hydration.py`

Concept-based hydration following `StuffContentFactory.make_stuff_content_from_concept_required()` pattern:

```python
from typing import Any
from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_content_factory import StuffContentFactory
from pipelex.core.stuffs.text_content import TextContent

def hydrate_working_memory(working_memory_raw: dict[str, Any]) -> WorkingMemory:
    """Reconstruct typed WorkingMemory from a raw dict.

    Must be called AFTER load_from_crate() has registered dynamic classes
    in the scoped ClassRegistry.
    """
    working_memory = WorkingMemory()

    raw_root = working_memory_raw.get("root", {})
    for stuff_name, stuff_dict in raw_root.items():
        concept = Concept.model_validate(stuff_dict["concept"])
        content = StuffContentFactory.make_stuff_content_from_concept_required(
            concept=concept,
            value=stuff_dict["content"],
        )
        stuff = Stuff(
            stuff_code=stuff_dict["stuff_code"],
            stuff_name=stuff_dict.get("stuff_name"),
            concept=concept,
            content=content,
        )
        working_memory.root[stuff_name] = stuff

    working_memory.aliases = working_memory_raw.get("aliases", {})
    return working_memory
```

Key insight: `StuffContentFactory.make_stuff_content_from_concept_required()` already does `concept.structure_class_name` → ClassRegistry lookup → `model_validate()`. We reuse it.

#### B5: Hydration unit tests
**New file**: `tests/unit/pipelex/temporal/tprl_pipe/test_hydration.py`

Tests (require boot to have concepts loaded):
- `test_hydrate_with_native_text` — raw dict with TextContent → typed TextContent
- `test_hydrate_empty` — raw dict for empty WM → empty WM
- `test_hydrate_preserves_aliases` — aliases survive round-trip

#### B6: Update direct-mode PipeRouter
**Modify**: `pipelex/pipe_run/pipe_router.py` line 21

```python
# Before:
working_memory=pipe_job.working_memory,
# After:
working_memory=pipe_job.get_working_memory(),
```

#### B7: Update Temporal dispatchers
**Modify**: `pipelex/temporal/tprl_pipe/pipe_router_top.py`

In `_run_pipe_job()`, before `executor.execute_workflow()`:
```python
pipe_job.prepare_for_temporal()
```

**Modify**: `pipelex/temporal/tprl_pipe/pipe_router_child.py`

In `_run_pipe_job()`, before `executor.execute_child_workflow()`:
```python
pipe_job.prepare_for_temporal()
```

#### B8: Update WfPipeRouter — scoped registry + hydration
**Modify**: `pipelex/temporal/tprl_pipe/wf_pipe_router.py`

Add imports inside `workflow.unsafe.imports_passed_through()`:
```python
from kajson.composite_class_registry import CompositeClassRegistry
from kajson.kajson_manager import KajsonManager
from pipelex.temporal.tprl_pipe.hydration import hydrate_working_memory
```

Update `run()`:
```python
try:
    if library_crate is not None:
        # 1. Create scoped ClassRegistry
        global_registry = KajsonManager.get_class_registry()
        scoped_registry = CompositeClassRegistry(parent=global_registry)
        KajsonManager.set_scoped_class_registry(scoped_registry)

        # 2. Load crate (registers dynamic classes into scoped registry)
        library_manager = get_library_manager()
        wf_library_id = f"wf_{workflow.info().workflow_id}"
        library_manager.open_library(library_id=wf_library_id)
        set_current_library(library_id=wf_library_id)
        library_manager.load_from_crate(library_id=wf_library_id, crate=library_crate)

        # 3. Hydrate WorkingMemory
        if workflow_arg.working_memory_raw is not None:
            workflow_arg.working_memory = hydrate_working_memory(workflow_arg.working_memory_raw)
            workflow_arg.working_memory_raw = None

    working_memory = workflow_arg.get_working_memory()
    pipe_output = await pipe.run_pipe(
        working_memory=working_memory,
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
```

#### B9: Integration test — dynamic concepts through Temporal
**New file**: `tests/integration/pipelex/temporal/library_crate/dynamic_concept_sequence.mthds`

A test bundle with a custom concept with inline structure, e.g.:
```toml
[domain]
code = "dynamic_concept_test"

[concepts.Greeting]
structure.message = "str"
structure.language = "str"

[pipes.greet]
type = "PipeLLM"
# ... produces a Greeting
```

**Add to**: `tests/integration/pipelex/temporal/test_data.py`

```python
class DeferredHydrationTestData:
    BUNDLE_FILE: ClassVar[str] = str(Path(__file__).parent / "library_crate" / "dynamic_concept_sequence.mthds")
    PIPE_CODE: ClassVar[str] = "dynamic_greeting_sequence"
    DOMAIN: ClassVar[str] = "dynamic_concept_test"
```

**New file**: `tests/integration/pipelex/temporal/library_crate/test_wf_deferred_hydration.py`

Following existing Phase 2 test patterns:
- Load dynamic concept bundle via `PipelexInterpreter.make_pipelex_bundle_blueprint()`
- Build PipeJob with WorkingMemory (may be empty or contain input stuff)
- Execute via Temporal workflow
- Assert output has correctly typed Stuff with StructuredContent (field-by-field assertions)

#### B10: Lint and test
```bash
make agent-check
make agent-test
```

---

## File Summary

| File | Change |
|------|--------|
| **Kajson** | |
| `kajson/kajson/composite_class_registry.py` | **NEW** — CompositeClassRegistry |
| `kajson/kajson/kajson_manager.py` | Add ContextVar scoping |
| `kajson/tests/unit/test_composite_class_registry.py` | **NEW** — unit tests |
| **Pipelex** | |
| `pipelex/pipe_run/exceptions.py` | Add PipeJobError |
| `pipelex/pipe_run/pipe_job.py` | Add raw field, get_working_memory(), prepare_for_temporal() |
| `pipelex/pipe_run/pipe_router.py` | Use get_working_memory() |
| `pipelex/temporal/tprl_pipe/hydration.py` | **NEW** — concept-based hydration |
| `pipelex/temporal/tprl_pipe/pipe_router_top.py` | Call prepare_for_temporal() |
| `pipelex/temporal/tprl_pipe/pipe_router_child.py` | Call prepare_for_temporal() |
| `pipelex/temporal/tprl_pipe/wf_pipe_router.py` | Scoped registry + hydration |
| `tests/unit/pipelex/pipe_run/test_pipe_job_hydration.py` | **NEW** |
| `tests/unit/pipelex/temporal/tprl_pipe/test_hydration.py` | **NEW** |
| `tests/integration/pipelex/temporal/test_data.py` | Add DeferredHydrationTestData |
| `tests/integration/pipelex/temporal/library_crate/dynamic_concept_sequence.mthds` | **NEW** |
| `tests/integration/pipelex/temporal/library_crate/test_wf_deferred_hydration.py` | **NEW** |

---

## Verification

1. Kajson unit tests pass: `test_composite_class_registry.py`
2. PipeJob unit tests pass: `test_pipe_job_hydration.py`
3. Hydration unit tests pass: `test_hydration.py`
4. Existing Phase 2 tests still pass: `test_wf_library_crate.py`
5. New integration test passes: `test_wf_deferred_hydration.py`
6. `make agent-check` passes
7. `make agent-test` passes
