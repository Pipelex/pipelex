# Plan: Explicit ClassRegistry — No Singleton Scoping in Kajson

## Context

Phase 3 (deferred WorkingMemory hydration + scoped ClassRegistry) works with in-process tests but fails with separate Temporal workers due to two bugs:

1. **Decoder bypass**: `json_decoder.py:140-150` never reaches the ClassRegistry fallback for dynamic classes because `builtins` is always in `sys.modules`
2. **Teardown clobber**: `wf_pipe_router.py` sets the scoped registry to `None` in `finally`, which isn't stack-safe for nested workflows

Both bugs stem from the same architectural weakness: kajson (a serialization library) owns workflow-scoping concerns via a ContextVar singleton. The fix is to move scoping out of kajson entirely, tie the ClassRegistry to the Library lifecycle (where it logically belongs), and give kajson an explicit `class_registry` parameter.

## Design Principles

- **Kajson is a pure library**: no ContextVars, no workflow scoping. Accepts explicit `class_registry` parameter.
- **Library owns its ClassRegistry**: each Library (loaded from a crate) gets a pre-seeded ClassRegistry containing global + dynamic classes. No CompositeClassRegistry needed — just a flat dict.
- **Reuse existing `_library_id` ContextVar**: `hub.get_class_registry()` reads the active library_id, gets that library's ClassRegistry. No new ContextVar.
- **Explicit at the boundary**: `temporal_data_converter` passes the registry explicitly to `kajson.loads()`.

## Changes

### 1. Kajson — Add explicit `class_registry` param, remove scoping

**`kajson/kajson.py`** — `loads()` and `load()` accept optional `class_registry`
```python
def loads(json_string, class_registry=None, **kwargs):
    if class_registry is not None:
        kwargs["class_registry"] = class_registry
    return json.loads(json_string, cls=UniversalJSONDecoder, **kwargs)
```
Same for `load()`.

**`kajson/json_decoder.py`** — Decoder uses explicit registry first
```python
def __init__(self, *args, **kwargs):
    self._class_registry = kwargs.pop("class_registry", None)
    json.JSONDecoder.__init__(self, object_hook=self.universal_decoder, *args, **kwargs)
    self.logger = logging.getLogger(DECODER_LOGGER_CHANNEL_NAME)
```

In `universal_decoder()` class resolution (lines 139-172), add a new first step:
```python
# Step 0: Check explicit registry first (handles dynamic classes)
if self._class_registry is not None:
    registered_class = self._class_registry.get_class(name=class_name)
    if registered_class is not None:
        the_class = registered_class
        # skip to decoder strategies (line 174)
```
If not found in explicit registry, fall through to existing logic (sys.modules → global registry → importlib).

**`kajson/kajson_manager.py`** — Remove ContextVar and scoped methods
- Delete `_scoped_class_registry` ContextVar
- Delete `set_scoped_class_registry()` method
- `get_class_registry()` simply returns `cls.get_instance()._class_registry` (global only)

**`kajson/composite_class_registry.py`** — Keep file, stop using it. Can be removed in a follow-up.

### 2. Pipelex — Library owns its ClassRegistry (PrivateAttr)

**`pipelex/libraries/library.py`** — Add ClassRegistry as a PrivateAttr on Library:
```python
from pydantic import PrivateAttr
from kajson.class_registry import ClassRegistry

class Library(BaseModel):
    # ... existing fields ...
    _class_registry: ClassRegistry | None = PrivateAttr(default=None)

    def get_class_registry(self) -> ClassRegistry | None:
        return self._class_registry

    def set_class_registry(self, class_registry: ClassRegistry) -> None:
        self._class_registry = class_registry
```

PrivateAttr keeps it off the Pydantic serialization path (no impact on `model_dump()`, validation, or crate serialization). The registry lives and dies with the Library — when `teardown()` deletes the Library from `_libraries`, the registry is GC'd with it. No parallel dicts, no sync risk, no memory leaks.

**`pipelex/libraries/library_manager.py`** — Accessor for convenience:
```python
def get_library_class_registry(self, library_id: str) -> ClassRegistry | None:
    library = self._libraries.get(library_id)
    if library is not None:
        return library.get_class_registry()
    return None
```

No changes needed in `teardown()` — the Library's deletion handles cleanup automatically.

### 3. Pipelex — `hub.get_class_registry()` reads from Library

**`pipelex/hub.py:381-388`** — Replace KajsonManager delegation with library lookup:
```python
def get_class_registry() -> ClassRegistryAbstract:
    library_id = _library_id.get()
    if library_id is not None:
        registry = get_library_manager().get_library_class_registry(library_id)
        if registry is not None:
            return registry
    return get_pipelex_hub().get_required_class_registry()
```

Remove `from kajson.kajson_manager import KajsonManager` from hub.py if no longer needed (check other usages first).

### 4. Pipelex — wf_pipe_router uses plain ClassRegistry

**`pipelex/temporal/tprl_pipe/wf_pipe_router.py`** — Rewrite scoping:

```python
# Remove CompositeClassRegistry and KajsonManager imports
# Add: from kajson.class_registry import ClassRegistry

try:
    if library_crate is not None:
        # 1. Create per-workflow ClassRegistry pre-seeded from global
        global_registry = get_pipelex_hub().get_required_class_registry()
        workflow_registry = ClassRegistry()
        workflow_registry.register_classes_dict(dict(global_registry.root))  # copy global entries

        # 2. Open library and attach registry to it
        library_manager = get_library_manager()
        wf_library_id = f"wf_{workflow.info().workflow_id}"
        _wf_library_id, wf_library = library_manager.open_library(library_id=wf_library_id)
        wf_library.set_class_registry(workflow_registry)
        set_current_library(library_id=wf_library_id)

        # 3. Load crate (registers dynamic classes into workflow_registry via hub.get_class_registry())
        library_manager.load_from_crate(library_id=wf_library_id, crate=library_crate)

        # 4. Hydrate WorkingMemory
        if workflow_arg.working_memory_raw is not None:
            workflow_arg.working_memory = hydrate_working_memory(workflow_arg.working_memory_raw)
            workflow_arg.working_memory_raw = None

    # ... run pipe ...

finally:
    if wf_library_id is not None:
        get_library_manager().teardown(library_id=wf_library_id)  # cleans up registry too
        teardown_current_library()
    # No KajsonManager.set_scoped_class_registry(None) needed!
```

Key insight: `set_current_library()` sets `_library_id` ContextVar. From that point, all calls to `hub.get_class_registry()` return `workflow_registry`. When `concept_factory` calls `KajsonManager.get_class_registry().register_class(...)`, it still hits the global. We need to migrate those callers.

### 5. Migrate KajsonManager.get_class_registry() callers to hub

All ~20 call sites in Pipelex that use `KajsonManager.get_class_registry()` must switch to `hub.get_class_registry()` (or receive the registry explicitly). This is a mechanical change.

**Files to update** (import `get_class_registry` from `pipelex.hub` instead of `KajsonManager` from `kajson`):

| File | Lines | Change |
|------|-------|--------|
| `pipelex/core/concepts/concept_factory.py` | 323, 359, 405, 435 | `get_class_registry().register_class(...)` |
| `pipelex/core/concepts/concept.py` | 132, 133, 162, 165, 175, 183 | `get_class_registry().get_class(...)` etc. |
| `pipelex/core/concepts/structure_generation/generator.py` | 585 | `get_class_registry().get_class(...)` |
| `pipelex/core/pipes/pipe_factory.py` | 110 | `get_class_registry().get_required_subclass(...)` |
| `pipelex/libraries/library_manager.py` | 1134, 1165 | `get_class_registry()` |
| `pipelex/system/registries/class_registry_utils.py` | 37, 148 | `get_class_registry()` |
| `pipelex/tools/typing/structure_printer.py` | 26 | `get_class_registry()` |
| `pipelex/pipe_operators/func/pipe_func.py` | 104 | `get_class_registry().get_class(...)` |
| `pipelex/cli/commands/build/structures_cmd.py` | 194, 243, 270 | `get_class_registry().register_class(...)` |

Each file: replace `KajsonManager.get_class_registry()` with `get_class_registry()` imported from `pipelex.hub`. Remove unused `KajsonManager` import if nothing else uses it.

### 6. Temporal data converter — explicit parameter

**`pipelex/temporal/temporal_data_converter.py`** — Pass registry to `kajson.loads()`:

```python
from pipelex.hub import get_class_registry

def _kajson_deserialize_from_payload(self, payload: Payload) -> Any:
    data = payload.data.decode()
    log.verbose(f"unijson_deserialize_payload — data: {data}")
    pydantic_gizmo = kajson.loads(data, class_registry=get_class_registry())
    log.verbose(f"unijson_deserialize_payload — pydantic_gizmo: {pydantic_gizmo}")
    return pydantic_gizmo
```

### 7. Tests

**Kajson tests** (`tests/unit/test_composite_class_registry.py`):
- Update `test_scoped_context_var` — this test uses `set_scoped_class_registry` which is removed. Replace with a test that verifies `kajson.loads(data, class_registry=custom_reg)` resolves from the explicit registry.

**Pipelex tests** (`tests/unit/pipelex/temporal/tprl_pipe/test_hydration.py`):
- Update to reflect new ClassRegistry setup (no CompositeClassRegistry)

**Pipelex tests** (`tests/unit/pipelex/pipe_run/test_pipe_job_hydration.py`):
- Verify no breakage

**New test**: test that `kajson.loads()` with explicit `class_registry` finds dynamic classes even when `__module__` is `"builtins"` (the exact bug scenario).

## Verification

1. **Lint + type check**: `make agent-check` in both kajson and _temporal
2. **Unit tests**: `make agent-test` in both repos
3. **Manual Temporal test**: Use `/temporal-diagnose` with 3-process setup (server + separate worker + submitter) using `dynamic_concept_sequence.mthds` — this is the test that currently fails with `KajsonDecoderError: Class 'Greeting' not found in module 'builtins'`

## Key Files

| Repo | File | Purpose |
|------|------|---------|
| kajson | `kajson/kajson.py` | Add `class_registry` param to `loads()`/`load()` |
| kajson | `kajson/json_decoder.py` | Accept + use explicit registry in decoder |
| kajson | `kajson/kajson_manager.py` | Remove ContextVar, simplify to global-only |
| _temporal | `pipelex/hub.py` | `get_class_registry()` reads from library |
| _temporal | `pipelex/temporal/tprl_pipe/wf_pipe_router.py` | Plain ClassRegistry, library-associated |
| _temporal | `pipelex/temporal/temporal_data_converter.py` | Pass explicit registry to `kajson.loads()` |
| _temporal | `pipelex/libraries/library.py` | PrivateAttr ClassRegistry on Library |
| _temporal | `pipelex/libraries/library_manager.py` | Accessor for library's ClassRegistry |
| _temporal | ~9 files | Migrate `KajsonManager.get_class_registry()` → `hub.get_class_registry()` |
