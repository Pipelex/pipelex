# Temporal Worker Library Architecture

## The Problem

When pipelex runs pipelines via Temporal, there is a fundamental mismatch between **where the library is loaded** and **where the pipes execute**.

### Current Flow

```
API Process                                    Temporal Worker
──────────────────────────────────────────     ──────────────────────────────
PipelexRunner.execute_pipeline()
  │
  ├─ pipeline_run_setup()
  │   ├─ Loads library from PIPELEXPATH        (not here)
  │   ├─ Loads bundles from mthds_contents     (not here)
  │   ├─ Resolves pipe by code                 (not here)
  │   └─ Creates PipeJob (with pipe object)
  │
  └─ get_pipe_router().run(pipe_job)
       └─ PipeRouterTop sends PipeJob ──────►  WfPipeRouter.run(pipe_job)
          to Temporal                            └─ pipe.run_pipe()
                                                      ├─ PipeSequence → get_required_pipe() 💥
                                                      ├─ PipeCondition → get_required_pipe() 💥
                                                      ├─ PipeBatch → get_required_pipe() 💥
                                                      └─ Library not loaded on worker
```

### Why It Breaks

1. **`pipeline_run_setup()`** loads the full library (pipe definitions, concepts, etc.) into an in-memory `library_manager` singleton — but only in the **API process**.

2. The `PipeJob` sent to Temporal contains the **top-level pipe object** (serialized via Pydantic), but child pipes are referenced **by code** (e.g., `get_required_pipe("my_sub_pipe")`).

3. During execution on the Temporal worker, controllers like `PipeSequence`, `PipeCondition`, `PipeBatch`, `PipeParallel`, and `SubPipe` all call `get_required_pipe()` to resolve child pipes from the global library — which is **empty** on the worker.

4. Additionally, Temporal can **replay workflows on a different worker** after crashes or cache evictions. Any library state loaded as a side effect is lost.

### What the Library Contains

Each pipeline execution can involve:
- **Base libraries** — shared pipe/concept definitions loaded from `PIPELEXPATH` directories. These are the same for all executions.
- **Custom bundles** — per-request `mthds_contents` (MTHDS bundle strings). Each API call can bring its own method definitions. This is what makes each workflow potentially unique.

---

## Proposed Architecture

### Principles

1. **`mthds_contents` travels with the workflow input** — it is the portable, self-contained representation of custom bundles. No filesystem dependency.
2. **Workers are stateless** — any worker can handle any workflow.
3. **Library loading happens in Activities** (not in workflow code) — this is Temporal-correct: all I/O belongs in activities, making execution replay-safe.
4. **Two-tier library caching** avoids redundant reloading.

### New Flow

```
API Process                                    Temporal Worker
──────────────────────────────────────────     ──────────────────────────────
1. Validate request
2. Package raw data into                       Worker startup:
   PipelineWorkflowInput:                        └─ Load base library from
   - mthds_contents (bundle strings)                 PIPELEXPATH (Tier 1, cached)
   - pipe_code
   - inputs (serialized)
   - execution_config
3. Start workflow ──────────────────────────►  WfPipelineExecute.run(input)
                                                │
                                                ├─ Activity: setup_and_execute()
                                                │   ├─ Load mthds_contents overlay
                                                │   │   (Tier 2, cached by content hash)
                                                │   ├─ pipeline_run_setup()
                                                │   │   (library is now available)
                                                │   ├─ pipe.run_pipe()
                                                │   │   get_required_pipe() works ✅
                                                │   └─ return PipeOutput
                                                │
                                                └─ Return result
```

### Two-Tier Library Cache

| Tier | What | When loaded | Lifetime | Cache key |
|------|------|-------------|----------|-----------|
| **Tier 1 — Base library** | PIPELEXPATH directories (shared pipe definitions, standard concepts) | Worker startup | Worker lifetime | N/A (always loaded) |
| **Tier 2 — Request overlay** | `mthds_contents` (custom bundles from API request) | First use per pipeline | Evicted after pipeline completes or TTL | Content hash |

- If a request uses only base library pipes (no custom `mthds_contents`), **zero per-request loading** happens.
- If a top-level pipeline spawns child workflows on the same worker, the Tier 2 cache means the custom bundles are loaded **once**, not per child workflow.
- If a child workflow replays on a different worker, `mthds_contents` is in the workflow input — the new worker loads it (and caches it).

### What Changes

| Component | Today | Proposed |
|-----------|-------|----------|
| **Workflow input** | `PipeJob` (pre-resolved pipe object) | `PipelineWorkflowInput` (raw data: `mthds_contents`, `pipe_code`, `inputs`) |
| **Library loading** | API process only, before Temporal dispatch | Activity on the worker, per-execution |
| **Pipe execution** | Inside workflow code (non-deterministic) | Inside activity (Temporal-correct) |
| **Worker state** | Assumes library is loaded externally | Self-sufficient: base library at startup + per-request overlay |
| **`library_dirs`** | Per-request parameter | Worker configuration (PIPELEXPATH) |
| **`mthds_contents`** | Consumed in API, not sent to worker | Travels with workflow input |

### Decomposition Path (Future)

Starting with a single `setup_and_execute` activity is the pragmatic first step. Later, for better observability and granular retries, the workflow can be decomposed:

```
WfPipelineExecute.run(input)
  │
  ├─ Activity: setup_library(mthds_contents) → library loaded + cached
  │
  ├─ For PipeSequence:
  │   ├─ Child Workflow: step_1 (same mthds_contents → cache hit)
  │   ├─ Child Workflow: step_2 (cache hit)
  │   └─ Child Workflow: step_3 (cache hit)
  │
  └─ Return aggregated PipeOutput
```

Each child workflow carries `mthds_contents` for correctness, but the cache makes it free in the common case (same worker).

---

## Summary

| | Today | Proposed |
|---|---|---|
| **Works with Temporal?** | No — library not on worker | Yes — library loaded on worker |
| **Replay-safe?** | No — library is a side effect | Yes — activity re-executes cleanly |
| **Per-request library cost** | Loads everything every time | Base cached at startup, overlay cached by hash |
| **Custom bundles** | Lost at Temporal boundary | Travel with workflow input |
| **Worker requirements** | Must have library pre-loaded somehow | Stateless (PIPELEXPATH + mthds_contents) |
