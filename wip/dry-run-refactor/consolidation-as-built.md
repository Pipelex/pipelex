# Dry-run / validation consolidation — as built

> **Status: shipped.** The in-process consolidation (D-plan **Part A**) landed on `main` in **#956**, with its `pipelex-api` companion. This doc describes **what exists now** — the architecture, the decisions that hold, and where the code lives. It is a current-state reference, not a build log.
>
> - **Still to do** → see the open follow-ups in [`README.md`](./README.md). Nothing here is open.
> - **Design rationale (the *why*, plus Parts B & C)** → [`D-plan.md`](./D-plan.md). Line numbers there are indicative — verify by symbol.

## The model: two operations, not one

"Dry-run" is really two distinct operations, and the consolidation keeps them separate:

- **Execution dry-run** — a single pipe through `PipelexRunner`, in DRY run mode. Raises on failure. This is the normal run primitive with the leaves mocked; it is the north-star ("a run is a run").
- **Validation sweep** — a *batch*, *tolerant* pass over a set of already-loaded pipes that classifies each as `SUCCESS` / `FAILURE` / `SKIPPED` and aggregates the result. This is what `validate --all`, the build/validate CLIs, the builder ops, and `pipelex-api`'s validate/build routes need.

Before the consolidation the sweep lived in a bespoke `dry_run.py` path (plus `dry_run_with_graph.py` and a dead `dry_pipe_router.py`) that bypassed the runner orchestration. Now the sweep is a first-class service — `BundleValidator` — that **composes the same execution seam the runner uses**.

## The shared execution seam

`pipeline_run_setup` was factored into two reusable, side-effect-scoped seams, both in `pipelex/pipeline/execution_seams.py`:

- **`acquire_library(library_id, *, library_dirs, mthds_contents, bundle_uris) -> (library_id, qualified_main_pipe)`** — load-only. Opens + loads a library and returns the domain-qualified main pipe. Owns load-failure teardown: on failure it restores the caller's previous current-library (or clears it) and tears down the partially-opened library. Sync.
- **`prepare_pipe_job(pipe, *, library_id, execution_config, pipe_run_mode, …) -> PipeJob`** — pure. Builds an equivalent `PipeJob` (run mode, mock input, run id, crate) against a pre-opened library. No registration, telemetry, graph-open, or library mutation.

`pipeline_run_setup` is now the thin wrapper composing them (`add_new_pipeline` → `acquire_library` → resolve pipe / tracer / run-mode / registry / otel inside one `try/finally` → `prepare_pipe_job` → emit `PIPELINE_EXECUTE`). Its public signature is unchanged. `BundleValidator` composes the **same** seams without importing the runner wrapper.

A behavior fix landed with the extraction: load/resolve failures now tear down the library. Previously a pre-`try` failure (e.g. an absent pipe code) **leaked** the library; `acquire_library` owns that teardown now, matching the already-hardened `validate_bundle` idiom.

## `BundleValidator` — the validation-sweep service

`pipelex/pipeline/bundle_validator.py`. Two lifecycles (D-plan **D6**):

- **`acquire_and_validate(*, library_dirs, mthds_contents, bundle_uris, library_id="", allow_signatures=False)`** — owns `acquire_library` once + always tears down in `finally`. This is the standalone `validate --all` sweep (sweeps every loaded pipe). Wired to the agent-CLI `validate_all` and builder `validate_all`.
- **`validate_pipes(pipes, *, library_id, allow_signatures=False)`** — the **public inner sweep**. Classifies a caller-supplied pipe list against an **already-open** library and **never tears down**, preserving the loaded-on-success contract that `validate_bundle` and its callers depend on (they read the loaded library afterward via `get_required_pipe`). Wired to `validate_bundle` / `validate_bundles_from_directory`, main-CLI `do_validate_all`, the build CLIs, the builder single-pipe/runner-code ops, and `pipelex-api`'s `/build/runner`.

Internals:

- **Direct in-process primitive.** `__init__` constructs a *local* `PipeRun(PipeRouter(observer=ObserverNoOp()))` — deliberately **not** the hub's `get_pipe_run()`. So a validation sweep runs in-process **regardless of `temporal.is_enabled`** and never dispatches a workflow/activity. (Making DRY *honor* the backend is a separate goal — Part B.)
- **Order (D-plan D7):** `validate_with_libraries` wiring pass → signature pre-pass → per-pipe sweep. The wiring pass runs first so an unresolved **cross-package** sub-pipe in a controller is recorded `SKIPPED` and dropped from the remaining passes instead of aborting the sweep; same-package typos still hard-fail at library load. The signature pre-pass runs over the **full** pipe list (not the post-SKIPPED-drop list) so a `PipeSignature` hidden behind a cross-package wiring gap can't slip past strict validation.
- **Classification catch:** `except (PipelexError, ValidationError, FactoryException)` around both `prepare_pipe_job` and the run. `SKIPPED` is decided by a recursive `_root_cause_is(exc, PipeNotFoundError)` walk over `exc` itself and its `__cause__`/`__context__` chain — necessary because `PipeRun.run` re-raises the original and the router wraps a cross-package `PipeNotFoundError` (itself a `PipelexError`) inside another `PipelexError`. A non-dependency `PipelexError` raised mid-run classifies as a per-pipe `FAILURE`, not a sweep abort.
- **`allowed_to_fail`:** a single aggregate match on the namespaced `pipe.pipe_ref`; the per-pipe step classifies only (no early abort). A sweep with multiple non-allowed failures reports them all. `pipelex.toml`'s `allowed_to_fail_pipes` uses namespaced refs (e.g. `failing_pipelines.infinite_loop_1`).
- **`DryRunStatus` / `DryRunOutput`** live here (canonical home). `DryRunOutput` carries the namespaced `pipe_ref` alongside the bare `pipe_code`.
- **Report registry:** one per sweep, keyed by `SpecialPipelineId.DRY_RUN_UNTITLED`, closed in `finally`. (The DRY LLM leaf emits a synthetic zero-token report, so the registry is genuinely used.)

## `allow_signatures` is a validation gate

Not a runner parameter. It threads through `validate_pipes` / `validate_bundle` and is exposed as a request-body field (`default=False`, strict) on every `pipelex-api` validation route (`/validate`, `/build/runner`, `/build/inputs`, `/build/output`). `SignaturesNotAllowedError` carries `error_domain = ErrorDomain.INPUT`, so a strict signature rejection is a **422** (caller-fixable), not a 500.

## Validate-result identity

Every `validate` surface reports each pipe by its **namespaced `pipe_ref`** (`domain.code`) — agent `validate all`/`bundle`/`pipe`/`pipe --bundle` and all builder validate ops. `build_validated_pipes` (`pipelex/pipeline/validate_bundle.py`) returns `list[ValidatedPipeEntry]` (a `TypedDict` with `pipe_code` + `status`); the `pipe_code` **key name** is preserved for the published JSON contract but its **value** is the qualified ref. The MTHDS skills repo consumes this JSON — its cross-repo update is the one open tail (see [`handoff-skills-validate-namespaced-identity.md`](./handoff-skills-validate-namespaced-identity.md)).

## What was deleted / kept

- **Deleted:** `pipe_run/dry_run.py`, `pipe_run/dry_run_with_graph.py`, `pipe_run/dry_pipe_router.py` (the latter was always dead code), and `tests/unit/pipelex/pipe_run/test_dry_run.py` (coverage ported to `test_bundle_validator.py`).
- **Kept:** `pipe_run/dry_run_pipeline.py` — a still-live "dry-run a whole bundle from MTHDS content → GraphSpec" helper (callers: `pipelex/graph/graph_rendering.py` and `pipelex-api`'s validate route). It already uses the unified DRY-mode `PipelexRunner` path. Not inlined into `graph_rendering.py` (that would break the cross-repo import).
- The two relocated mock helpers (`convert_to_working_memory_format`, `convert_stuff_spec_to_typed_named`) now live as classmethods on `WorkingMemoryFactory`.

## Part C as built — dry-run + validation as ONE in-process Temporal activity (Mode 1)

Shipped on `feature/Dry-run-as-temporal-activity` (+ the `pipelex-api` branch `feature/Update-dry-run-api`). Full phase-by-phase record in the branch's `TODOS.md`; design in [`followup-temporal-validation-activity.md`](./followup-temporal-validation-activity.md).

- **The two-instance fix:** `pipelex.hub.scoped_event_log(event_log)` + `get_event_log_override()` — both the tracer write side (`pipeline_run_setup.py`) and the assembly read side (`tracing_assembly.py`) prefer the scoped instance over `make_event_log`, so a run traces into ONE shared `InMemoryEventLog`. A set override implies tracing-enabled; the scope owner keeps the instance's lifecycle.
- **The in-process graph dry-run:** `dry_run_pipe_in_process(pipe, *, library_id)` in `pipe_run/dry_run_pipeline.py` — `prepare_pipe_job` (DRY + mock_inputs + generate_graph) + a local `PipeRun` under `scoped_event_log` + `scoped_pipe_router` + the new `hub.scoped_content_generator` (inference leaves resolve an inline `ContentGeneratorDry` instead of `ContentGeneratorInWorkflow`; `get_content_generator()` prefers the override). `BundleValidator.validate_pipes` also carries the content-generator scope, so the sweep stays in-process post-Part-B everywhere.
- **The activity:** `temporal/tprl_pipe/act_dry_validate.py` — composes `validate_bundle` (the SAME function the direct route calls, so both backends share the categorized `ValidateBundleError` 422 contract) + `dry_run_pipe_in_process` against the same once-loaded library; graph is best-effort behind a narrow expected-failure catch (`DryRunError`/`PipeRunError`/`PipeRouterError`/`ValidationError`/`FactoryException` → `graph_spec=None`; everything else propagates). Dispatched via the one-step wrapper `wf_dry_validate.py::WfDryValidate` (explicit activity timeout + non-retryable validation error types) through the submitter helper `dry_validate_dispatch.py::dispatch_dry_validate` (workflow-tier `maximum_attempts=1` — a deterministic validation failure must not re-run). Registered in `temporal/tasks.py` (`PackName.PIPE`).
- **The API route** (`pipelex-api/api/routes/pipelex/validate.py`): Temporal-enabled `/validate` dispatches FIRST (one round-trip, identical 422 via the recovered `ErrorReport`), then re-parses blueprints and builds `pipe_structures` from a load-only `acquire_library`. Direct mode unchanged.
- **Verification:** Mode-1 isolation tests (`tests/integration/pipelex/temporal/test_dry_validate_activity_in_memory.py` — zero nested dispatch pinned on the Temporal history) · Tier 2d in the `temporal-e2e-validate` skill (activity + API arms, GREEN + RED-proven on a real 3-process stack) · `pipelex-api/tests/unit/test_validate_temporal_dispatch.py` (both backends).
- **Deferred:** Phase G0 standalone activity (`temporalio` bump) · retiring the old worker-workflow graph path for `/validate` · moving `pipe_structures` into the activity result (drops the API-side load-only acquisition).

## Where the code lives

- `pipelex/pipeline/execution_seams.py` — `acquire_library`, `prepare_pipe_job`.
- `pipelex/pipeline/pipeline_run_setup.py` — the thin runner-setup wrapper over the seams.
- `pipelex/pipeline/bundle_validator.py` — `BundleValidator` (both lifecycles), `DryRunStatus`, `DryRunOutput`.
- `pipelex/pipeline/validate_bundle.py` — `validate_bundle` / `validate_bundles_from_directory` (delegate the sweep to `BundleValidator.validate_pipes`; keep only library lifecycle + error presentation), `build_validated_pipes`, `ValidatedPipeEntry`.
- `pipelex/core/memory/working_memory_factory.py` — the two relocated mock helpers.
- Tests: `tests/unit/pipelex/pipeline/test_bundle_validator.py`, `tests/integration/pipelex/pipeline/{test_bundle_validator,test_execution_seams,test_acquire_and_validate,test_pipeline_run_setup_characterization}.py`.
- `pipelex-api`: `api/routes/pipelex/build/runner.py` (+ `validate.py`, `build/inputs.py`, `build/output.py` for the `allow_signatures` flag).
