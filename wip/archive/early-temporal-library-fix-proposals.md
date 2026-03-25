# Architecture Discussion: Fixing Library Unavailability in Distributed Execution (v2)

> **Status**: Draft v2 — for team architecture review
> **Date**: 2026-03-22
> **Context**: See [Pipe Routing & Execution](../under-the-hood/pipe-routing-and-execution.md) for how direct and distributed execution work. See [temporal-worker-problem.md](../../.claude/skills/temporal-diagnose/references/temporal-worker-problem.md) for the detailed root cause analysis and error patterns.
> **Changes from v1**: Relaxed C1 (breaking changes acceptable), replaced naive `mthds_content: str` model with proper multi-bundle library context analysis, proposed `LibraryContext` model for API evolution.

---

## 1. Problem Statement

When pipe controllers (PipeSequence, PipeCondition, PipeBatch, PipeParallel) run via **distributed execution** (Temporal), they fail because the library is never loaded on the worker process.

```
API Process                                    Temporal Worker
─────────────────────────────────────────     ──────────────────────────────
pipeline_run_setup()
  ├─ Loads library (library_manager)          (empty here)
  ├─ Generates dynamic concept classes        (classes don't exist here)
  ├─ Registers them with Kajson               (Kajson registry incomplete here)
  ├─ Resolves pipe by code                    (can't resolve here)
  └─ Creates PipeJob (top-level pipe)
       │
       └─ PipeRouterTop sends PipeJob ──────►  WfPipeRouter.run(pipe_job)
          to Temporal                            ├─ Kajson deserializes PipeJob
                                                 │   └─ FAILS (Layer 1): unknown class
                                                 └─ pipe.run_pipe()
                                                      └─ get_required_pipe() FAILS (Layer 2)
```

### Layer 1 -- Deserialization Failure (hits first)

The `PipeJob`'s `WorkingMemory` contains `Stuff` objects with dynamically-generated concept content classes (e.g., `RawText` inheriting from `TextContent`). These classes are created by `ConceptFactory` during library loading and registered with Kajson's class registry. On the worker, these classes don't exist -> `KajsonDecoderError: Class 'RawText' not found in module 'builtins'`.

This is a **hard blocker**: Temporal's workflow instance cannot even deserialize the workflow input.

### Layer 2 -- Pipe Resolution Failure (would hit after Layer 1 is fixed)

Controllers call `get_required_pipe(child_pipe_code)` to resolve child pipes at runtime. This queries the `library_manager` singleton, which is empty on the worker -> pipe not found.

### Why Tests Don't Catch It

- Integration tests use `PipeRouter` (direct, in-process) -- library is shared
- Temporal tests only cover leaf workflows (text gen, jinja2) that don't call `get_required_pipe()`
- No test sends a pipe controller through `WfPipeRouter`

### Key Insight

Both layers are fixed by the same fundamental action: **loading the library on the worker**. Library loading generates and registers dynamic classes (fixing Layer 1) AND populates `library_manager` with pipe definitions (fixing Layer 2).

---

## 2. Constraints

Any solution must respect these constraints:

| # | Constraint | Rationale |
|---|-----------|-----------|
| C1 | **Minimize disruption to direct execution** | Additive changes (optional params, new methods) are welcome. Breaking changes are acceptable if justified -- discuss damage control before implementation, but retro-compatibility is not required. |
| C2 | **Temporal replay safety** | Workflow code must be deterministic. Side effects (file I/O, library loading) belong in Activities, not workflow `run()` methods. Activities re-execute cleanly on replay. |
| C3 | **Worker reuse** | A single worker processes jobs from different API calls, potentially with different library contexts. The solution must handle this without conflict. |
| C4 | **Dynamic class generation is unavoidable** | Concepts declared in `.mthds` files create Python classes at library-load time. These must exist before Kajson deserialization. |
| C5 | **Library context is multi-layered** | See section 2.1. The library is not a single string -- it's a multi-file, multi-package system with manifests, dependencies, and namespace isolation. Any solution must account for this. |
| C6 | **Library loading is I/O-bound** | Reads files, parses TOML, generates classes, validates. Not suitable for workflow code (violates C2). |
| C7 | **Temporal payload size** | Default limit is 2MB (configurable). Solutions that embed large payloads must account for this. |
| C8 | **Reproduce from sources, not snapshots** | The solution should reproduce library state from source inputs (file contents, manifests, dependency metadata), not serialize the resolved `Library` object graph (which includes dependency libraries, class registries, and dynamically generated Python types). |

### 2.1 Understanding the Library Data Model

The current proposals v1 treated `mthds_content` as a single string that could carry "the library context." This is fundamentally incorrect. MTHDS is a **multi-bundle, multi-package** system:

**A package** is a directory containing:

- A `METHODS.toml` manifest (identity, exports, dependencies)
- One or more `.mthds` bundle files (each declaring one domain)
- Bundles within a package sharing the same domain code **merge** their namespaces

**Cross-package dependencies** are declared in `METHODS.toml`:

```toml
[dependencies]
scoring_lib = { address = "github.com/mthds/scoring-lib", version = "^0.5.0" }
```

Pipes reference cross-package pipes via alias syntax: `scoring_lib->scoring.compute_weighted_score`. Only exported pipes (declared in `[exports]`) are visible across package boundaries.

**How library loading actually works** (`library_manager.load_libraries()`):

1. Discovers all `.mthds` files from directory paths
2. Walks up to find `METHODS.toml` manifests for each file
3. Resolves dependencies (local path + address-based remote fetch)
4. Enforces visibility/exports between packages
5. Loads all blueprints into a `Library` with `dependency_libraries: dict[str, Library]`

**The current `mthds_content` parameter** in `pipeline_run_setup()` only handles a single string -> single `PipelexBundleBlueprint`. This works for simple single-domain bundles but cannot represent multi-file packages with manifests and cross-package dependencies. This is a known limitation of the current API surface, not the target architecture.

**Two loading paths exist today:**

| Path | Input | Handles multi-file? | Handles deps? | Used by |
|------|-------|---------------------|---------------|---------|
| Directory-based | `library_dirs` (filesystem paths) | Yes | Yes | PIPELEXPATH, installed methods |
| Content-based | `mthds_content` (single string) | No | No | API single-file bundles |

The Temporal solution must work with both paths and must not bake in the assumption that all library context fits in a single string.

---

## 3. Solution Options

### Option A: Worker Startup + Per-Workflow Library Context

**Summary**: Workers load base libraries from `PIPELEXPATH` at startup (Tier 1). Per-workflow library context -- whether a single bundle or a full package -- travels with the workflow input and is loaded in an Activity before the main pipe executes (Tier 2, cached by content hash).

**How it fixes each layer**:

- **Layer 1**: Base library loading at worker startup generates and registers all base concept classes with Kajson. For additional content, a "library setup" Activity runs before the pipe, parsing the content and registering dynamic classes.
- **Layer 2**: Base pipes populated at startup. Additional pipes loaded in the setup Activity. `get_required_pipe()` finds everything.

**Tier 1 -- Base Library at Worker Startup (already implemented)**:

`worker_cli.py` already loads base libraries after `Pipelex.make()`:

```python
# In configure(), after Pipelex.make(temporal_enabled=True):
library_manager = get_library_manager()
library_manager.open_library(library_id="worker_base")
effective_dirs, _ = resolve_library_dirs(library_dirs=None)
if effective_dirs:
    library_manager.load_libraries(library_id="worker_base", library_dirs=effective_dirs)
```

This generates and registers all base concept classes with Kajson, and populates the pipe library. Fixes both layers for workflows that only use base pipes/concepts (the majority of cases).

**Tier 2 -- Per-Workflow Library Context**:

For workflows with additional library content beyond the base, a `LibraryContext` model travels with the workflow:

```python
class LibraryContext(BaseModel):
    """Describes library content that must be loaded on the worker before execution."""
    bundles: list[BundleContent]                             # One or more .mthds files
    manifest_content: str | None      # METHODS.toml content, if present
    resolved_dependencies: list[ResolvedDependencyRef] | None  # pre-resolved dep refs
    fingerprint: str                  # SHA256 hash for caching
```

This replaces the naive `mthds_content: str | None` model. For the current single-file API case, it wraps the string in `bundles` with one entry. For future multi-file support, it carries the full package context.

**Changes required**:

- ~~`worker_cli.py`: Add library loading~~ (already done)
- New `LibraryContext` model in `pipelex/temporal/`
- `PipeRouterTop`: Build `LibraryContext` from the current library state when dispatching
- New `act_library_setup.py`: Activity that loads `LibraryContext` into the library (cached by fingerprint)
- `WfPipeRouter`: Call the setup Activity before `pipe.run_pipe()`

**Impact on direct execution**: None. `pipeline_run_setup()` and `PipeRouter` unchanged.

**Replay safety**: Library loading happens in Activities (replay-safe). The Activity is idempotent -- loading the same fingerprint twice is a no-op.

**Critical issue**: Layer 1 has a timing problem. Temporal automatically deserializes the PipeJob (via the data converter) *before* the workflow code runs. If the PipeJob contains custom concept instances, deserialization fails before the setup Activity can register the classes. This means **Option A alone cannot fix Layer 1 for content beyond the base library**. See Option D for the solution.

---

### Option B: Flatten All Pipes into PipeJob (Self-Contained Job)

**Summary**: At `pipeline_run_setup()` time, resolve the entire pipe tree and embed all referenced pipes directly into the PipeJob. The worker needs no library for pipe resolution.

**How it fixes each layer**:

- **Layer 1**: Does NOT fix. The `WorkingMemory` still contains `Stuff` objects with dynamic concept classes. Flattening pipes doesn't address deserialization of concept content classes.
- **Layer 2**: Fixed. `get_required_pipe()` calls replaced by lookups into a `resolved_pipes` map on the PipeJob.

**Changes required**:

- `PipeJob`: Add `resolved_pipes: dict[str, PipeAbstract]`
- All pipe controllers: Refactor to accept a pipe resolver instead of calling `get_required_pipe()` from the hub
- `pipeline_run_setup()`: Recursively resolve all child pipes and attach to PipeJob

**Impact on direct execution**: Significant. Pipe controllers currently call `get_required_pipe()` globally. Changing them to use a local resolver changes the interface everywhere, adding complexity even in direct mode. With relaxed C1, this is *allowed* but the cost is disproportionate.

**Replay safety**: Excellent. Everything needed is in the workflow input.

**Performance**: Larger PipeJob payloads. Redundant data if pipes are shared across workflows.

**Complexity**: High. Requires refactoring all pipe controllers.

**Verdict**: Fixes only Layer 2, high complexity. Not recommended as standalone approach. The key insight is: once the library is loaded on the worker (which is necessary for Layer 1 regardless), pipe resolution works identically to direct execution -- making the flattening effort unnecessary.

---

### Option C: Ship Full Library State per Workflow

**Summary**: Serialize the entire library (domains, concepts, pipes, class definitions) and include it in every workflow invocation. The worker reconstructs the library from this payload.

**How it fixes each layer**:

- **Layer 1**: Include concept structure blueprints in the payload. A pre-deserialization step regenerates dynamic classes.
- **Layer 2**: Full pipe library reconstructed from serialized state.

**Important distinction**: There are two sub-approaches here:

- **C-snapshot**: Serialize the resolved `Library` object graph. This is impractical -- `Library` includes `dependency_libraries`, dynamically generated Python types, Kajson registry state, etc. Violates C8.
- **C-sources**: Ship the source inputs (file contents, manifests, dependency metadata) and reproduce the library on the worker. This is essentially what Option A Tier 2 does with `LibraryContext`.

**Verdict for C-snapshot**: Over-engineered, poor performance, every workflow carries the entire library, risk of hitting payload size limits (C7), violates C8. Not recommended.

**Verdict for C-sources**: This is Option A Tier 2 by another name. The right principle ("reproduce from source inputs") is incorporated into the recommended approach.

---

### Option D: Deferred Deserialization

**Summary**: Instead of letting Temporal automatically deserialize the PipeJob, the workflow receives a raw payload (bytes or a lightweight wrapper). A library setup Activity runs first to load the library and register dynamic classes. Then the workflow manually deserializes the PipeJob via `kajson.loads()`.

This is designed to solve Option A's critical timing issue with Layer 1.

**How it fixes each layer**:

- **Layer 1**: Library is loaded (including dynamic class registration) *before* deserialization, so all classes exist when `kajson.loads()` runs.
- **Layer 2**: Same as Option A -- library is loaded.

**When is this needed?** Only when the workflow introduces dynamic classes not already in the worker's base library. For the common case (PIPELEXPATH-based libraries loaded at worker startup), Temporal's normal deserialization works fine because all classes are registered at startup.

**Changes required**:

- `PipeRouterTop`: Serialize PipeJob to raw JSON bytes before dispatching
- New envelope model:

```python
class TemporalPipeJobEnvelope(BaseModel):
    """Lightweight wrapper that Temporal can deserialize without dynamic classes."""
    library_context: LibraryContext | None  # None = use worker's base library
    library_dirs_fingerprint: str | None    # Verify worker's base matches API's
    raw_pipe_job_payload: bytes             # Pre-serialized PipeJob JSON
```

- `WfPipeRouter`: Accept `TemporalPipeJobEnvelope` instead of `PipeJob`. Call setup Activity if `library_context` is present, then manually `kajson.loads()` the raw payload.
- Temporal data converter: No changes -- the envelope is a simple model that deserializes without dynamic classes

**Impact on direct execution**: None. Only touches Temporal layer code.

**Replay safety**: Same as Option A -- Activity-based.

**Performance**: Minimal overhead -- one extra serialization/deserialization step.

**Complexity**: Moderate. The main conceptual shift is that the workflow input type changes from `PipeJob` to `TemporalPipeJobEnvelope`.

---

## 4. Key Dilemmas

### 4.1 Where should library loading happen?

| Location | Pros | Cons |
|----------|------|------|
| **Worker startup** (for base library) | Amortized cost, guaranteed availability, simple | Worker restart needed if base library changes. Only handles filesystem-available content. |
| **Per-workflow Activity** (for additional content) | Guarantees correct version, handles per-request content | Adds latency per workflow (mitigated by caching) |
| **Hybrid** (both) | Best of both worlds | Two loading paths to maintain |
| **Shared filesystem** (workers mount same PIPELEXPATH) | Zero additional work -- Tier 1 handles everything | Requires deployment architecture where workers access same dirs |

**Recommendation**: Hybrid, with shared filesystem as the primary deployment model. Base at startup, additional content per-workflow-with-caching. In practice, most deployments will share PIPELEXPATH, making Tier 1 sufficient for the vast majority of cases.

### 4.2 Should PipeJob carry resolved pipes or just pipe codes?

| Approach | Pros | Cons |
|----------|------|------|
| **Current** (resolved top-level only) | Minimal payload | Layer 2 breaks for children |
| **All resolved** (flattened) | Self-contained, no library needed on worker | Bloats payload, forces refactoring of controllers |
| **Codes only + worker-side resolution** | Cleanest -- worker resolves exactly like direct mode | Requires library on worker (but we need that for Layer 1 anyway) |

**Recommendation**: Codes only + worker-side resolution. Once the library is loaded on the worker (which is necessary for Layer 1 regardless), pipe resolution works identically to direct execution. No changes to controllers or the PipeJob model.

### 4.3 Dynamic class registration timing

This is the crux of the Layer 1 problem:

```
Temporal automatically deserializes workflow input
    +-- Uses data converter -> kajson.loads()
    +-- Needs dynamic classes registered BEFORE this point
    +-- But workflow code hasn't run yet -> can't load library first
```

Three approaches:

| Approach | How | Trade-off |
|----------|-----|-----------|
| **Pre-load at worker level** | Load base library at worker startup | Works for base concepts only. Additional content's concepts aren't available. |
| **Deferred deserialization** (Option D) | Send raw bytes, deserialize manually after library setup | Changes workflow input type. Small conceptual overhead. |
| **Lazy class resolution in Kajson** | Modify Kajson decoder to load classes on demand | Invasive change to a shared library. Complex. |

**Recommendation**: Pre-load at worker level for base concepts (covers the majority of cases) + deferred deserialization for additional content (Option D handles it cleanly).

### 4.4 Caching strategy

Caching is only relevant for Tier 2 (per-workflow library context). For Tier 1 (PIPELEXPATH), the library is loaded once at worker startup and persists for the worker's lifetime.

| Strategy | Cache key | Scope | Trade-off |
|----------|-----------|-------|-----------|
| **No caching** | -- | Always reload | Simple but wasteful |
| **Content-hash** | `SHA256(library_context)` | Per unique context | Handles same content from different API calls |
| **Library-ID** | `library_id` parameter | Per library instance | Uses existing `library_manager` multi-library support |

**Recommendation**: Content-hash caching for Tier 2 overlays. The `library_manager` already supports multiple concurrent libraries keyed by `library_id`. Map content hashes to library IDs. The Activity checks: "is this fingerprint already loaded?" -> skip if yes.

### 4.5 What if different workflows need different library contexts?

The `library_manager` already supports multiple concurrent libraries, and `set_current_library()` uses a `ContextVar` so different async tasks can have different current libraries. On the worker, each workflow's setup Activity would set the appropriate library ID before executing.

**Risk**: Dynamic class names could collide if two different contexts define the same concept code with different structures. Mitigation: prefix class names with a content hash, or validate that same-named concepts have identical structures.

**Assessment**: This scenario only arises with API-provided content (Tier 2). For filesystem-based libraries (Tier 1), all workers load the same content. Worth noting but not a design blocker.

### 4.6 How should the API evolve for multi-file packages?

The current `mthds_content: str | None` parameter in `pipeline_run_setup()` handles only a single `.mthds` file. Real packages are multi-file with manifests and dependencies. The API needs to evolve.

**Proposed model -- `LibraryContext`**:

```python
class BundleContent(BaseModel):
    """A single .mthds bundle file's content with its filename for domain identification."""
    filename: str        # e.g., "contracts.mthds"
    content: str         # The MTHDS TOML content

class ResolvedDependencyRef(BaseModel):
    """A pre-resolved dependency reference (address + version already resolved)."""
    alias: str           # The dependency alias in METHODS.toml
    address: str         # Resolved package address
    version: str         # Resolved version

class LibraryContext(BaseModel):
    """Complete library context that can be shipped to a worker."""
    bundles: list[BundleContent]                             # One or more .mthds files
    manifest_content: str | None = None                      # METHODS.toml content
    resolved_dependencies: list[ResolvedDependencyRef] | None = None  # Pre-resolved deps
    fingerprint: str                                         # Hash for caching
```

**How `pipeline_run_setup()` would consume it**:

The existing `mthds_content: str | None` parameter could be supplemented or replaced with a `library_context: LibraryContext | None` parameter. For backward compatibility, `mthds_content` could be sugar for a single-bundle `LibraryContext`.

**How it flows to Temporal**:

The `TemporalPipeJobEnvelope` carries `library_context`. The worker's `act_library_setup` Activity:

1. Checks `fingerprint` against cache -- skip if already loaded
2. Parses each bundle in `bundles` into a `PipelexBundleBlueprint`
3. If `manifest_content` is present, parses it and enforces visibility
4. If `resolved_dependencies` is present, loads dependency packages from installed methods (or fetches by address)
5. Calls `library_manager.load_from_blueprints()` with all blueprints

**What about dependencies that need fetching?**

For production, dependency packages should be pre-installed on the worker (via `mthds install` or shared filesystem). The `resolved_dependencies` field provides the addresses for the worker to locate them. If a dependency is not installed, the Activity can attempt to fetch it (same as `library_manager` does today for address-based deps), but this adds latency and requires network access from the worker.

**Recommendation**: Start with the `LibraryContext` model. The initial implementation can focus on the single-bundle case (wrapping current `mthds_content`). Multi-bundle support is a clear extension path without architectural changes.

---

## 5. Recommendation

**Recommended approach: Option A (base at startup) + Option D (deferred deserialization with `LibraryContext`)**

### Tier 1 -- Base Library at Worker Startup (done)

Already implemented in `worker_cli.py`. Workers load base libraries from `PIPELEXPATH` on startup. This fixes both layers for the majority of use cases where pipes and concepts come from filesystem-based packages.

### Tier 2 -- Deferred Deserialization with LibraryContext

For workflows with library content beyond the base:

1. `PipeRouterTop` builds a `LibraryContext` from the current library state (capturing what was loaded beyond PIPELEXPATH)
2. Serializes PipeJob to raw bytes
3. Wraps both in a `TemporalPipeJobEnvelope`
4. `WfPipeRouter` receives the envelope, runs `act_library_setup` Activity if `library_context` is present
5. Manually deserializes PipeJob via `kajson.loads()` after library is loaded

### Implementation Sequence

1. **(Done)** Tier 1 -- base library loading in `worker_cli.py`
2. **Integration test** -- Send a PipeSequence through Temporal with PIPELEXPATH-based library to validate Tier 1
3. **Design `LibraryContext` model** -- Start with single-bundle wrapper for current `mthds_content` behavior
4. **Implement deferred deserialization** (Option D) -- `TemporalPipeJobEnvelope`, `act_library_setup`, `WfPipeRouter` changes
5. **Library fingerprint validation** -- Worker checks its base library matches API's expectation
6. **Multi-bundle support** -- Extend `LibraryContext` to carry multiple bundles + manifest

### Why Not the Others

| Option | Why not |
|--------|---------|
| B (flatten pipes) | Doesn't fix Layer 1. High refactoring cost for marginal benefit -- once library is loaded (required for Layer 1 anyway), pipe resolution works for free. |
| C (ship library snapshot) | Serializing resolved `Library` is impractical. The right version of this idea (reproduce from sources) is what `LibraryContext` does. |

---

## 6. Appendix

### PipeJob Model

```python
class PipeJob(BaseModel):
    pipe: PipeAbstract                    # The resolved pipe object
    working_memory: WorkingMemory         # Runtime data store
    pipe_run_params: PipeRunParams        # Run mode, multiplicity, pipe stack
    job_metadata: JobMetadata             # Pipeline run ID, user ID, OTel context
    output_name: str | None = None        # Override output variable name
```

PipeJob stays unchanged -- no `mthds_content` or library context added to it. Library context travels in the `TemporalPipeJobEnvelope` wrapper, separate from the job itself.

### get_required_pipe() Call Sites in Controllers

| Controller | File | Usage |
|------------|------|-------|
| PipeSequence | `pipe_controllers/sequence/pipe_sequence.py` | Resolves each `sub_pipe.pipe_code` in the sequence |
| PipeCondition | `pipe_controllers/condition/pipe_condition.py` | Resolves the selected branch pipe from `outcome_map` |
| PipeBatch | `pipe_controllers/batch/pipe_batch.py` | Resolves `branch_pipe_code` for each batch item |
| PipeParallel | `pipe_controllers/parallel/pipe_parallel.py` | Resolves each parallel branch pipe |
| SubPipe | `pipe_controllers/sub_pipe.py` | Used during validation |

### Key Code Paths

| What | Where |
|------|-------|
| Library loading (API-side) | `pipelex/pipeline/pipeline_run_setup.py` |
| Hub singleton + get_required_pipe | `pipelex/hub.py` |
| Library manager | `pipelex/libraries/library_manager.py` |
| Dynamic concept class generation | `pipelex/core/concepts/concept_factory.py` |
| Structure generator (creates classes) | `pipelex/core/concepts/structure_generation/generator.py` |
| Kajson class registration | `pipelex/pipelex.py` (CoreRegistryModels) + `concept_factory.py` (dynamic) |
| Kajson data converter (Temporal serde) | `pipelex/temporal/temporal_data_converter.py` |
| Workflow definition | `pipelex/temporal/tprl_pipe/wf_pipe_router.py` |
| Router (Temporal) | `pipelex/temporal/tprl_pipe/pipe_router_top.py` |
| Router (direct) | `pipelex/pipe_run/pipe_router.py` |
| Worker startup (Tier 1 -- already implemented) | `pipelex/temporal/worker_cli.py` |
| MTHDS package manifest spec | `../mthds/docs/spec/manifest-format.md` |
| Namespace resolution spec | `../mthds/docs/spec/namespace-resolution.md` |
| Package loading algorithm | `../mthds/docs/implementers/package-loading.md` |
