# Fix: `/validate` dry-run leaked nested controller sub-pipes to Temporal

> **Status: DONE.** Bug fixed and all three layers of test coverage are in place. This doc is the PR-review guide — what the bug was, what changed, why it's correct, and how it's guarded.
>
> **Stacking:** this branch (`fix/Temporal-dry-run`) is stacked on `feature/PipeSearch-Temporal` (open PR [#974](https://github.com/Pipelex/pipelex/pull/974)). The `pipe_search.py` / `search_generate.py` / `content_generator_in_workflow.py` / `native_search.mthds` / `structured_search.mthds` / `test_workflow_search_*` files in the diff belong to **#974**, not to this change — review them there. The files owned by **this** change are listed under [Files in this change](#files-in-this-change) below.

**Where the fix lives:** `pipelex` core (the runtime), **not** `pipelex-api`. All paths are relative to the `pipelex` repo (locally the editable `_search` worktree). No change was needed in `pipelex-api`.

## Symptom

With the API running Temporal-enabled (`.pipelex/pipelex_override.toml` → `[temporal] is_enabled = true`, task queue `pipelex_dev`) and a worker up:

- `make bundle-validate BUNDLE=.../fashion_moodboard` → **HTTP 422**
- `make bundle-validate BUNDLE=.../joke_judge` → **OK**
- `make bundle-run BUNDLE=.../fashion_moodboard` (full run) → **OK**
- `pipelex validate bundle .../fashion_moodboard` (CLI) → **OK**

The 422 body:

```
ValidateBundleError (error_domain=input), 422
detail: "Dry run failed with 1 unexpected pipe failure(s):
  'fashion_moodboard.create_moodboards': ... status=DryRunStatus.FAILURE
  error_message=\"Dry run failed for pipe 'fashion_moodboard.create_moodboards':
  Failed to execute workflow WfPipeRouter\""
```

The string **"Failed to execute workflow WfPipeRouter"** (no trailing detail) is produced only at `pipelex/temporal/tprl/workflow_caller.py:136`, the `(WorkflowAlreadyStartedError, RPCError)` branch of `WorkflowExecutor.execute_workflow` — i.e. a **top-level** Temporal workflow dispatch from the submitter side. A dry run should never reach that code.

## Root cause

The `/validate` path runs an **in-process** dry-run sweep, but nested controller sub-pipes leaked out to the Temporal router.

Flow: `api/routes/pipelex/validate.py` → `validate_bundle()` (`pipelex/pipeline/validate_bundle.py`) → `BundleValidator.validate_pipes()` (`pipelex/pipeline/bundle_validator.py`).

`BundleValidator` deliberately builds a **local, in-process** execution primitive so the sweep never touches Temporal — its own module docstring says so. **But that local router was only used for the _top-level_ pipe.** Every controller dispatches its nested sub-pipes through the **hub's** `get_pipe_router()`, not the injected router. This is broad — it is **not** specific to `PipeBatch`:

```python
# pipelex/pipe_controllers/batch/pipe_batch.py  (_live_run_controller_pipe)
return await get_pipe_router().run(pipe_job=PipeJobFactory.make_pipe_job(...))

# pipelex/pipe_controllers/sub_pipe.py  (SubPipe.run_pipe — used by EVERY PipeSequence step;
# also the inline `batch_over` path and the PipeCondition path)
pipe_output = await get_pipe_router().run(pipe_job=PipeJobFactory.make_pipe_job(...))
```

`get_pipe_router()` (`pipelex/hub.py`) returns a contextvar override **if one is set**, else the hub default. In the Temporal-enabled API process the hub default is the **`TemporalPipeRouter`** (wired in `pipelex/pipelex.py` when `get_config().temporal.is_enabled`). Called from the API process — i.e. **outside** any Temporal workflow (`is_in_temporal_workflow()` is False) — `TemporalPipeRouter._run_pipe_job` took the **top-level dispatch** branch → `executor.execute_workflow(WfPipeRouter, ...)` → failed → "Failed to execute workflow WfPipeRouter". The per-pipe dry run was marked `FAILURE`, `BundleValidator._aggregate` raised `DryRunError`, `validate_bundle` translated it to `ValidateBundleError`, and the global handler rendered 422.

`BundleValidator` built the in-process router but **never installed it as the `scoped_pipe_router(...)` override**, so the nested controllers fell through to the hub default (Temporal).

## FAIL vs. FALSE-PASS — the leak happened always; only some shapes 422'd

The leak (nested dispatch → `TemporalPipeRouter`) happened for **every** bundle with a controller. Whether the dry run **failed** depended on a Temporal **workflow-id collision**:

- `make_top_workflow_id` (`pipelex/temporal/temporal_manager.py`) is `f"{prefix}{pipeline_run_id}"` — derived from `pipeline_run_id` **alone**. The whole sweep shares **one** `dry_run_pipeline_id`, so **every** top-level Temporal dispatch in a sweep computed the **same** workflow id.
- `WorkflowExecutor.execute_workflow` **waits for completion**, and no `id_reuse_policy` is set → Temporal's default `ALLOW_DUPLICATE` (reuse allowed once the prior run has *closed*). So **serial** dispatches reusing that id are fine; only **concurrent** same-id dispatches collide → `WorkflowAlreadyStartedError` → `WorkflowExecutionError("Failed to execute workflow WfPipeRouter")`. (`WorkflowExecutionError` is a `PipelexError`, so it records as a dry-run `FAILURE` → 422, not a 500.)

The deciding structural factor is **standalone batch/parallel vs. batch-reached-as-a-sub-pipe**:

- A **standalone top-level `PipeBatch`/`PipeParallel`** the sweep dry-runs *directly* runs its top level on the local in-process router, but its **fan-out loop executes in the API process** (`_live_run_controller_pipe` → `gather_bounded`) and fires **N concurrent top-level Temporal dispatches** with the same id → collision → **FAILURE**. A mocked "multiple" list yields `nb_stuffs = 3`, so N≥2.
- A **batch reached as a sub-pipe** (inline `batch_over` step, or a batch nested under a sequence/parallel) is dispatched as a **single** top-level workflow — the fan-out into branches then happens **inside the worker** as child workflows (legal). Sequence steps run serially, so it's one dispatch at a time → **no concurrent collision** → it **passed** (still round-tripping Temporal, just not colliding — a false pass).

So `fashion_moodboard`'s `create_moodboards` (a standalone `PipeBatch`) 422'd, while a sequence-nested batch silently round-tripped Temporal and passed. The fix removes the Temporal round-trip for the whole sweep, fixing both the real failure **and** the silent false-pass leak.

## The fix as shipped

### Part 1 — scope the in-process router for the whole sweep (commit `3377babb`)

The codebase had already solved this exact leak for DIRECT mode in `pipelex/runtime_bridge/bridge.py::_run_direct`, with a comment describing the precise failure mode. `BundleValidator` now applies the same guard around its dry-run sweep:

1. `__init__` keeps the router instance instead of discarding it inside `PipeRun(...)`:
   ```python
   self._pipe_router = PipeRouter(observer=ObserverNoOp())
   self._pipe_run: PipeRunProtocol = PipeRun(pipe_router=self._pipe_router)
   ```
2. `validate_pipes` wraps the **per-pipe dry-run sweep loop** (step 4) in `scoped_pipe_router`:
   ```python
   with scoped_pipe_router(self._pipe_router):
       for pipe in sweepable_pipes:
           results[pipe.pipe_ref] = await self._classify_pipe(...)
   ```
   Wrapping `validate_pipes` covers all entry points (`acquire_and_validate`, `validate_current_library`, and the direct `validate_bundle` path all funnel through it). Steps 1–3 (wiring check, signature pre-pass, telemetry) don't run pipes, so they don't need the scope.

**Why it's safe:**

- `scoped_pipe_router` is **contextvar-scoped** and restores the prior value on exit, so concurrent `/validate` requests don't leak into each other.
- `PipeBatch` fans branches out via `gather_bounded` → `asyncio.gather`, whose Tasks copy the current context at creation (and creation happens inside the `with` scope), so each branch task inherits the override and resolves the in-process router too.

### Part 2 — `--temporal/--no-temporal` flag on `validate` (commit `b8eadeda`)

A `--temporal/--no-temporal` flag was added to `pipelex validate bundle`, `pipe`, and `method` (and therefore `validate --all`, which routes to `validate pipe`), giving parity with `pipelex run`. It threads through `_validate_core.execute_validate(temporal=...)` → `make_pipelex_for_cli(temporal_enabled=...)`, overriding `temporal.is_enabled` **for the boot only**.

**This flag is behavior-neutral for validation today.** The sweep always runs in-process regardless of the flag (Part 1 guarantees that). The flag does not change *what* validation does — it controls *how Pipelex boots*, which is the lever for exercising the "validation stays in-process even on a Temporal-enabled hub" contract without juggling a `pipelex_temporary_override.toml`. It is also forward-looking: once validation runs as a standalone Temporal activity ([`wip/dry-run-refactor/followup-temporal-validation-activity.md`](wip/dry-run-refactor/followup-temporal-validation-activity.md)), `--temporal` stops being a no-op and becomes the switch that dispatches the sweep through that activity.

## Reviewer note — the graph step was deliberately NOT changed

An earlier diagnosis claimed the best-effort **graph** step in `validate.py` — `dry_run_pipeline()` (`pipelex/pipe_run/dry_run_pipeline.py`) → `PipelexRunner(...).execute_pipeline(...)` — had "the same leak." **It does not**, and an attempt to "fix" it was **reverted**. The graph step does a **single** top-level dispatch of the main pipe — no concurrent same-id collision — so under Temporal it dispatches the one workflow to the worker, which (tracing enabled, `backend = "temporal_dynamodb"`) assembles the `GraphSpec` and returns it on `PipeOutput`. That is the intended distributed design: `pipelex-api` runs with tracing disabled (thin submitter); the **worker** owns tracing + graph assembly. Forcing it in-process broke graph generation (tracing off in the API → empty `GraphSpec` → graph dropped). **Do not "fix" the graph step to run in-process** — if a `/validate` graph is wanted without a worker, the lever is enabling tracing in the API, a separate deployment decision.

## Test coverage — all three layers in place

The contract — *the validation sweep never dispatches to Temporal* — is guarded at three complementary layers (none redundant):

| Layer | Where it runs | CI-automated | What it adds | Status |
|---|---|---|---|---|
| **Sentinel regression test** (no Temporal) | `tests/integration/pipelex/pipeline/test_bundle_validator.py::TestBundleValidatorIntegration::test_standalone_batch_sweep_scopes_in_process_router` | ✅ | Installs a *raising* hub-default router; sweeps a standalone `PipeBatch`; asserts SUCCESS with the hub default never touched. Deterministic, zero Temporal infra. | exists |
| **Mode-1 pytest** (real Temporal router) | `tests/integration/pipelex/temporal/test_validate_sweep_stays_in_process.py::TestValidateSweepStaysInProcess` | ✅ | Resolves the **real** `TemporalPipeRouter` as the hub default (proving the config→hub-default *wiring* the sentinel bypasses); spies `WorkflowExecutor.execute_workflow` and asserts it's never called. | **new — this change** |
| **Mode-2 scenario** (3 separate processes) | `temporal-e2e-validate` skill, Tier 2c (agent-run) | ✗ | Production-faithful API↔worker boundary: `validate bundle --temporal` over a standalone `PipeBatch` exits 0 **and** the worker stays idle (no `WfPipeRouter` dispatch). Documents the GREEN/RED procedure. | **new — this change** |

The Mode-1 pytest is the cheaper automated catch (fast, deterministic, runs in CI); the Mode-2 scenario is the deployment-faithful demonstration and the only one that also exercises the genuinely cross-process surfaces (LibraryCrate propagation, serialization). Both were verified RED with the `scoped_pipe_router` scope removed and GREEN with it in place.

The repro bundle reuses an existing fixture (no new fixture): `tests/integration/pipelex/temporal/library_crate/temporal_batch.mthds` already declares a standalone `type = "PipeBatch"` pipe (`batch_temporal_describe_topics`) whose direct sweep fans out — the exact shape that 422'd.

## Files in this change

Owned by **this** change (the rest of the diff belongs to PR #974 — see [Stacking](#fix-validate-dry-run-leaked-nested-controller-sub-pipes-to-temporal)):

- `pipelex/pipeline/bundle_validator.py` — the fix (`__init__` keeps `self._pipe_router`; `validate_pipes` wraps the sweep in `scoped_pipe_router`).
- `pipelex/cli/commands/validate/{_validate_core,bundle_cmd,method_cmd,pipe_cmd}.py` — the `--temporal/--no-temporal` flag.
- `tests/integration/pipelex/pipeline/test_bundle_validator.py` — sentinel regression test (+ siblings).
- `tests/integration/pipelex/temporal/test_validate_sweep_stays_in_process.py` — **new** Mode-1 pytest.
- `tests/unit/pipelex/cli/test_validate_temporal_flag.py` — locks the CLI surface (each subcommand exposes `--temporal/--no-temporal`; `--help` short-circuits before boot).
- `.claude/skills/temporal-e2e-validate/references/mode-2-tiers.md` — **new** Tier 2c scenario (+ Contents + Step 7 row).
- `CHANGELOG.md` — entry under `[Unreleased]`.
- `TODOS.md`, `wip/distributed-execution/validate-sweep-temporal-leak-repro.md` — this guide + the repro brief.

## How to verify (local setup)

API on :8081 (`make run`), Temporal server + worker up (from `pipelex-worker`), both on the editable `pipelex` checkout.

```bash
# was failing → now 200 with validated bundle
make bundle-validate BUNDLE=/Users/lchoquel/repos/Pipelex/pipelex-demos/mthds-wip/fashion_moodboard
# regression guard → still 200
make bundle-validate BUNDLE=/Users/lchoquel/repos/Pipelex/pipelex-demos/mthds-wip/joke_judge
```

CLI parity check (no override file needed): `pipelex validate bundle <bundle> --temporal` boots Temporal-enabled yet the sweep stays in-process — exits 0 with no workflow dispatched to the worker. See [`wip/distributed-execution/validate-sweep-temporal-leak-repro.md`](wip/distributed-execution/validate-sweep-temporal-leak-repro.md) for the full GREEN/RED procedure (now implemented as Tier 2c in the `temporal-e2e-validate` skill).
