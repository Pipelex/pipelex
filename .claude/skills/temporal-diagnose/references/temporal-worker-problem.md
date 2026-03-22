# Temporal Worker Library Problem

## The Bug

When pipelex runs pipe controllers (PipeSequence, PipeCondition, PipeBatch, PipeParallel, SubPipe) via Temporal, they fail because the library is not loaded on the worker process. The missing library causes two cascading failures.

## Root Cause

```
API Process                                    Temporal Worker
─────────────────────────────────────────     ──────────────────────────────
PipelexRunner.execute_pipeline()
  ├─ pipeline_run_setup()
  │   ├─ Loads library (library_manager)      (empty here)
  │   ├─ Generates dynamic concept classes    (classes don't exist here)
  │   ├─ Registers them with Kajson           (Kajson registry incomplete here)
  │   ├─ Resolves pipe by code                (can't resolve here)
  │   └─ Creates PipeJob (top-level pipe)
  └─ PipeRouterTop sends PipeJob ──────────►  WfPipeRouter.run(pipe_job)
     to Temporal                                ├─ Kajson deserializes PipeJob
                                                │   └─ FAILS (Layer 1): unknown class
                                                └─ pipe.run_pipe()
                                                     └─ get_required_pipe() FAILS (Layer 2)
```

1. `pipeline_run_setup()` loads the library into an in-memory `library_manager` singleton — **only in the API process**.
2. During library loading, `ConceptFactory` dynamically generates Python classes for concepts defined in `.mthds` bundles (e.g., `RawText = "Raw input text..."` generates a `RawText` class inheriting from `TextContent`) and registers them with Kajson's class registry.
3. The `PipeJob` is serialized via Kajson, which embeds `__class__` / `__module__` metadata for all Pydantic objects — including these dynamically-generated concept classes.
4. On the worker, the library was never loaded → these dynamic classes don't exist → **Kajson deserialization fails** before the workflow even starts (Layer 1).
5. Even if deserialization succeeded, child pipes are referenced **by code** via `get_required_pipe()`, which queries the empty `library_manager` singleton (Layer 2).
6. Temporal can replay workflows on different workers, so any side-effect library state is lost.

## Key Code Paths

| What | Where |
|------|-------|
| Library loading | `pipelex/pipeline/pipeline_run_setup.py` → `library_manager` |
| Dynamic concept class generation | `pipelex/core/concepts/concept_factory.py` → `_handle_basic_blueprint()` |
| Structure generator (creates the classes) | `pipelex/core/concepts/structure_generation/generator.py` |
| Kajson class registration | `pipelex/pipelex.py:353` (CoreRegistryModels) + `concept_factory.py:359` (dynamic) |
| Kajson data converter (Temporal serde) | `pipelex/temporal/temporal_data_converter.py` |
| `get_required_pipe()` | `pipelex/hub.py:511` |
| Callers that break (Layer 2) | `pipelex/pipe_controllers/sequence/pipe_sequence.py`, `condition/pipe_condition.py`, `batch/pipe_batch.py`, `parallel/pipe_parallel.py`, `sub_pipe.py` |
| Workflow definition | `pipelex/temporal/tprl_pipe/wf_pipe_router.py` |
| Router (Temporal) | `pipelex/temporal/tprl_pipe/pipe_router_top.py` |
| Router (local) | `pipelex/pipe_run/pipe_router.py` |
| Worker CLI | `pipelex/temporal/worker_cli.py` |

## What the Library Contains

- **Base libraries** — shared pipe/concept definitions from `PIPELEXPATH` directories. Same for all executions.
- **Custom bundles** — per-request `mthds_contents` (MTHDS bundle strings). Each API call can bring its own definitions.

## What Library Loading Does (beyond populating pipes)

Loading a library also **generates dynamic Python classes** for concepts. When a `.mthds` file
declares a simple concept like `RawText = "Raw input text..."`, `ConceptFactory._handle_basic_blueprint()`
calls `StructureGenerator.generate_from_structure_blueprint()` to create a new Python class named
`RawText` inheriting from `TextContent`, then registers it with Kajson's class registry. These
dynamically-generated classes are used as the `content` type of `Stuff` objects in the `WorkingMemory`.

When the PipeJob is serialized via Kajson for Temporal transport, these objects carry
`__class__: "RawText"` and `__module__: "builtins"` metadata. The worker must have these classes
registered before it can deserialize the PipeJob.

## Why Tests Don't Catch It

- Integration tests use local `PipeRouter` (in-process), not Temporal. Library is shared.
- Temporal tests only test leaf workflows (text gen, jinja2) that don't call `get_required_pipe()`.
- No test sends a pipe controller through `WfPipeRouter`.

## Expected Error Patterns

The bug manifests in two layers. Layer 1 hits first and prevents Layer 2 from being reached.

### Layer 1: Kajson deserialization failure (hits first)

On the **worker** stderr:
- `KajsonDecoderError: Class '<ConceptCode>' not found in module 'builtins'`
  (e.g., `Class 'RawText' not found in module 'builtins'`)
- Wrapped as `RuntimeError: Failed decoding arguments` by Temporal's workflow instance
- The concept code (e.g., `RawText`) is a dynamically-generated Python class created by
  `ConceptFactory._handle_basic_blueprint()` during library loading — which never ran on the worker
- The submitter may **hang indefinitely** waiting for a workflow result that will never arrive

### Layer 2: Library resolution failure (would hit after Layer 1 is fixed)

On the **worker** stderr:
- Errors from `get_required_pipe()` — pipe code not found in library
- The error originates inside `run_pipe()` of a controller (PipeSequence, PipeCondition, etc.)
- The API/submitter side will see a `TemporalError` or `ActivityError` wrapping it

## Proposed Fix Direction

Loading the library on the worker fixes both layers: it generates and registers the dynamic
concept classes (fixing Layer 1 deserialization) and populates `library_manager` with pipe
definitions (fixing Layer 2 resolution).

1. Workers load base library at startup from PIPELEXPATH (Tier 1 cache) — this generates
   dynamic concept classes and registers them with Kajson, enabling deserialization.
2. `mthds_contents` travels with workflow input (not consumed on API side).
3. Library loading happens in Activities (replay-safe), not workflow code.
4. Per-request overlay cached by content hash (Tier 2 cache).
