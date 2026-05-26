# Dry-Run Refactor Plan — for outside-voice review

## Context

Pipelex is a Python runtime that executes "MTHDS" pipelines. A pipeline is a graph of pipes (LLM calls, controllers like sequence/parallel/batch/condition, etc.). The runtime supports a DRY mode that swaps real LLM/IO calls for mock outputs so the pipeline can be validated end-to-end without spending money or making network calls.

The hosted deployment runs LIVE pipelines on Temporal (workflows on remote workers). Today, DRY mode has accumulated several parallel code paths that don't go through the same orchestration as LIVE.

## Audit findings (pre-plan)

Architecture today:

- **`PipelexRunner`** — top-level entry. Builds a `PipeJob` via `pipeline_run_setup`, then calls `pipe_run.run(pipe_job, delivery_assignment)`.
- **`PipeRun` (local) / `TemporalPipeRun` (hosted)** — orchestrator. Calls the router, then DeliveryExecutor.
- **`PipeRouter` (local) / `TemporalPipeRouter` (hosted)** — calls `pipe.run_pipe(...)` (local) or kicks off `WfPipeRouter` as a Temporal workflow.
- **`PipeAbstract._run_pipe_traced`** — matches on `pipe_run_params.run_mode` and dispatches to `live_run_pipe()` or `dry_run_pipe()` at the pipe level.
- Hub swap at `pipelex/pipelex.py:443-461`: if `config.temporal.is_enabled`, registers Temporal variants; otherwise local. One swap per process at boot.

Parallel dry-run code that bypasses the unified path:

- `pipelex/pipe_run/dry_run.py` — `dry_run_pipe`, `dry_run_pipes`, `DryRunStatus`, `DryRunOutput`, `DryRunError`, `allowed_to_fail_pipes` config aggregation, `convert_to_working_memory_format`.
- `pipelex/pipe_run/dry_run_pipeline.py` — wraps PipelexRunner with mode=DRY + main_pipe extraction + forced `generate_graph=True, mock_inputs=True`.
- `pipelex/pipe_run/dry_run_with_graph.py` — single-pipe path that manually opens GraphTracer and calls `pipe.run_pipe(...mode=DRY)`. Bypasses PipelexRunner.
- `pipelex/pipe_run/dry_pipe_router.py` — `DryPipeRouter` that calls `pipe.dry_run_pipe(...)` directly. **Dead code — never instantiated**; the regular `PipeRouter` routes DRY correctly because the mode dispatch lives in the pipe.

Other related smells:

- `_run_core.py:178-203` (CLI) writes `main_stuff.json`, `main_stuff.md`, `main_stuff.html`, `main_stuff_viewer.html`, `working_memory.json`, graph files by hand — duplicating `DeliveryExecutor.generate_result_files`.
- `pipelex/pipeline/validate_bundle.py` has THREE commented-out `dry_run_pipes(...)` calls (lines 137, 144, 161) marked `# TODO: wip - restore or refactor dry run`. Bundle validation currently does NO dry-run validation — silent regression since the Temporal merge.
- `PipeRouter` is a trivial 1-line wrapper around `pipe.run_pipe()`. It earns its keep only because `PipeRouterProtocol` is the seam that lets `TemporalPipeRouter` exist.

## Decided design

**Principles** (user-stated, repeatedly):

> "A run is a run, whether it's dry or live or else, it's the SAME THING. The delivery, the preparation, should go through the SAME thing."
>
> "Everything should go through the PipelexRunner. Runner protocol. JUST FUCKIN DROP those dry-run functions."
>
> "The CLI should ONLY CALL THE PIPELEXRUNNER with the right configuration. There SHOULDN'T BE A dry-run CLI; it should be the RUN cli with a dry mode."

**Concrete plan (single PR):**

1. **Delete** `dry_run.py`, `dry_run_pipeline.py`, `dry_run_with_graph.py`, `dry_pipe_router.py` entirely. Including: `DryRunStatus`, `DryRunOutput`, `DryRunError`, `allowed_to_fail_pipes` config. No relocation — these types should not exist. Dry-runs return `PipeOutput` (with mock content) and raise `PipelineExecutionError` on failure, symmetric with live runs.

2. **PipelexRunner enforces routing** (Option A from review). In `_resolve_pipe_run()`: if `pipe_run_mode == DRY`, build/use a local `PipeRun(pipe_router=PipeRouter())`, regardless of hub default. If LIVE, use hub default (Temporal in pipelex-api-deploy). Per-request explicit `pipe_run` override beats both.

3. **Delivery is mode-agnostic (Framing B).** `PipeRun.run()` does not gate on mode. Whatever `DeliveryAssignment` the caller passes is honored. Policy of "no S3/webhook for DRY in hosted API" lives at the API endpoint (caller decides what target to pass), not in the runtime.

4. **Validators migrate to PipelexRunner.** Six callsites (`cli/commands/validate/_validate_core.py:69,112`, `cli/agent_cli/commands/validate/_validate_core.py:46,114,150`, `builder/operations/validate_ops.py:46,150,185`, `builder/operations/runner_code_ops.py:45`, `pipeline/validate_bundle.py:217`) become `try/except` loops over `runner.execute_pipeline(pipe_code=p, pipe_run_mode=DRY, mock_inputs=True)`. Failures aggregated into `dict[str, str]`.

5. **Restore validate_bundle dry-on-load.** Uncomment lines 137/144/161, migrated to runner. Closes the silent regression.

6. **`convert_to_working_memory_format` and mock-input generation move into PipelexRunner.** When `mock_inputs=True` and no inputs are provided, the runner generates them via the existing `WorkingMemoryFactory.make_mock_inputs`. Validators stop building their own.

7. **`graph_rendering.py:132`** (only consumer of `dry_run_pipeline`) becomes a direct `runner.execute_pipeline(pipe_run_mode=DRY, generate_graph=True)` call; reads `response.pipe_output.graph_spec`.

8. **MUST-add regression test:** `validate_bundle.py` dry-on-load surfaces broken pipes. The test loads a bundle with a top-level controller pipe that recursively calls a broken sub-pipe; asserts `ValidateBundleResult.dry_run_result` contains the sub-pipe failure with usable context.

**Explicitly out of scope:** API endpoint unification (`/validate`+`/execute` → `/run` in pipelex-api — follow-up); CLI artifact dedup (depends on `LocalStorageProvider` per-request root design — separate PR); renaming `WfPipeRouter`/`WfPipeRun` for clarity.

**Kept as-is:** `PipeRouterProtocol`, `PipeRunProtocol`, the Router/Run two-layer split (mirrors Temporal parent/child workflow shape), pipe-level `_dry_run_pipe`/`_dry_run_operator_pipe`/`_dry_run_controller_pipe` methods (legitimate boundary — the only place `run_mode` should matter).

## Load profile (FastAPI concern)

Concern: pipelex-api will have a dry-run endpoint that stays in-process while live runs go to Temporal. Could thousands of concurrent dry-runs overload uvicorn workers?

Audit: dry-run path is CPU-only. Verified no `requests`/`httpx`/`aiohttp`/`open()`/`subprocess` reachable. `ContentGeneratorDry` returns canned strings; `DryRunFactory` (polyfactory) builds mock Pydantic objects. Per dry-run: 5-50 ms (Pydantic + Jinja2), 1.5-2 MB memory, 1 lock (schema codegen cache, uncontended post-warmup). Estimated ~20k dry-runs/sec/worker. Verdict: safe in-process. Caveat: user-defined `PipeFunc` could blocking-IO in dry mode (not short-circuited) — surface as a contract.

## Performance impact of validator migration

Today's validator bypasses `pipeline_run_setup` (calls `pipe.run_pipe(...)` directly). After: each runner invocation pays setup cost (~10-15ms vs ~5ms). User correctly noted: dry-running a controller recursively dry-runs children, so a 50-pipe bundle is ~5-10 top-level invocations, not 50. ~50-150ms overhead — accepted, not a hot path.

## What you're being asked to find

This plan has been through a structured eng-review. Don't repeat that. Find what it missed:

- Unstated assumptions that survived the review.
- Overcomplexity: is there a meaningfully simpler approach that achieves the same goal?
- Feasibility risks the review took for granted (e.g., does PipelexRunner actually support per-request `pipe_run` injection cleanly when `pipeline_run_setup` is also in the call path? does the mock-input generation logic plug into the runner without bigger refactors?).
- Sequencing issues (which deletion/migration ordering minimizes broken intermediate states?).
- Strategic miscalibration: is "DRY → always local" actually correct? Edge case: user-defined dynamic concepts loaded only in the Temporal worker — would a local dry-run fail to resolve them?
- Anything about the Framing B "delivery is mode-agnostic" decision that could bite (e.g., webhook accidentally fired during a CI dry-run because of a config typo).

Be direct. Be terse. No compliments. Just the problems.
