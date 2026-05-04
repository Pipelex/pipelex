# Kajson Decoder: ClassRegistry Fallback Not Reached for Dynamic Classes

## Problem

The Kajson JSON decoder (`kajson/json_decoder.py:140-153`) resolves classes in three steps:

1. **Line 140-150**: If `module_name` is in `sys.modules`, use `getattr(sys.modules[module_name], class_name)`. If not found, raise `KajsonDecoderError`.
2. **Line 151-153**: Else, try `KajsonManager.get_class_registry().get_class(name=class_name)`.
3. **Line 155+**: Else, try `importlib.import_module(module_name)` and `getattr`.

The ClassRegistry lookup (step 2) only runs when the module is NOT in `sys.modules`. Dynamic classes generated at runtime (e.g., `GreetingContent` from inline concept structures) are registered in the ClassRegistry with `__module__` set to `"builtins"`. Since `builtins` is always in `sys.modules`, the decoder takes step 1, does `getattr(builtins, "Greeting")`, fails, and raises at line 150 — **never reaching the ClassRegistry fallback at line 151**.

## How It Manifests

In a Temporal PipeSequence with dynamic concepts:

1. Parent workflow dispatches a child workflow (e.g., `generate_greeting` PipeLLM)
2. Child workflow executes successfully, produces `PipeOutput` with `Greeting` StructuredContent
3. Child result is serialized by Kajson with `__class__: "Greeting"`, `__module__: "builtins"`
4. Parent workflow receives the child result — Kajson decoder does `getattr(sys.modules["builtins"], "Greeting")` → `AttributeError` → `KajsonDecoderError` at line 150
5. The ClassRegistry (line 151), which DOES have the `Greeting` class registered, is never consulted

## Why In-Process Tests Pass

The integration test runs the worker in-process (`is_not_sandboxed=True`). The test fixture pre-loads the blueprint globally, which registers the dynamic class in the ClassRegistry. Since the class was generated in the same process, `StructureGenerator` may also place it in a module that makes `getattr` succeed. With a **separate** worker process, the dynamic class is only in the ClassRegistry (loaded from the crate), not in any importable module attribute.

## Verified via Manual Test

Using `/temporal-diagnose` with a 3-process setup (Temporal server + separate worker + job submitter), the `dynamic_concept_sequence.mthds` bundle fails with:

```
KajsonDecoderError: Class 'Greeting' not found in module 'builtins'
```

The worker logs show the child workflow result deserialization failing at `_convert_payloads` in the Temporal SDK, which calls `kajson.loads()`.

## Proposed Solution

In `kajson/json_decoder.py`, when the module IS in `sys.modules` but `getattr` fails (line 149-150), fall back to the ClassRegistry before raising:

```python
# Current (line 149-150):
else:
    raise KajsonDecoderError(f"Class '{class_name}' not found in module '{module_name}'")

# Proposed:
else:
    # Module is loaded but class not found as attribute — try ClassRegistry
    # (handles dynamic classes registered at runtime, including scoped registries)
    registered_class = KajsonManager.get_class_registry().get_class(name=class_name)
    if registered_class is not None:
        the_class = registered_class
    else:
        raise KajsonDecoderError(f"Class '{class_name}' not found in module '{module_name}' or ClassRegistry")
```

This preserves the existing priority (module attribute first, registry second) and only changes behavior when `getattr` fails for a non-generic class.

## Dependencies

- Scoped registry teardown (token-based, see `wip/scoped-registry-teardown.md`) should be implemented first, so the decoder uses the correct scoped registry in concurrent workflow scenarios
- The Kajson decoder change should be tested with both global and scoped registry scenarios
- The `hub.get_class_registry()` → `KajsonManager.get_class_registry()` change (already applied in `pipelex/hub.py`) is complementary — it fixes explicit lookups (e.g., `StuffContentFactory`) while this fix covers Kajson deserialization
