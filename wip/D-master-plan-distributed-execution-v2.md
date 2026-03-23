# Master Plan v2: Distributed Execution with Library Context

> **Status**: Master plan for phased implementation
> **Date**: 2026-03-23
> **Related**: [A-temporal-library-fix-proposals-v2.md](A-temporal-library-fix-proposals-v2.md), [B-library-as-execution-context.md](B-library-as-execution-context.md), [C-temporal-payload-codec-strategy.md](C-temporal-payload-codec-strategy.md)

---

## Goal

Enable distributed execution (Temporal) to work with full library context, so pipe controllers (PipeSequence, PipeCondition, PipeBatch, PipeParallel) can run on workers. Get there incrementally with fast, testable results at each phase.

---

## Design Principles

1. **Same API for direct and distributed execution.** `library_context` is an optional parameter on `PipeJob` / `run_pipe`, not a Temporal-specific wrapper. No `TemporalPipeJobEnvelope`.

2. **Library context = domains, not bundles.** The serializable unit is a domain containing concept blueprints and pipe blueprints (structured Pydantic models), not raw `.mthds` file text or bundle-level objects.

3. **Transparency in dashboards.** Everything in PipeJob remains visible as structured JSON in Temporal dashboards. No opaque bytes.

4. **Deferred hydration, not deferred deserialization.** When WorkingMemory contains Stuff with dynamic concept classes unknown to the worker, it travels as a raw JSON dict (fully visible). After the library context is loaded and classes are registered, the dict is hydrated into typed `WorkingMemory`. This avoids both opaque bytes and Kajson modifications.

---

## Architecture Summary

| Component | What it solves | Phase |
|-----------|---------------|-------|
| **LibraryContext + act_library_setup** | Library loading on worker (Layer 2: pipe resolution) | Phase 1 |
| **Deferred WorkingMemory hydration** | Dynamic class registration timing (Layer 1: Kajson deser) | Phase 2 |
| **StoragePayloadCodec** | Payload size limits (2MB) for large libraries and WorkingMemory | Phase 3 |

---

## Phase 1: LibraryContext + act_library_setup

**Goal**: Pipe controllers work on Temporal workers when all concepts come from the worker's base library (PIPELEXPATH). This covers the majority of use cases.

**What it solves**: Layer 2 (pipe resolution). When the API loads additional library content (beyond PIPELEXPATH), that content travels with the workflow and is loaded on the worker before execution. `get_required_pipe()` finds everything.

**What it does NOT solve yet**: Layer 1 (dynamic class deserialization) for concepts introduced by `mthds_content` that aren't in PIPELEXPATH. That's Phase 2.

### LibraryContext model

The library context is organized by domain -- the semantic unit of the loaded library -- not by bundle (the file-system artifact).

```python
class DomainContext(BaseModel):
    """A domain's worth of concept and pipe blueprints, ready to load."""
    domain_code: str
    description: str | None = None
    concepts: dict[str, ConceptBlueprint]       # concept_code -> blueprint
    pipes: dict[str, PipeBlueprintUnion]         # pipe_code -> blueprint

class LibraryContext(BaseModel):
    """Library content that must be loaded on the worker before execution."""
    domains: list[DomainContext]
    fingerprint: str                             # SHA256 for caching
```

**How it's built** (API side, in `PipeRouterTop`):
- After `pipeline_run_setup()` loads the library, extract the domains that came from additional content (not from PIPELEXPATH base)
- Build `DomainContext` for each, pulling concept/pipe blueprints from the loaded `PipelexBundleBlueprint` objects
- Compute fingerprint from serialized domains
- If no additional content beyond PIPELEXPATH, `library_context = None`

**Where it lives**: On `PipeJob` as an optional field.

```python
class PipeJob(BaseModel):
    pipe: PipeAbstract
    working_memory: WorkingMemory
    pipe_run_params: PipeRunParams
    job_metadata: JobMetadata
    output_name: str | None = None
    library_context: LibraryContext | None = None    # NEW
```

This is the same PipeJob used by both direct and distributed execution. In direct mode, `library_context` is always `None` (the library is already in-process). In distributed mode, it's populated when there's additional content beyond the worker's base.

### act_library_setup activity

```python
@activity.defn
async def act_library_setup(library_context: LibraryContext) -> None:
    # 1. Check cache: if fingerprint already loaded, skip
    # 2. Convert DomainContexts -> PipelexBundleBlueprints (or load directly)
    # 3. Call library_manager.load_from_blueprints(library_id, blueprints)
    # 4. Cache fingerprint
```

- Retry-safe (activities may re-execute due to retries/failures)
- Idempotent (same fingerprint = no-op via in-process cache)
- Uses `library_manager.load_from_blueprints()` (already exists)

### WfPipeRouter changes

```python
@workflow.run
async def run(self, pipe_job: PipeJob) -> PipeOutput:
    # NEW: if library context present, load it first
    if pipe_job.library_context is not None:
        await workflow.execute_activity(
            act_library_setup,
            pipe_job.library_context,
            start_to_close_timeout=timedelta(seconds=30),
        )
    # Then execute pipe as before
    return await pipe_job.pipe.run_pipe(...)
```

### What to test

- Integration test: Send a PipeSequence through Temporal with PIPELEXPATH-based library only (no library_context needed, Tier 1)
- Integration test: Send a PipeSequence with `mthds_content` containing additional pipes (library_context shipped, loaded via activity)
- Verify `get_required_pipe()` works on worker for child pipes

### Key files

| File | Change |
|------|--------|
| `pipelex/temporal/library_context.py` | **New** -- DomainContext, LibraryContext models |
| `pipelex/temporal/tprl_pipe/act_library_setup.py` | **New** -- Library setup activity |
| `pipelex/temporal/tprl_pipe/wf_pipe_router.py` | Call act_library_setup before pipe execution |
| `pipelex/temporal/tprl_pipe/pipe_router_top.py` | Build LibraryContext when dispatching |
| `pipelex/pipe_run/pipe_job.py` | Add `library_context: LibraryContext | None` field |
| `pipelex/temporal/temporal_tasks.py` | Register act_library_setup |

### Future expansion

- Multi-package dependencies in LibraryContext
- Library fingerprint validation (worker base matches API expectation)
- Cross-worker cache via shared storage

---

## Phase 2: Deferred WorkingMemory Hydration

**Goal**: Handle the Layer 1 problem -- when `mthds_content` introduces dynamic concept classes that the worker doesn't know about at deserialization time.

**The problem**: Temporal auto-deserializes PipeJob via the Kajson data converter. If WorkingMemory contains Stuff objects with dynamic content classes (e.g., `RawText`), Kajson fails because those classes aren't registered on the worker yet. The `act_library_setup` activity can't run until the workflow starts, but the workflow input must be deserialized first.

**The solution**: WorkingMemory travels as a raw JSON dict when it contains dynamic concepts. After library setup registers the classes, the dict is hydrated into a typed `WorkingMemory`.

### PipeJob changes

```python
class PipeJob(BaseModel):
    pipe: PipeAbstract
    working_memory: WorkingMemory | None = None           # typed (direct mode, or no dynamic concepts)
    working_memory_raw: dict[str, Any] | None = None      # raw JSON (when deferred hydration needed)
    pipe_run_params: PipeRunParams
    job_metadata: JobMetadata
    output_name: str | None = None
    library_context: LibraryContext | None = None
```

- **Direct mode**: `working_memory` is always set, `working_memory_raw` is always `None`
- **Temporal, base concepts only**: `working_memory` is set (Kajson can deserialize because classes are registered at worker startup)
- **Temporal, dynamic concepts**: `working_memory = None`, `working_memory_raw` is the raw JSON dict. After library setup, hydrate it.

### PipeRouterTop changes

When dispatching to Temporal:
1. Check if the WorkingMemory contains Stuff with dynamic concepts (beyond PIPELEXPATH base)
2. If yes: serialize WorkingMemory to dict via `kajson.dumps()` / `json.loads()`, set `working_memory_raw`, clear `working_memory`
3. If no: leave `working_memory` as-is (normal path)

### WfPipeRouter changes

```python
@workflow.run
async def run(self, pipe_job: PipeJob) -> PipeOutput:
    # Load library context if present
    if pipe_job.library_context is not None:
        await workflow.execute_activity(
            act_library_setup,
            pipe_job.library_context,
            start_to_close_timeout=timedelta(seconds=30),
        )

    # Hydrate working memory if deferred
    working_memory: WorkingMemory
    if pipe_job.working_memory is not None:
        working_memory = pipe_job.working_memory
    elif pipe_job.working_memory_raw is not None:
        # Classes now registered by act_library_setup
        working_memory = hydrate_working_memory(pipe_job.working_memory_raw)
    else:
        raise WorkflowInputError("No working memory")

    return await pipe_job.pipe.run_pipe(working_memory=working_memory, ...)
```

### Hydration

```python
def hydrate_working_memory(raw: dict[str, Any]) -> WorkingMemory:
    """Reconstruct typed WorkingMemory from raw JSON dict using Kajson."""
    json_str = json.dumps(raw)
    return kajson.loads(json_str, WorkingMemory)
```

Kajson now succeeds because `act_library_setup` registered the dynamic classes.

### Dashboard visibility

- `working_memory_raw` is a plain JSON dict -- fully visible and inspectable in Temporal dashboards
- `library_context` is structured Pydantic data -- also fully visible
- No opaque bytes anywhere

### What to test

- Integration test: PipeSequence with `mthds_content` containing a custom concept with inline structure (dynamic class)
- Verify working_memory_raw hydrates correctly after library setup
- Verify Stuff objects have correct typed content after hydration

### Key files

| File | Change |
|------|--------|
| `pipelex/pipe_run/pipe_job.py` | Add `working_memory_raw: dict[str, Any] | None` field |
| `pipelex/temporal/tprl_pipe/pipe_router_top.py` | Detect dynamic concepts, serialize WM to raw dict |
| `pipelex/temporal/tprl_pipe/wf_pipe_router.py` | Hydration logic after library setup |
| `pipelex/temporal/tprl_pipe/hydration.py` | **New** -- `hydrate_working_memory()` utility |

### Future expansion

- Smarter detection of "needs deferred hydration" (check if all content classes are in base registry)
- Partial hydration (only defer Stuff objects with unknown classes)

---

## Phase 3: StoragePayloadCodec

**Goal**: Remove the 2MB payload size limit for production workloads with large libraries or WorkingMemory containing images/documents.

**Why third**: Phases 1-2 work for small-to-medium payloads. Phase 3 is needed when payloads grow beyond Temporal's limits.

### StoragePayloadCodec

Extends `temporalio.converter.PayloadCodec`. Operates at the wire boundary -- transparent to all application code.

```
Application code                    StoragePayloadCodec               Temporal Server
-----                               -----                             -----
pass WorkingMemory (50MB) -->  encode(): upload to storage,     -->  stores small ref
                               replace with storage key ref           in Event History

receive storage ref           <-- decode(): download from storage, <-- reads ref from
return WorkingMemory (50MB)       reconstruct original payload        Event History
```

- Content-addressed (SHA256 key) = natural deduplication
- Uses Pipelex's existing `StorageProviderAbstract`
- V1: `LocalStorageProvider` (same filesystem for dev)
- Threshold: 1MB (configurable, well under 2MB hard limit)

### Integration

The codec is composed into the existing `DataConverter` and passed to both client and worker.

### Key files

| File | Change |
|------|--------|
| `pipelex/temporal/storage_payload_codec.py` | **New** -- StoragePayloadCodec class |
| `pipelex/temporal/temporal_data_converter.py` | Add codec to DataConverter |
| `pipelex/temporal/temporal_connect.py` | Pass codec-enabled converter |
| `pipelex/temporal/worker_cli.py` | Pass codec-enabled converter |
| `pipelex/temporal/config_temporal.py` | Add payload codec config |
| `pipelex/pipelex.toml` | Add `[pipelex.temporal.payload_codec]` |

### Future expansion

- S3/GCP backend (swap storage provider config)
- TTL/lifecycle rules
- Codec Server for Temporal Web UI observability
- Migration to Temporal's native `ExternalStorage` API when released

---

## Dependencies Between Phases

```
Phase 1 (LibraryContext + act_library_setup)
    |
    v
Phase 2 (Deferred WM Hydration)        -- requires Phase 1's library_context and activity
    |
    v
Phase 3 (StoragePayloadCodec)           -- independent, but needed for production payloads
```

Phase 1 is immediately testable with small payloads. Phase 2 builds on Phase 1's activity. Phase 3 is independently useful and can be done in parallel with Phase 2 if needed.

---

## What Exists Already

| What | Where | Status |
|------|-------|--------|
| Worker base library loading (Tier 1) | `worker_cli.py` | Done |
| Kajson data converter | `temporal_data_converter.py` | Done |
| Storage provider system (local/S3/GCP) | `pipelex/tools/storage/` | Done |
| Library manager with multi-library + ContextVar | `pipelex/libraries/library_manager.py` | Done |
| `load_from_blueprints()` | `library_manager.py` | Done |
| `PipelexInterpreter.make_pipelex_bundle_blueprint()` | interpreter | Done |
| ConceptBlueprint, PipeBlueprintUnion models | `pipelex/core/` | Done |

---

## Implementation Pattern Per Phase

1. **Model + unit tests** -- Define new models, test serialization
2. **Core logic + unit tests** -- Activity / codec / hydration logic
3. **Integration** -- Wire into Temporal plumbing
4. **`make agent-check`** -- Lint + type check
5. **Integration test** -- End-to-end through Temporal
6. **`make agent-test`** -- Full suite passes
