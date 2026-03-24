# Master Plan v2: LibraryCrate & Distributed Execution

> **Status**: Master plan for phased implementation
> **Date**: 2026-03-23
> **Related**: [B-library-as-execution-context.md](B-library-as-execution-context.md), [E-pipe-namespace-fix.md](E-pipe-namespace-fix.md), [C-temporal-payload-codec-strategy.md](C-temporal-payload-codec-strategy.md)

---

## Goal

Introduce the LibraryCrate as the universal intermediate representation for library loading, then leverage it to enable distributed execution (Temporal) with full library context. Get there incrementally with fast, testable results at each phase.

---

## Design Principles

1. **Three-stage pipeline.** `Bundles (files) → LibraryCrate (data) → Library (live)`. The crate is the clean boundary between sourcing and execution.

2. **Flat and ref-keyed.** The crate is two flat dicts: concepts keyed by `concept_ref`, pipes keyed by `pipe_ref`. Domain is a namespace prefix in the key, not a structural container. No source paths, no package provenance.

3. **Same API for direct and distributed execution.** The LibraryCrate is not Temporal-specific. Direct mode builds and loads it in-process. Distributed mode serializes and ships it. The crate model is identical.

4. **Transparency in dashboards.** Everything in PipeJob remains visible as structured JSON in Temporal dashboards. No opaque bytes.

5. **TDD where it makes sense.** Each phase defines clear "done" criteria with specific tests. Write tests first for the new models and interfaces.

---

## Architecture Summary

| Phase | Component | What it solves |
|-------|-----------|----------------|
| **0** | Pipe namespace fix (`pipe_ref`) | Prerequisite: pipes indexed by domain-qualified ref, symmetric with concepts |
| **1** | LibraryCrate (direct mode) | Universal intermediate between bundles and live library |
| **2** | LibraryCrate on Temporal | Library loading on workers (Layer 2: pipe resolution) |
| **3** | Deferred WorkingMemory hydration | Dynamic class registration timing (Layer 1: Kajson deser) |
| **4** | StoragePayloadCodec | Payload size limits (2MB) for large libraries and WorkingMemory |

---

## Phase 0: Pipe Namespace Fix (`pipe_ref`)

> **Status**: Complete — PR #780 (628e414d)

**Goal**: Pipes are indexed by domain-qualified `pipe_ref` (`domain.pipe_code`), symmetric with how concepts use `concept_ref` (`domain.ConceptCode`). Multiple bundles can contribute to the same domain.

**Why first**: The LibraryCrate organizes content by domain. If pipes can collide across domains, the crate can't reliably merge content. This fix is also valuable independently — it eliminates a latent bug.

See [E-pipe-namespace-fix.md](E-pipe-namespace-fix.md) for the full technical spec.

### Changes

- Add `pipe_ref` property to `PipeAbstract` = `f"{domain_code}.{code}"`
- Rekey `PipeLibrary` root dict from bare `code` to `pipe_ref`
- Update `add_new_pipe()`, `get_optional_pipe()`, `get_required_pipe()` to use `pipe_ref` as primary key
- Update `library_manager.load_from_blueprints()` pipe tracking and source mapping
- Fix `DomainLibrary.add_domain()` to support additive merging (or make idempotent for same-domain re-adds)
- Update all call sites that assume bare-code pipe indexing

### Key files

| File | Change |
|------|--------|
| `pipelex/core/pipes/pipe_abstract.py` | Add `pipe_ref` property |
| `pipelex/libraries/pipe/pipe_library.py` | Rekey root dict by `pipe_ref`, update all lookup methods |
| `pipelex/libraries/pipe/pipe_library_abstract.py` | Update interface signatures |
| `pipelex/libraries/library_manager.py` | Update `pipe_source_in_this_load`, source map tracking |
| `pipelex/libraries/domain/domain_library.py` | Support additive domain merging |
| `pipelex/hub.py` | Update global pipe lookup helpers |
| `pipelex/pipe_controllers/sub_pipe.py` | Update pipe resolution |
| Multiple call sites | Audit all `get_required_pipe(pipe_code=...)` calls |

### Done when

- [x] All existing tests pass with `pipe_ref`-based indexing
- [x] New unit test: two pipes with same code in different domains coexist in one `PipeLibrary`
- [x] New unit test: domain-qualified lookup returns correct pipe when same code exists in multiple domains
- [x] New unit test: bare-code lookup still works when unambiguous (single domain)
- [x] New unit test: bare-code lookup raises when ambiguous (same code in multiple domains)
- [x] New unit test: multiple bundles for the same domain can be loaded (domain merging)
- [x] `make agent-check` passes
- [x] `make agent-test` passes

---

## Phase 1: LibraryCrate (Direct Mode)

**Goal**: All library loading goes through `LibraryCrate` as an intermediate. The three-stage pipeline (`bundles → crate → library`) is the only path. Works in direct execution mode.

### LibraryCrate model

```python
class LibraryCrate(BaseModel):
    """Complete library content, ready to load into a live Library."""
    concepts: dict[str, ConceptBlueprint]    # concept_ref (domain.Code) -> blueprint
    pipes: dict[str, PipeBlueprintUnion]     # pipe_ref (domain.pipe_code) -> blueprint
    fingerprint: str                         # SHA256 of serialized content
```

Flat structure. Domain is implicit in the keys — `scoring.WeightedScore`, `scoring.compute_score`. No `DomainCrate` wrapper.

### Changes

- Define `LibraryCrate` model with serialization tests
- `LibraryCrateFactory.make_from_blueprints(blueprints)`: for each bundle, qualify concept codes and pipe codes with the bundle's domain, add to flat dicts, compute fingerprint. Same ref appearing twice = error.
- New `LibraryManager.load_from_crate(library_id, crate)`: extract domain codes from refs, create domains/concepts/pipes. This becomes the single entry point for loading.
- Refactor `load_from_blueprints()`: internally builds a crate, then calls `load_from_crate()`. Callers don't change yet, but the path goes through the crate.
- Update `pipeline_run_setup()` to route through the crate path.

### Key files

| File | Change |
|------|--------|
| `pipelex/libraries/library_crate.py` | **New** — `LibraryCrate` model |
| `pipelex/libraries/library_crate_factory.py` | **New** — `make_from_blueprints()`, fingerprint computation |
| `pipelex/libraries/library_manager.py` | Add `load_from_crate()`, refactor `load_from_blueprints()` to go through crate |
| `pipelex/pipeline/pipeline_run_setup.py` | Route through crate |

### Done when

- [ ] `LibraryCrate` model serializes and deserializes correctly (unit test: JSON round-trip)
- [ ] `make_from_blueprints()` merges correctly (unit test: two blueprints for same domain → both pipes/concepts in flat crate with qualified refs)
- [ ] `make_from_blueprints()` raises on concept/pipe code collision within a domain (unit test)
- [ ] `load_from_crate()` produces a valid library equivalent to `load_from_blueprints()` (integration test)
- [ ] All existing pipeline tests pass through the new `bundles → crate → library` path
- [ ] `make agent-check` passes
- [ ] `make agent-test` passes

---

## Phase 2: LibraryCrate on Temporal

**Goal**: Temporal workers receive and load a LibraryCrate. Pipe controllers (PipeSequence, PipeCondition, PipeBatch, PipeParallel) work on workers. This solves Layer 2 (pipe resolution).

**What it does NOT solve yet**: Layer 1 (dynamic class deserialization) for concepts introduced by `mthds_content` that aren't in PIPELEXPATH. That's Phase 3.

### Changes

- Add `library_crate: LibraryCrate | None` field to `PipeJob`
- In `PipeRouterTop`: after `pipeline_run_setup()` loads the library, build the flat crate from the blueprints that were loaded beyond PIPELEXPATH base. Attach to `PipeJob`.
- New `act_library_setup` activity: receives a `LibraryCrate`, calls `load_from_crate()`. Idempotent via fingerprint caching.
- Update `WfPipeRouter`: call `act_library_setup` before pipe execution if `library_crate` is present.

```python
@workflow.run
async def run(self, pipe_job: PipeJob) -> PipeOutput:
    if pipe_job.library_crate is not None:
        await workflow.execute_activity(
            act_library_setup,
            pipe_job.library_crate,
            start_to_close_timeout=timedelta(seconds=30),
        )
    return await pipe_job.pipe.run_pipe(...)
```

### Key files

| File | Change |
|------|--------|
| `pipelex/pipe_run/pipe_job.py` | Add `library_crate: LibraryCrate | None` field |
| `pipelex/temporal/tprl_pipe/act_library_setup.py` | **New** — library setup activity |
| `pipelex/temporal/tprl_pipe/wf_pipe_router.py` | Call `act_library_setup` before pipe execution |
| `pipelex/temporal/tprl_pipe/pipe_router_top.py` | Build `LibraryCrate` when dispatching |
| `pipelex/temporal/temporal_tasks.py` | Register `act_library_setup` |

### Done when

- [ ] Integration test: PipeSequence through Temporal with PIPELEXPATH-based library only (no crate needed)
- [ ] Integration test: PipeSequence with `mthds_content` containing additional pipes (crate shipped, loaded via activity)
- [ ] `get_required_pipe()` works on worker for child pipes
- [ ] Crate is visible as structured JSON in Temporal dashboard
- [ ] `make agent-check` passes
- [ ] `make agent-test` passes

---

## Phase 3: Deferred WorkingMemory Hydration

**Goal**: Handle Layer 1 — when `mthds_content` introduces dynamic concept classes that the worker doesn't know about at deserialization time.

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
    library_crate: LibraryCrate | None = None
```

### Key files

| File | Change |
|------|--------|
| `pipelex/pipe_run/pipe_job.py` | Add `working_memory_raw: dict[str, Any] | None` field |
| `pipelex/temporal/tprl_pipe/pipe_router_top.py` | Detect dynamic concepts, serialize WM to raw dict |
| `pipelex/temporal/tprl_pipe/wf_pipe_router.py` | Hydration logic after library setup |
| `pipelex/temporal/tprl_pipe/hydration.py` | **New** — `hydrate_working_memory()` utility |

### Done when

- [ ] Integration test: PipeSequence with `mthds_content` containing a custom concept with inline structure (dynamic class)
- [ ] `working_memory_raw` hydrates correctly after library setup
- [ ] Stuff objects have correct typed content after hydration
- [ ] `working_memory_raw` is visible as plain JSON in Temporal dashboard
- [ ] `make agent-check` passes
- [ ] `make agent-test` passes

---

## Phase 4: StoragePayloadCodec

**Goal**: Remove the 2MB payload size limit for production workloads with large libraries or WorkingMemory containing images/documents.

**Why last**: Phases 0-3 work for small-to-medium payloads. Phase 4 is needed when payloads grow beyond Temporal's limits.

### StoragePayloadCodec

Extends `temporalio.converter.PayloadCodec`. Operates at the wire boundary — transparent to all application code.

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

### Key files

| File | Change |
|------|--------|
| `pipelex/temporal/storage_payload_codec.py` | **New** — StoragePayloadCodec class |
| `pipelex/temporal/temporal_data_converter.py` | Add codec to DataConverter |
| `pipelex/temporal/temporal_connect.py` | Pass codec-enabled converter |
| `pipelex/temporal/worker_cli.py` | Pass codec-enabled converter |
| `pipelex/temporal/config_temporal.py` | Add payload codec config |
| `pipelex/pipelex.toml` | Add `[pipelex.temporal.payload_codec]` |

### Done when

- [ ] Unit test: payloads above threshold are stored externally, below threshold pass through
- [ ] Unit test: content-addressed deduplication works
- [ ] Integration test: large WorkingMemory survives Temporal round-trip
- [ ] `make agent-check` passes
- [ ] `make agent-test` passes

---

## Future Phases (Out of Scope)

These are documented for roadmap visibility but not planned for implementation now.

### Crate Stripping (Static Dependency Tree)

From the entry pipe, walk the transitive closure of `pipe_dependencies()` + `concept_dependencies` to determine the minimal subset of the library needed. Strip the crate to only those domains/concepts/pipes. Reduces payload size and clarifies execution context.

### Remote Dependency Resolution

Resolve dependencies from GitHub method package addresses (e.g., `github:org/repo`). Clone to a temp directory, parse bundles, merge into the crate. Enables running pipelines whose dependencies aren't pre-installed.

### Library Fingerprint Validation

Verify that the worker's base library (PIPELEXPATH) matches the API's expectation. Detect version drift between API and worker deployments.

### Cross-Worker Cache via Shared Storage

Cache loaded libraries in shared storage (Redis, S3) so multiple workers don't redundantly load the same crate. Keyed by fingerprint.

---

## Dependencies Between Phases

```
Phase 0 (pipe_ref fix)
    │
    ▼
Phase 1 (LibraryCrate, direct mode)
    │
    ▼
Phase 2 (LibraryCrate on Temporal)
    │
    ▼
Phase 3 (Deferred WM Hydration)        ← requires Phase 2's library_crate and activity

Phase 4 (StoragePayloadCodec)           ← independent, can parallel with Phase 3
```

Phase 0 is a prerequisite for Phase 1 (domain-qualified indexing). Phase 1 is a prerequisite for Phase 2 (crate must exist to ship it). Phase 3 builds on Phase 2's activity. Phase 4 is independently useful.

---

## What Exists Already

| What | Where | Status |
|------|-------|--------|
| Worker base library loading (Tier 1) | `worker_cli.py` | Done |
| Kajson data converter | `temporal_data_converter.py` | Done |
| Storage provider system (local/S3/GCP) | `pipelex/tools/storage/` | Done |
| Library manager with multi-library + ContextVar | `pipelex/libraries/library_manager.py` | Done |
| `load_from_blueprints()` | `library_manager.py` | Done (will refactor through crate) |
| `PipelexInterpreter.make_pipelex_bundle_blueprint()` | interpreter | Done |
| ConceptBlueprint, PipeBlueprintUnion models | `pipelex/core/` | Done |
| `concept_ref` on Concept | `pipelex/core/concepts/concept.py` | Done (model for `pipe_ref`) |

---

## Implementation Pattern Per Phase

1. **Tests first** — Define new models, write serialization/unit tests before implementation
2. **Model + core logic** — Implement models and core functions, pass unit tests
3. **Integration** — Wire into existing plumbing, pass integration tests
4. **`make agent-check`** — Lint + type check
5. **`make agent-test`** — Full suite passes
6. **Review "done" checklist** — All criteria met before moving to next phase
