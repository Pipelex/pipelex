# Scoped Registry Teardown: ContextVar Token Save/Restore

## Problem

In `pipelex/temporal/tprl_pipe/wf_pipe_router.py`, the scoped ClassRegistry cleanup in the `finally` block unconditionally sets the scoped registry to `None`:

```python
finally:
    if library_crate is not None:
        KajsonManager.set_scoped_class_registry(None)
```

This is not stack-safe. If a nested or re-entrant workflow sets its own scoped registry, the inner workflow's `finally` block resets to `None`, clobbering the outer workflow's scoped registry. The outer workflow then resolves classes from the global registry instead of its own scoped registry, potentially getting the wrong class definitions.

## Proposed Solution

Use Python's `ContextVar` token save/restore mechanism. `ContextVar.set()` returns a `Token` object, and `ContextVar.reset(token)` restores the value that was in effect before that `set()` call. This is the standard pattern for push/pop scoping with ContextVars.

### Changes to Kajson (`kajson/kajson/kajson_manager.py`)

1. Import `Token` from `contextvars`
2. Change `set_scoped_class_registry` to return the Token:

```python
from contextvars import ContextVar, Token

@classmethod
def set_scoped_class_registry(cls, registry: ClassRegistryAbstract | None) -> Token[ClassRegistryAbstract | None]:
    return _scoped_class_registry.set(registry)
```

3. Add a `reset_scoped_class_registry` method:

```python
@classmethod
def reset_scoped_class_registry(cls, token: Token[ClassRegistryAbstract | None]) -> None:
    _scoped_class_registry.reset(token)
```

### Changes to Pipelex (`pipelex/temporal/tprl_pipe/wf_pipe_router.py`)

```python
registry_token = None
try:
    if library_crate is not None:
        global_registry = KajsonManager.get_class_registry()
        scoped_registry = CompositeClassRegistry(parent=global_registry)
        registry_token = KajsonManager.set_scoped_class_registry(scoped_registry)
        # ... load crate, hydrate WM ...

    # ... run pipe ...
finally:
    # ... library teardown ...
    if registry_token is not None:
        KajsonManager.reset_scoped_class_registry(registry_token)
```

### Why Token-Based

- The guard changes from `if library_crate is not None` to `if registry_token is not None`, which is more precise (only resets if we actually set a scoped registry)
- Properly handles nesting: inner workflow restores to outer's scoped registry, not to `None`
- Standard Python pattern for ContextVar scoping — no custom stack management needed

### Impact on Existing Code

- `set_scoped_class_registry` return type changes from `None` to `Token`. This is backward-compatible for callers that discard the return value. No existing callers check the return value.
- The Kajson unit tests (`test_scoped_context_var`) should be updated to verify the token-based reset restores the previous value.
