# Tier 2 Live: ContextVar Registry Doesn't Cross Temporal Boundaries

**Status:** Open — needs architectural decision
**Branch:** `fix/Temporal-Img`
**Date:** 2026-04-01

## What works

- Tier 2 **dry-run** passes (no real LLM calls, `ObjectAssignment` never hits the structured output path)
- Tiers 1, 3, 4, 5 pass in both dry-run and live mode
- The `ObjectAssignment.__init__` deserialization fix (removing the eager class registry check) is correct and already applied on this branch

## What fails

Tier 2 **live** — `dynamic_concept_sequence.mthds` with `--pipe dynamic_greeting_sequence` through Temporal.

The bundle defines a dynamic concept `Greeting` (with `message` and `language` fields) and a `PipeLLM` that outputs structured data into that concept using `structuring_method = "direct"`.

## Error

```
Class 'dynamic_concept_test__Greeting' not found in registry
```

Thrown from `llm_generate.py:32`:
```python
content_class = get_class_registry().get_required_base_model(name=content_class_name)
```

## Root cause

`get_class_registry()` uses a `ContextVar` (`_library_id` in `hub.py:462`) to resolve the workflow-scoped registry. But ContextVars don't propagate across Temporal's execution boundaries:

```
WfPipeRouter (ContextVar set here via set_current_library)
  → pipe.run_pipe()
    → ContentGeneratorChild.make_object_direct()
      → child workflow WfMakeObject (NEW async context — ContextVar is None)
        → activity act_llm_gen_object (ANOTHER context — ContextVar is None)
          → llm_gen_object()
            → get_class_registry() → returns GLOBAL registry → class not found
```

The dynamic concept class `dynamic_concept_test__Greeting` was registered in `WfPipeRouter`'s **workflow-scoped** `ClassRegistry`. But two hops later — inside the activity of a child workflow — `get_class_registry()` returns the **global** registry, which doesn't have it.

## Why dry-run works

In dry-run mode, `PipeLLM` never reaches `ContentGeneratorChild.make_object_direct()` — the dry-run path generates mock output without calling the LLM, so it never needs to look up the dynamic class from the registry inside an activity.

## Why other tiers aren't affected

- **Tier 1** (native text sequence): Uses `PipeLLM` with `Text` output (a native concept, always in the global registry). No structured output, no `ObjectAssignment`.
- **Tier 3** (parallel): Same — text-only pipes, no dynamic concepts in structured output position.
- **Tiers 4-5** (image): Image generation doesn't go through `ObjectAssignment` or `llm_gen_object`. Images use `ImgGenAssignment` → `act_img_gen` which doesn't need the class registry.

## Fix already applied on this branch

Removed `ObjectAssignment.__init__` class registry validation (`assignment_models.py:90-94`). This was causing a **separate** deserialization failure: when Temporal's data converter called `kajson.loads()` to deserialize the `ObjectAssignment` argument for `WfMakeObject`, pydantic called `__init__` which checked the registry. Removing it fixed the deserialization, but the same lookup fails later in the activity.

## Approach options

### A) Embed the class schema in ObjectAssignment

Add the Pydantic model's JSON schema (or the field definitions) as a field on `ObjectAssignment`. The activity reconstructs the class locally from the schema without needing the registry. This is the "carry everything you need" pattern, similar to how `LibraryCrate` carries pipe definitions.

**Pros:** Self-contained, no cross-boundary coupling, works for any Temporal topology.
**Cons:** Increases payload size, needs a "reconstruct Pydantic class from schema" utility.

### B) Propagate library_id through Temporal headers

Use Temporal's workflow/activity interceptors to copy the `_library_id` ContextVar into Temporal headers on dispatch, and restore it on the receiving end. This is the transparent approach.

**Pros:** No changes to assignment models, ContextVar "just works" across boundaries.
**Cons:** Requires Temporal interceptor infrastructure, the receiving side still needs access to the same `LibraryManager` state (child workflows and activities must be on the same worker).

### C) Pre-register dynamic classes in the global registry

When `WfPipeRouter.load_from_crate()` runs, also register dynamic classes in the global registry (not just the workflow-scoped one). Clean up on workflow teardown.

**Pros:** Simplest change, everything finds the class.
**Cons:** Breaks per-workflow isolation — concurrent workflows with conflicting class names will clobber each other (exactly the bug the scoped registry was designed to prevent).

### D) WfMakeObject loads the crate itself

Pass the `LibraryCrate` to `WfMakeObject` alongside the `ObjectAssignment`. The child workflow sets up its own scoped registry before the activity runs.

**Pros:** Reuses existing crate-loading pattern from `WfPipeRouter`.
**Cons:** Increases child workflow payload, adds setup/teardown overhead to every structured output call.

## Key files

| File | Role |
|------|------|
| `pipelex/hub.py:381-386, 462-467` | `get_class_registry()` and `_library_id` ContextVar |
| `pipelex/temporal/tprl_pipe/wf_pipe_router.py:46-68` | Crate loading and registry setup |
| `pipelex/temporal/tprl_content_generation/wf_make_object.py` | Child workflow receiving `ObjectAssignment` |
| `pipelex/cogt/content_generation/llm_generate.py:32` | Activity calling `get_class_registry()` |
| `pipelex/cogt/content_generation/assignment_models.py:86` | `ObjectAssignment` model (init check removed) |
| `pipelex/temporal/temporal_data_converter.py:77` | Kajson deserialization using `get_class_registry()` |
| `tests/integration/pipelex/temporal/library_crate/dynamic_concept_sequence.mthds` | Test bundle |

## Reproduction

```bash
# Start Temporal server + worker
tmux new-session -d -s temporal-server 'temporal server start-dev'
sleep 3
tmux new-session -d -c "$PWD" -s temporal-worker \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed'
sleep 4

# This passes (dry-run)
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/dynamic_concept_sequence.mthds \
  --pipe dynamic_greeting_sequence \
  --temporal --dry-run --mock-inputs --no-logo

# This fails (live)
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/dynamic_concept_sequence.mthds \
  --pipe dynamic_greeting_sequence \
  --temporal --no-logo
```
