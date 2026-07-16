# Nested CompositeContent hydration is not recursive across the runtime bridge

**Status:** Deferred follow-up (confirmed defect, deliberately not fixed in the v0.37.0 release). Flagged by codex and cubic on PR #1020.

## Problem

The transport encode side recurses, the hydration side doesn't:

- **Encode** (`pipelex/core/memory/working_memory.py`): `_encode_composite_for_transport` sends every composite component through `_encode_content_with_class_markers`, which recurses back into `_encode_composite_for_transport` when the component is itself a `CompositeContent`. Inner components are correctly stamped with `__pipelex_class__` / `__pipelex_module__` markers at every depth.
- **Hydrate** (`pipelex/runtime_bridge/primitives/hydration.py`): `_hydrate_list_item`'s marker branch strips the markers only at the top level and calls `item_class.model_validate(clean_item)`. When `item_class` is a `CompositeContent` subclass (extra="allow" — no annotations to drive validation), the inner components are left as raw marker-bearing dicts instead of typed `StuffContent`.

Consequence: a `CompositeContent` nested inside another `CompositeContent` (e.g. a `PipeParallel` result feeding another parallel's combine, crossing the Temporal/runtime-bridge boundary via `dump_for_transport()` → `hydrate_working_memory()`) round-trips with corrupted typed access — downstream `rendered_*` calls and type checks see dicts with `__pipelex_*` keys.

One level of composite (the common case, top-level composite stuff) hydrates correctly via `hydrate_content`'s composite branch; only *nested* composites are affected.

## Proposed fix

In `_hydrate_list_item` (hydration.py), in the marker branch: after resolving `item_class` and building `clean_item`, when `issubclass(item_class, CompositeContent)`, map each value of `clean_item` through the existing `_hydrate_composite_component` before `model_validate`. The mutual recursion `_hydrate_composite_component` ↔ `_hydrate_list_item` then handles arbitrary nesting depth.

## Test shape (TDD)

In `tests/unit/pipelex/runtime_bridge/primitives/test_hydration.py`: build a `WorkingMemory` whose main stuff is a `CompositeContent` containing (a) a nested `CompositeContent` component and (b) a list-of-composites component; run `dump_for_transport()` → `json.dumps`/`json.loads` → `hydrate_working_memory()`; assert every nested component is a typed `StuffContent` instance and no `__pipelex_class__` / `__pipelex_module__` key survives anywhere in the tree.
