---
title: "Runtime Bridge & Transport"
description: "The backend-neutral seam that carries a pipe run across process boundaries — boundary DTOs, LibraryCrate propagation, deferred hydration, and per-call registry/library isolation — and where open core ends."
---

# Runtime Bridge & Transport

This page is for contributors working on Pipelex internals. For the capability overview, see the user-facing [Distributed Execution](../distributed-execution/index.md) page instead.

Pipelex runs a pipe either **direct** (everything in one Python process) or **distributed** on a host runtime (a separate worker process, potentially on another machine). Both paths reach pipe execution through the same framework-agnostic **runtime bridge**. This page documents that bridge backend-neutrally: the boundary data types, how a library snapshot and working memory cross a process boundary, and how concurrent runs stay isolated. The concrete realizations — Temporal-backed durable execution and the Mistral Workflows integration — are commercial Pipelex platform capabilities; their backend-specific topology lives in their own plugin repos.

!!! info "A commercial capability rides on this seam"
    Pipelex's own host-runtime embedding — running a pipe as durable, distributed workflows — is part of Pipelex's [workflow-orchestration offer](https://pipelex.com/products#durable-execution). This page documents the **open seam** and the **open boundary types**; the cross-process plumbing that drives them is not part of open core (see [Where open core ends](#where-open-core-ends) below). For the orchestrator extension point a third-party backend compiles against, see [Orchestrator Plugins](./orchestrator-plugins.md).

---

## Direct vs distributed, one bridge

| Mode | Where pipes run | How the PipeJob travels |
|------|-----------------|--------------------------|
| **Direct** | All pipes in the same process. Library, class registry, and pipe resolution are shared in-memory. | Stays in-process; no serialization. |
| **Distributed** | The PipeJob is serialized and sent to a worker — a separate process. | Crosses the boundary as structured JSON, carrying a serializable library snapshot. |

Both modes share the same pipe definitions, library loading, and controller logic. The only difference is *where* a pipe runs and how its `PipeJob` gets there. Distributing execution across separate processes introduces problems that don't exist in-process — those problems, and their solutions, are this page's subject. For the routing layer that sits above the bridge (how a controller dispatches its child pipes in each mode), see [Pipe Routing & Execution](./pipe-routing-and-execution.md).

---

## The boundary data types

Three open-core Pydantic models are everything that crosses a process boundary.

### PipeJob — the unit of execution

`PipeJob` (`pipelex/pipe_run/pipe_job.py`) carries everything needed to run a single pipe:

| Field | Purpose |
|-------|---------|
| `pipe` | The resolved pipe object (concrete operator or controller). |
| `working_memory` | Runtime data store — typed `Stuff` objects keyed by variable name. |
| `working_memory_raw` | Raw JSON dict of working memory for deferred hydration (cross-process only). |
| `pipe_run_params` | Execution config: run mode (LIVE/DRY), output multiplicity, pipe stack for cycle detection. |
| `job_metadata` | Pipeline run ID, user ID, tracing context. |
| `library_crate` | Serializable library snapshot for distributed execution. |

### PipeOutput — the result that comes back

`PipeOutput` (`pipelex/core/pipes/pipe_output.py`) carries the run result. Like `PipeJob`, it has both a typed `working_memory` and a `working_memory_raw` dict — the raw field is how a result travels back across a boundary without requiring class resolution at every hop (see [Deferred hydration](#deferred-hydration)).

### LibraryCrate — a serializable library snapshot

A `LibraryCrate` (`pipelex/libraries/library_crate.py`) is a flat, serializable snapshot of the library — the pipes and concepts a worker needs to run the job:

```python
class LibraryCrate(BaseModel):
    concepts: dict[str, ConceptBlueprint | str]  # concept ref -> blueprint or description
    pipes: dict[str, PipeBlueprintUnion]  # pipe ref -> blueprint
    domains: dict[str, DomainBlueprint]  # domain code -> domain metadata
    source_map: dict[str, str]  # ref -> source file (error traceability)
    fingerprint: str  # SHA256 of serialized content
```

Domain is encoded in the dictionary keys (e.g., `scoring.WeightedScore`, `scoring.compute_score`), not in a structural container. `source_map` lets error messages trace back to origin files. The `fingerprint` enables idempotent loading — a worker that already loaded a crate with the same fingerprint skips the reload. The crate is a plain Pydantic model, so a host runtime serializes it as structured JSON in the job input — fully inspectable, not opaque bytes.

---

## The three cross-process challenges

Sending a pipe run to a separate worker process introduces three challenges that single-process execution never faces:

1. **Pipe resolution** — Controllers call `get_required_pipe()` to resolve child pipes. The worker's library must contain those pipes. → solved by **LibraryCrate propagation**.
2. **Dynamic class deserialization** — `.mthds` bundles generate Python classes at runtime (e.g., `RawText` inheriting from `TextContent`). A receiving process must have those classes registered before it can deserialize `WorkingMemory`. → solved by **deferred hydration**.
3. **Concurrent isolation** — One worker may run many jobs at once. Two jobs that each define a concept named `Result` with different structures must not share a class registry or library. → solved by **per-call scoping**.

---

## LibraryCrate propagation

The submitter builds a `LibraryCrate` from its loaded library (`pipelex/libraries/library_crate_factory.py`) and attaches it to the `PipeJob`. On the worker, the job's entry point loads the crate into a scoped library, registering the bundle's dynamic concept classes, so `get_required_pipe()` resolves every pipe at every level of nesting. Because a distributed run can fan out into nested jobs (a controller's child pipes), every nested job carries the same crate; loading is idempotent via the fingerprint, so re-receiving a crate already loaded on a worker is a no-op.

---

## Deferred hydration

### The chicken-and-egg problem

A host runtime's data converter deserializes a payload (a job input, a return value) before any bundle code has run — but reconstructing a typed `WorkingMemory` needs the bundle's dynamic concept classes registered, and those only get registered when the `LibraryCrate` is loaded *inside* the job. Two deserialization gaps follow:

1. **Input** — the `PipeJob` input contains `WorkingMemory` whose dynamic classes don't exist yet on the worker.
2. **Output** — a nested job's `PipeOutput` return value contains `WorkingMemory` with dynamic classes, and the parent's data converter typically runs outside the job's scope, so it can't reach the per-job class registry.

### The solution: carry working memory raw

Both `PipeJob` and `PipeOutput` carry a `working_memory_raw` field — a plain JSON dict — alongside the typed `working_memory`. The raw dict needs no class resolution to cross a boundary, which decouples transport from class registration.

- **Input dehydration** — before dispatch, the working memory is moved into `working_memory_raw` (a plain dict produced by `WorkingMemory.dump_for_transport()`, which stays in open core at `pipelex/core/memory/working_memory.py`). After the worker loads the crate, the job's entry point hydrates the raw dict back to a typed `WorkingMemory`, inside the job's scope.
- **Output dehydration** — before a nested job returns, its working memory is dehydrated to `working_memory_raw`. A **parent job** that consumes the nested output (a controller combining branch results — PipeParallel, PipeBatch) rehydrates it on receive, inside its **own already-loaded scope**: the parent's library carries the same crate (checked by fingerprint via `is_crate_loaded`), so hydration rebinds the nested output to the parent's own dynamic classes — the identity the parent's models reference. **Delivery** workers never load the crate — they render from the raw dict, only best-effort hydrating the main stuff via globally registered classes (falling back to a generic dict render when the class isn't registered), so they stay crate-free. The **top-level submitter** rehydrates too, opening a fresh scoped library when it hasn't loaded the crate itself.

The worker-side hydration helper (`pipelex/runtime_bridge/primitives/hydration.py`) is open core: it iterates the raw dict, uses `StuffContentFactory` to rebuild typed content from the registered classes, and preserves aliases. It also guards against cross-exec class-identity mismatches (`_validate_as_known_class` round-trips items through `model_dump()`): the dynamic classes a worker re-execs from the crate are new Python identities sharing a name with whatever a data converter eagerly rebuilt, and a naive `model_validate` would reject the older instance.

### Boundary-by-boundary (backend-neutral)

| Boundary | Direction | What crosses | Hydrate on receive? |
|----------|-----------|--------------|----------------------|
| Submitter → top worker job | input | `PipeJob` (`working_memory_raw` + `library_crate`) | Yes — worker loads crate, then hydrates in scope |
| Parent job → nested job | input | Same `PipeJob` shape (crate re-loaded idempotently) | Yes — in the nested job's own scope |
| Nested job → parent | output | `PipeOutput` (`working_memory_raw`) | Yes — in the parent's own scope, whose library already carries the crate (fingerprint match), so branch instances rebind to the parent's class identities |
| Parent job → delivery | result arg | `PipeOutput` (`working_memory_raw`, no crate) | **No** — delivery renders from raw, best-effort local hydration of the main stuff using only globally registered classes |
| Top worker job → submitter | output | `PipeOutput` (`working_memory_raw`) | Yes — the submitter rehydrates, opening a fresh scoped library if a crate is available |

Because delivery renders from the raw dict (`pipelex/pipe_run/delivery_executor.py` branches on which field is populated), a delivery worker never needs the crate loaded — which is the precondition for true distributed execution. Dynamic concepts lose typed rendering on the delivery worker (a generic field-walking fallback still produces readable JSON/HTML), but the worker stays crate-free.

!!! note "Where the transport prep lives"
    Moving working memory into `working_memory_raw` for a job, dehydrating a result before return, and the submitter-side rehydration are cross-process plumbing, and are **not** part of open core. The *raw field itself*, `dump_for_transport`, and the worker-side hydration helper stay **open core**, because they are host-agnostic and are also exercised by the open `pipelex-api` runner.

---

## Per-call scoping

A single process may handle many concurrent jobs — and, in a server, many concurrent requests that are not jobs at all. If two of them define a concept named `Result` with different fields, they must not share a `ClassRegistry` or `Library`: structure classes are registered under a name key, so the second registration overwrites the first and the two silently swap schemas and output types. The isolation is therefore structural rather than something a caller opts into — every `Library` the manager opens carries its own registry:

1. **ClassRegistry** — `library_manager.open_library()` attaches a fresh `ClassRegistry` to every library it creates, pre-seeded from the global registry (which holds the base classes from `PIPELEXPATH`). A load's dynamic classes register there, never in the global registry, and no caller can forget to ask for it.
2. **Library** — a fresh `Library` (`library_manager.open_fresh_library()`), set as current via a `ContextVar` keyed by the run id. Run-id keying (not job/workflow id) is deliberate: a reused workflow id across retries/resets could otherwise let a closed predecessor's cleanup tear down a live successor's library on the same worker.
3. **Lookup chain** — `hub.get_class_registry()` reads the `ContextVar`, returns the scoped library's registry, and falls back to the global registry when no library is set (e.g. a data converter running outside the job scope — which is exactly why output uses deferred hydration).
4. **Cleanup** — `library_manager.teardown(library_id)` drops the library and its registry; the `ContextVar` is reset. No manual GC needed.

One consequence is worth stating for host code: a structure class registered while a library is current lands in *that library's* registry and is gone when it is torn down. A Python structure class that every load should see must be registered before any library is opened — which is what importing it at boot, or loading it from a library directory into the library that uses it, already does.

The class-registry accessor and its library scoping (`pipelex/runtime_hub.py`, `pipelex/system/registries/class_registry_access.py`, `pipelex/interpreter_hub.py`, `pipelex/libraries/library.py`, `pipelex/libraries/library_manager.py`) is open core — the same machinery serves direct execution, the open runner, and any host-runtime plugin.

---

## Where open core ends

The boundary types and the host-agnostic helpers are **open** (MIT, in the `pipelex` distribution):

| Concern | Open core (`pipelex`) |
|---|---|
| Boundary DTOs | `PipeJob`, `PipeOutput`, `LibraryCrate`, `runtime_bridge/payloads.py` |
| Serialization | `runtime_bridge/serialization.py` |
| Mode / delivery model | `orchestration_mode`, `DeliveryMode`, the orchestrator registry / SPI |
| Working-memory raw + dump | `working_memory_raw`, `WorkingMemory.dump_for_transport` |
| Worker-side hydration | `runtime_bridge/primitives/hydration.py` |

The cross-process *plumbing* that drives a pipe run across the boundary — the host-side bridge entry point, the transport-prep step, and the dispatch primitives (submitter rehydration, delivery, trace flush, scoped-library, pipe classification, and the submit-arg envelope) — is **not open core**. Pipelex's own host-runtime embedding is a commercial capability.

A third-party orchestrator compiles against the **open** surface only (the [Orchestrator SPI](./orchestrator-plugins.md#the-orchestrator-spi)); Pipelex's own host-runtime plugins (Temporal, Mistral Workflows) additionally build on the closed side.

---

## Next steps

- [Orchestrator Plugins](./orchestrator-plugins.md) — the orchestration-mode seam, the Orchestrator SPI, and the open/closed boundary in contract terms.
- [Pipe Routing & Execution](./pipe-routing-and-execution.md) — how PipeJobs are created and routed in direct and distributed modes.
- [Content Generation Across Boundaries](./distributed-content-generation.md) — how dynamic Pydantic models and large binary payloads cross a worker boundary.
- [Distributed Execution](../distributed-execution/index.md) — the user-facing capability overview, and the [workflow-orchestration offer](https://pipelex.com/products#durable-execution) (Temporal-backed durable execution, the Mistral Workflows integration).
