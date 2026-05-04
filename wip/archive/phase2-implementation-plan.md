# Phase 2 Implementation Plan: LibraryCrate on Temporal

> **Status**: Reviewed, ready to implement (updated after feature/LibraryCrate merge — 5477e16a, then crate design review — Option A chosen)
> **Date**: 2026-03-25
> **Related**: [00-master-plan.md](00-master-plan.md), [phase2-crate-propagation-rationale.md](phase2-crate-propagation-rationale.md), [future-crate-first-architecture.md](future-crate-first-architecture.md)
> **Review**: Eng review passed (0 critical gaps). Codex outside voice: 7 findings, all addressed. Crate design review: Option A (blueprint accumulation) chosen over Option B (crate merge).

---

## Context

Phase 0 (pipe_ref fix) and Phase 1 (LibraryCrate in direct mode) are complete. Temporal workers currently cannot resolve child pipes from `mthds_content` or extra `library_dirs` because those definitions only exist on the API/submitter side. Phase 2 ships the `LibraryCrate` inside `PipeJob` so every worker — including child workflows on different machines — receives the full library context.

**What this solves**: Pipe controllers (PipeSequence, PipeCondition, PipeBatch, PipeParallel) work on Temporal workers. `get_required_pipe()` succeeds for all pipes in the library.

**What this does NOT solve**: Layer 1 (dynamic class deserialization for custom concepts). That's Phase 3.

---

## Key Architecture Decisions

1. **Crate on PipeJob** — `library_crate: LibraryCrate | None = None` field on `PipeJob`. Threaded through the signature chain as an optional parameter. (Rationale: [phase2-crate-propagation-rationale.md](phase2-crate-propagation-rationale.md))

2. **Self-contained crate** — The crate carries ALL blueprints (PIPELEXPATH + mthds_content + extra library_dirs). Workers don't assume anything is pre-loaded.

3. **Blueprint accumulation on LibraryManager** — `_blueprints: dict[str, list[PipelexBundleBlueprint]]` tracks all blueprints loaded per `library_id`. Each `load_from_blueprints()` call appends to the list. `get_crate(library_id)` builds one crate from all accumulated blueprints via `LibraryCrateFactory.make_from_blueprints()`. No merge logic, no crate accumulation — blueprints are the unit of accumulation. See [future-crate-first-architecture.md](future-crate-first-architecture.md) for the rationale.

4. **Per-workflow library on workers** — Each `WfPipeRouter` opens its own library using a unique ID derived from `workflow.info().workflow_id` (e.g., `f"wf_{workflow_id}"`). Full isolation — parent and child workflows from PipeParallel/PipeBatch get different IDs. Teardown after execution.

5. **Inline loading (no activity)** — Crate loading is pure in-memory work. No Temporal activity needed.

6. **Fingerprint idempotency** — `load_from_crate()` skips if a crate with the same fingerprint was already loaded into the same `library_id`.

---

## Data Flow

```
SUBMITTER (pipeline_run_setup)
════════════════════════════════════════════════════════
  load_libraries(library_id, dirs)          ─┐
    → load_from_blueprints(blueprints)       │  Each call appends blueprints
      → _blueprints[library_id] += blueprints│  to the accumulation list,
      → LibraryCrateFactory → crate          │  then loads from crate
      → load_from_crate(library_id, crate)  ─┘  as today

  [if mthds_content]
  load_from_blueprints(library_id, mthds_blueprints)
    → same path → blueprints appended to _blueprints[library_id]

  library_crate = library_manager.get_crate(library_id)
    → LibraryCrateFactory.make_from_blueprints(_blueprints[library_id])
    → one crate from ALL accumulated blueprints
  pipe_job = PipeJobFactory.make_pipe_job(..., library_crate=library_crate)


TEMPORAL DISPATCH
════════════════════════════════════════════════════════
  PipeRouterTop._run_pipe_job(pipe_job)
    → WfPipeRouter workflow(pipe_job)    [can land on ANY worker]


WORKER (WfPipeRouter.run)
════════════════════════════════════════════════════════
  wf_library_id = f"wf_{workflow.info().workflow_id}"
  library_manager.open_library(library_id=wf_library_id)
  set_current_library(library_id=wf_library_id)
  library_manager.load_from_crate(wf_library_id, pipe_job.library_crate)

  pipe.run_pipe(..., library_crate=pipe_job.library_crate)
    → [controller] _live_run_controller_pipe(..., library_crate)
      → SubPipe.run_pipe(..., library_crate)
        → PipeJobFactory.make_pipe_job(..., library_crate)  # child carries crate
          → PipeRouterChild → new WfPipeRouter(child_pipe_job)
            [cycle repeats on potentially different worker]

  library_manager.teardown(library_id=wf_library_id)
  teardown_current_library()
```

---

## Implementation Steps

### Step 1: Blueprint accumulation + get_crate + fingerprint idempotency

**Tests first** (`tests/unit/pipelex/libraries/test_library_crate_accumulation.py`):
- `get_crate(library_id)` builds crate from all accumulated blueprints
- `get_crate(library_id)` returns `None` for unknown library_id
- `get_crate(library_id)` returns `None` when no blueprints were loaded
- Blueprints from multiple `load_from_blueprints()` calls are all included in the crate
- `load_from_crate()` returns `[]` on second call with same fingerprint (idempotency)
- `teardown()` clears blueprints for that library_id

**Then implement:**

**File**: `pipelex/libraries/library_manager.py`
- Add `_blueprints: dict[str, list[PipelexBundleBlueprint]]` field alongside `_libraries`
- In `load_from_blueprints()`:
  - Append `blueprints` to `_blueprints[library_id]` (before or after the existing crate build + load)
- In `load_from_crate()`:
  - Check fingerprint idempotency (skip if already seen for this library_id)
- Add `get_crate(library_id) -> LibraryCrate | None`: if `_blueprints[library_id]` exists and is non-empty, call `LibraryCrateFactory.make_from_blueprints()` with the full accumulated list; otherwise return `None`
- Clear `_blueprints[library_id]` in `teardown(library_id)` and `reset()`

**File**: `pipelex/libraries/library_manager_abstract.py`
- Add abstract `get_crate(library_id) -> LibraryCrate | None`

**No changes to `pipelex/libraries/library_crate.py`** — no `merge()` method needed.

---

### Step 2: Add `library_crate` field to PipeJob and PipeJobFactory

**File**: `pipelex/pipe_run/pipe_job.py`
- Add `library_crate: LibraryCrate | None = None` field

**File**: `pipelex/pipe_run/pipe_job_factory.py`
- Add `library_crate: LibraryCrate | None = None` param to `make_pipe_job()`, forward to PipeJob constructor

---

### Step 3: Thread `library_crate` through the signature chain

Add `library_crate: LibraryCrate | None = None` as the last parameter. Use `TYPE_CHECKING` import.

#### 3a. PipeAbstract (`pipelex/core/pipes/pipe_abstract.py`)

`@final` methods — add param and forward:
- `run_pipe()` → `live_run_pipe()` / `dry_run_pipe()`
- `live_run_pipe()` → `_live_run_pipe()`
- `dry_run_pipe()` → `_dry_run_pipe()`

Abstract methods — signature only:
- `_live_run_pipe()`
- `_dry_run_pipe()`

#### 3b. PipeOperator (`pipelex/pipe_operators/pipe_operator.py`)

Accept but do NOT forward deeper:
- `_live_run_pipe()` — receives `library_crate`, does NOT pass to `_live_run_operator_pipe()`
- `_dry_run_pipe()` — same

The 6 concrete operators (PipeLLM, PipeExtract, PipeSearch, PipeImgGen, PipeFunc, PipeCompose) need NO changes.

#### 3c. PipeController (`pipelex/pipe_controllers/pipe_controller.py`)

Add param and forward:
- `_live_run_pipe()` → `_live_run_controller_pipe()`
- `_dry_run_pipe()` → `_dry_run_controller_pipe()`
- `_live_run_controller_pipe()` (abstract) — signature only
- `_dry_run_controller_pipe()` (abstract) — signature only

#### 3d. Controller implementations

**PipeSequence** (`pipe_controllers/sequence/pipe_sequence.py`):
- `_live_run_controller_pipe()`: pass to `sub_pipe.run_pipe()` calls
- `_dry_run_controller_pipe()`: forward to `_live_run_controller_pipe()`

**PipeParallel** (`pipe_controllers/parallel/pipe_parallel.py`):
- `_live_run_controller_pipe()`: pass to `sub_pipe.run_pipe()` calls
- `_dry_run_controller_pipe()`: pass to `sub_pipe.run_pipe()` calls

**PipeBatch** (`pipe_controllers/batch/pipe_batch.py`):
- `_live_run_controller_pipe()`: pass to `PipeJobFactory.make_pipe_job()` calls
- `_dry_run_controller_pipe()`: forward to `_live_run_controller_pipe()`

**PipeCondition** (`pipe_controllers/condition/pipe_condition.py`):
- `_live_run_controller_pipe()`: pass to `PipeJobFactory.make_pipe_job()`
- `_dry_run_controller_pipe()`: pass to `pipe.run_pipe()` calls

#### 3e. SubPipe (`pipelex/pipe_controllers/sub_pipe.py`)

Add `library_crate` to `run_pipe()`. Forward to all 3 `PipeJobFactory.make_pipe_job()` calls (batch, condition, normal).

---

### Step 4: Update PipeRouter (direct) and WfPipeRouter (Temporal)

#### 4a. PipeRouter (`pipelex/pipe_run/pipe_router.py`)

In `_run_pipe_job()`: pass `library_crate=pipe_job.library_crate` to `pipe.run_pipe()`.

#### 4b. WfPipeRouter (`pipelex/temporal/tprl_pipe/wf_pipe_router.py`)

In `run()`:
1. Derive unique library ID: `wf_library_id = f"wf_{workflow.info().workflow_id}"`
2. Open per-workflow library: `library_manager.open_library(library_id=wf_library_id)`
3. Set as current: `set_current_library(library_id=wf_library_id)`
4. If `library_crate` present: `library_manager.load_from_crate(wf_library_id, crate)`
5. Run pipe with `library_crate=workflow_arg.library_crate`
6. In finally block: `library_manager.teardown(library_id=wf_library_id)` + `teardown_current_library()`

---

### Step 5: Build and attach crate in `pipeline_run_setup()`

**File**: `pipelex/pipeline/pipeline_run_setup.py`

**Note**: After the feature/LibraryCrate merge, `mthds_content` is now `mthds_contents: list[str] | None` and `bundle_uri` is now `bundle_uris: list[str] | None`. The crate accumulation approach is unaffected — both `load_libraries()` and `load_from_blueprints()` go through `load_from_crate()` which accumulates into `_crates[library_id]`.

After all library loading (load_libraries + load_from_blueprints), before creating PipeJob:

```python
library_crate = library_manager.get_crate(library_id)

pipe_job = PipeJobFactory.make_pipe_job(
    ...,
    library_crate=library_crate,
)
```

No manual crate building or merging needed — `get_crate()` returns the accumulated result.

---

### Step 6: Run checks and tests

1. `make agent-check` — lint + type check
2. `make agent-test` — full test suite

---

## NOT in scope

- **Layer 1 (dynamic class deserialization)** — Phase 3. When `mthds_content` introduces custom concepts with dynamic classes, Kajson can't deserialize WorkingMemory on the worker. Deferred.
- **StoragePayloadCodec** — Phase 4. For payloads exceeding 2MB. Not needed for typical libraries.
- **Crate stripping** — Future. Only shipping the transitive closure of pipe dependencies. Optimization.
- **Library fingerprint validation** — Future. Verifying worker's base library matches API's expectation.

### Phase 2 Known Limitations (from Codex review)

- **Cross-package address-based dependencies** — `load_from_crate()` does not resolve `alias->domain.pipe` refs. Pipes with cross-package deps won't resolve on workers. Scoped to packages using METHODS.toml dependency declarations.
- **Python-backed libraries** — `PipeFunc` (requires function registry) and `structure = "ExistingClass"` concepts (requires class registry) won't work on workers. `load_from_crate()` doesn't import Python modules. Standard pipe types (LLM, extract, search, compose) work fine.
- **Payload duplication in fanout** — PipeBatch/PipeParallel create N child PipeJobs, each carrying the full crate. Redundant for siblings on the same worker. Optimization via StoragePayloadCodec (Phase 4) or crate stripping (future).

---

## What already exists

| What | Where | Reuse |
|------|-------|-------|
| `LibraryCrate` model | `pipelex/libraries/library_crate.py` | Reuse as-is (no merge needed) |
| `LibraryCrateFactory.make_from_blueprints()` | `pipelex/libraries/library_crate_factory.py` | Reuse as-is |
| `LibraryManager.load_from_crate()` | `pipelex/libraries/library_manager.py` | Phase 1 — add fingerprint check |
| `load_from_blueprints()` → crate path | `library_manager.py:432` | Already builds crate internally, calls `load_from_crate` |
| `PipeFactory.make_pipe_ref_with_domain()` | `core/pipes/pipe_factory.py:41` | New helper — not needed in `merge()` (keys already qualified) |
| `ConceptFactory.make_concept_ref_with_domain()` | `core/concepts/concept_factory.py:213` | New helper — not needed in `merge()` (keys already qualified) |
| `LibraryCrate.compute_fingerprint_from_content()` | `libraries/library_crate.py` | Static method — used by `LibraryCrateFactory` |
| Worker base library loading | `temporal/worker_cli.py:65` | Exists — worker_base library |
| Kajson data converter | `temporal/temporal_data_converter.py` | Handles PipeJob serialization |
| `PipeRouterProtocol.run()` | `pipe_run/pipe_router_protocol.py` | Unchanged — PipeJob carries crate |

---

## Failure modes

| Codepath | Failure scenario | Test coverage | Error handling | User impact |
|----------|-----------------|---------------|----------------|-------------|
| Crate serialization | LibraryCrate too large for Temporal 2MB limit | Phase 4 test | Temporal raises PayloadTooLarge | Error visible in dashboard |
| Fingerprint collision | Two different crates with same SHA256 | Astronomically unlikely | Second load skipped silently | Wrong pipes loaded — very unlikely |
| Worker library teardown | Exception during pipe execution skips teardown | Needs try/finally | Add finally block in WfPipeRouter | Memory leak on worker |
| Concurrent crate loading | Two workflows load same crate simultaneously | Thread-safe via GIL | No issue in Python | None |
| Direct mode crate cleanup | `runner.py:199` calls `library.teardown()` directly, not `library_manager.teardown()` | Fix in Step 1 | Change `runner.py` to call `library_manager.teardown(library_id)` instead | Stale `_crates` state in direct mode if not fixed |

No critical gaps — all failure modes have either test coverage, error handling, or are handled by existing infrastructure.

**Note on fingerprint scope**: `compute_fingerprint()` hashes concepts + pipes only (not domains/source_map). This is intentional — domains carry metadata (description, system_prompt) that doesn't affect pipe resolution. If domain metadata changes become significant, fingerprint scope can be expanded later.

**Note on crate design**: Option A (blueprint accumulation) was chosen over Option B (crate merge). See [future-crate-first-architecture.md](future-crate-first-architecture.md) for the full rationale. In short: accumulating blueprints is simpler (no merge logic, no crate accumulation dict, no fingerprint recomputation) and directionally correct toward the future crate-first architecture.

---

## Verification

### Automated
- All existing tests pass (library_crate=None flows through silently in direct mode)
- New unit tests for merge, fingerprint idempotency, get_crate
- `make agent-check` passes
- `make agent-test` passes

### Manual (Temporal dev setup)
- 3-terminal Temporal dev setup (server + worker + job submitter)
- Submit a PipeSequence job with `mthds_content` containing additional pipes
- Verify child pipes resolve on the worker
- Check Temporal dashboard: crate visible as structured JSON in PipeJob workflow input

---

## File Summary

| File | Change |
|------|--------|
| `pipelex/libraries/library_crate.py` | No changes needed |
| `pipelex/libraries/library_manager.py` | Add `_blueprints` dict, accumulate in `load_from_blueprints()`, fingerprint idempotency in `load_from_crate()`, `get_crate()` builds crate from accumulated blueprints |
| `pipelex/libraries/library_manager_abstract.py` | Add abstract `get_crate()` |
| `pipelex/pipe_run/pipe_job.py` | Add `library_crate` field |
| `pipelex/pipe_run/pipe_job_factory.py` | Add `library_crate` param |
| `pipelex/core/pipes/pipe_abstract.py` | Add `library_crate` param to `run_pipe`, `live_run_pipe`, `dry_run_pipe`, `_live_run_pipe`, `_dry_run_pipe` |
| `pipelex/pipe_operators/pipe_operator.py` | Add `library_crate` param to `_live_run_pipe`, `_dry_run_pipe` (accept, ignore) |
| `pipelex/pipe_controllers/pipe_controller.py` | Add `library_crate` param to 4 methods |
| `pipelex/pipe_controllers/sequence/pipe_sequence.py` | Forward `library_crate` to `sub_pipe.run_pipe()` |
| `pipelex/pipe_controllers/parallel/pipe_parallel.py` | Forward `library_crate` to `sub_pipe.run_pipe()` |
| `pipelex/pipe_controllers/batch/pipe_batch.py` | Forward `library_crate` to `PipeJobFactory.make_pipe_job()` |
| `pipelex/pipe_controllers/condition/pipe_condition.py` | Forward `library_crate` to `PipeJobFactory.make_pipe_job()` / `pipe.run_pipe()` |
| `pipelex/pipe_controllers/sub_pipe.py` | Add `library_crate` param, forward to `PipeJobFactory.make_pipe_job()` |
| `pipelex/pipe_run/pipe_router.py` | Pass `library_crate` from PipeJob to `run_pipe()` |
| `pipelex/temporal/tprl_pipe/wf_pipe_router.py` | Per-workflow library lifecycle + load crate + pass to `run_pipe()` |
| `pipelex/pipeline/pipeline_run_setup.py` | Read crate via `get_crate()`, attach to PipeJob |
| `pipelex/pipeline/runner.py` | Fix teardown: call `library_manager.teardown(library_id)` instead of `library.teardown()` |
| `tests/unit/pipelex/libraries/test_library_crate_accumulation.py` | New: blueprint accumulation, idempotency, get_crate tests |
