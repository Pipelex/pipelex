# Tier 2 Live Bug: DynamicConceptTestGreeting not found

## The bug

When running Tier 2 (deferred hydration) in **live mode** (real LLM calls), the parent workflow `WfPipeRouter` fails to decode the child workflow `WfMakeObject`'s return value:

```
KajsonDecoderError: Class 'DynamicConceptTestGreeting' not found in module 'builtins' or global registry
```

Dry-run passes because mock data never triggers the real structured output path.

## How to reproduce

```bash
# Start Temporal server + worker, then:
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/dynamic_concept_sequence.mthds \
  --pipe dynamic_greeting_sequence \
  --temporal --no-logo --graph
```

## Execution flow where it breaks

```
WfPipeRouter (parent workflow)
  → set_current_library(wf_library_id)  # sets ContextVar
  → load_from_crate()                   # registers DynamicConceptTestGreeting in workflow-scoped registry
  → PipeSequence.run_pipe()
    → PipeLLM (generate_greeting)
      → ContentGeneratorChild.make_object_direct()
        → WfMakeObject (child workflow)
          → act_llm_gen_object (activity)
            → model_class_from_json_schema() creates class via exec()
            → LLM generates structured Greeting instance
            → Activity returns Greeting (BaseModel subclass)
          → WfMakeObject returns Greeting to parent
        → Temporal calls _convert_payloads to decode child result  ← FAILS HERE
```

## What we verified with diagnostic logs

1. **`to_payload` is NOT called for the Greeting activity return.** Only called for `ObjectAssignment` (activity input). The Greeting is serialized by Temporal's default JSON converter, NOT our `BaseModelPayloadConverter`. Therefore no `kajson_class_source` metadata is attached.

2. **`from_payload` IS called for the child workflow result.** The payload data is:
   ```json
   {"message": "Bonjour le monde", "language": "French", "__class__": "DynamicConceptTestGreeting", "__module__": "builtins"}
   ```
   With `class_source_code: None` (no metadata).

3. **The ContextVar is NOT propagated into `_convert_payloads`.** Temporal's internal `_apply_resolve_child_workflow_execution` → `_convert_payloads` runs outside the workflow coroutine's async context. So `get_class_registry()` falls back to the global KajsonManager registry, which doesn't have the dynamic class.

## Two independent problems

**Problem A: `to_payload` not called for activity results.**
The Greeting returned by `act_llm_gen_object` never passes through our `BaseModelPayloadConverter.to_payload()`. Reason unknown — possibly Temporal SDK uses a different serialization path for activity return values, or the exec'd class isn't recognized as `BaseModel` by the converter's `isinstance` check.

**Problem B: ContextVar not available in `_convert_payloads`.**
Even if `to_payload` worked and attached `kajson_class_source` metadata, the parent workflow's `_convert_payloads` runs in a Temporal-internal context where the `_library_id` ContextVar is not set. So `get_class_registry()` returns the global registry, not the workflow-scoped one.

## What was fixed so far (kajson repo)

**Decoder fallback** in `kajson/json_decoder.py`: When `sys.modules[module_name]` exists but `getattr` fails (the `builtins` case), the decoder now falls through to check `KajsonManager.get_class_registry()` before raising. Previously it raised immediately. This fix is correct but insufficient alone — the class isn't in the global registry either.

Test: `kajson/tests/unit/test_global_registry_fallback.py` — passes.

## What was NOT fixed

The `_collect_class_sources` helper added to `temporal_data_converter.py` is irrelevant since `to_payload` isn't called for the Greeting. The debug logs added should be removed.
