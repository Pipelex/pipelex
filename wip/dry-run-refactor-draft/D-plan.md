# Dry-Run Refactor — Plan (FINALIZED)

> **Status: design finalized 2026-06-01.** The open questions from the re-grounded base are resolved (decisions **D1–D3** below). This plan supersedes the earlier "awaiting clarified requirements" draft. The background docs ([`A-taxonomy.md`](./A-taxonomy.md), [`B-load-profile.md`](./B-load-profile.md), [`C-synthesis.md`](./C-synthesis.md), [`E-parity-gate.md`](./E-parity-gate.md)) remain accurate and are referenced where relevant.

## 1. Context

Pipelex executes MTHDS pipelines — graphs of pipes (LLM calls, controllers like sequence/parallel/batch/condition, operators, and `PipeSignature` contracts). DRY mode swaps real LLM/IO calls for mock outputs so a pipeline can be validated end-to-end without spending money or making network calls. The hosted deployment runs LIVE pipelines on Temporal (workflows on remote workers); DRY is meant to stay cheap and in-process.

Today DRY mode has accumulated parallel code paths that do not go through the same orchestration as LIVE, plus a confirmed dead `DryPipeRouter`. This plan consolidates them onto a single execution primitive.

## 2. North-star principle (user-stated)

> "A run is a run, whether it's dry or live or else, it's the SAME THING. The delivery, the preparation, should go through the SAME thing."
>
> "Everything should go through the PipelexRunner. Runner protocol. JUST FUCKIN DROP those dry-run functions."
>
> "The CLI should ONLY CALL THE PIPELEXRUNNER with the right configuration. There SHOULDN'T BE A dry-run CLI; it should be the RUN cli with a dry mode."

One entry point for *running a pipe* (`PipelexRunner`), `pipe_run_mode=DRY` as the only switch, no bespoke dry-run *execution* functions, no router-level mode dispatch.

## 3. The reframe that drives the design: two operations, not one

The thing the codebase calls "dry-run" is in fact **two distinct operations** wearing one name. Conflating them is what made the north-star feel slippery. Separating them is what makes the consolidation clean.

**A — Execution-dry-run (already through the runner).** `PipelexRunner.execute_pipeline(pipe_run_mode=DRY)` loads the library, builds a `PipeJob`, runs it through `PipeRun → PipeRouter → pipe.run_pipe()` (which dispatches DRY at the pipe level via `PipeAbstract._run_pipe_traced`), optionally delivers/graphs, **raises `PipelineExecutionError` on the first failure**, and tears the library down in `finally`. Single pipe, loads-from-scratch, strict. `pipe_run/dry_run_pipeline.py` (graph path) already does exactly this. **This is the north-star and it already exists.**

**B — Validation-sweep (the bespoke `dry_run.py` path).** `dry_run_pipes(pipes=[...])` takes **already-loaded** `PipeAbstract` objects, shares one library across all of them, and for each pipe mocks inputs + runs DRY **tolerantly**: it collects `SUCCESS / FAILURE / SKIPPED` per pipe, honors `allowed_to_fail_pipes`, skips cross-package unresolved deps (`PipeNotFoundError → SKIPPED`), and does a **single aggregated** signature pre-check across the whole batch *before* running anything. Consumed by `validate --all`, `validate_bundle`, `builder/operations/validate_ops.py`, and the agent CLI. **This is a quality gate, not a run.**

The honest conclusion: a validation sweep is not a run — it is a batch *policy* that *uses* runs. So "drop the dry-run functions and route everything through the runner" is exactly right for the *execution primitive* (A), while the *batch-validation semantics* (B) need a clean, explicit home that **composes** the runner rather than forking it.

## 4. Finalized design

### Decisions

- **D1 — Architecture.** A first-class `BundleValidator` domain service owns the validation sweep (signature pre-pass, per-pipe loop, tolerant aggregation) and composes `PipelexRunner`. The runner stays a pure single-pipe execution primitive. (Chosen over "runner absorbs a batch method," which would push `SKIPPED` / `allowed_to_fail` / signature-precheck — all irrelevant to LIVE — into the runner and make it a god-object.)
- **D2 — Library lifecycle.** The runner exposes a `borrowed_library` async context manager so a caller can open + load a library once and run many pipes against it without per-pipe reload/teardown. Inside the scope, `execute_pipeline` reuses the open library and skips teardown; the context manager owns teardown on exit. (Chosen over a bare `keep_library_loaded` flag for a cleaner ownership contract, and over reload-per-pipe which would cost seconds-to-minutes of pure load churn on `validate --all`.)
- **D3 — Validation model.** The sweep stays **tolerant**: per-pipe `SUCCESS / FAILURE / SKIPPED`, with `SKIPPED` preserved for cross-package unresolved deps and `allowed_to_fail_pipes` kept but **fixed to namespaced `domain.pipe_code` refs** (closing the live bare-code multi-domain-collision `# TODO`). One validation telemetry event, not one per pipe.

### 4.1 `PipelexRunner` — the single execution primitive

`execute_pipeline(pipe_code, pipe_run_mode, ...)` remains the only way to *run a pipe*. DRY or LIVE; raises `PipelineExecutionError` on failure (already true today). Two additions:

- **`borrowed_library` context manager** (D2). Contract:
  - On enter: open a library, load `library_dirs` / `mthds_contents` / a bundle into it, set it current, yield a handle carrying the `library_id`.
  - Inside: `execute_pipeline` resolves the pipe from the already-open library by `pipe_code`, builds the `PipeJob`, runs it — **no reload, no teardown**.
  - On exit: tear the library down (and restore the previous current-library), with the same safety ordering `validate_bundle` uses today (restore outer current-library before teardown so a teardown raise can't strand the outer scope).
  - Implementation touch points: `pipeline_run_setup` currently calls `library_manager.open_library(...)` and `execute_pipeline`'s `finally` calls `library_manager.teardown(...)`. Both must become conditional on an "externally-owned library" signal threaded from the borrowed scope. The self-contained (non-borrowed) path is unchanged — default behavior stays "open, run, teardown."
- **Validation-context suppression** (telemetry side of D3). When invoked inside a borrowed-library validation scope, `execute_pipeline` must **not** register a new pipeline in the pipeline manager nor emit per-run `PIPELINE_EXECUTE` / `PIPELINE_COMPLETE` events — a validation of N pipes is one logical event, emitted once by `BundleValidator`, not N pipeline runs. Carry this as a flag on the borrowed scope.

The runner gains **no** knowledge of signatures, `allowed_to_fail`, or `SKIPPED`. Those are validation concerns and live only in `BundleValidator`.

### 4.2 `BundleValidator` — the batch validation service (D1)

A first-class service (proposed home: `pipelex/pipeline/bundle_validator.py`, next to the existing `validate_bundle.py`, reusing `_translate_to_validate_bundle_error` as the error-translation boundary). All validation entry points route through it — both batch and single-pipe. Responsibilities, in order:

1. **Open a borrowed library** via `runner.borrowed_library(...)` (loads dirs / contents / bundle once).
2. **Select pipes to dry-run.** Whole bundle, or the `--pipe` slice via the existing `_pipes_to_dry_run` selector (keeps its `PipeNotFoundError` typo-guard so a misspelled `--pipe` fails loudly).
3. **Signature pre-pass** (D-plan §4.3). Walk the selected pipes with `collect_signature_refs` / `collect_signature_paths`; if `allow_signatures=False` and any signature is reached, raise the single aggregated `SignaturesNotAllowedError` (longest dep-chain per signature, as today). In strict mode, exclude signature pipes from the sweep itself (validating a signature directly would always trip the check); in lenient mode keep them (they dry-run trivially by minting a mock output). This is the same signature-aware filtering `validate --all` does today, now owned by the service.
4. **`validate_with_libraries()` pass.** Per selected pipe — this is a static library-wiring check that is *more* than a dry run and the runner's DRY path does not perform it (the runner only triggers `validate_before_run` inside `_run_pipe_traced`). Keeping it here preserves coverage. (It removes today's redundancy where both `validate --all` and `dry_run_pipe` call it.)
5. **Dry-run sweep.** For each selected pipe: `await runner.execute_pipeline(pipe_code=pipe.code, pipe_run_mode=DRY)` inside the borrowed scope, classifying the outcome:
   - success → `SUCCESS`
   - failure rooted in `PipeNotFoundError` (cross-package unresolved dep) → `SKIPPED`
   - any other `PipelineExecutionError` → `FAILURE`, unless the pipe's namespaced ref is in `allowed_to_fail_pipes`
6. **Aggregate + report.** Build the per-pipe status map, emit one validation telemetry event (`PIPE_DRY_RUN` with `NB_PIPES`), raise a single aggregated error if there are unexpected failures, else return the result.

Mock inputs are **not** built by the validator — it sets `is_mock_inputs=True` on the execution config and lets the runner generate them (the runner already does this in `pipeline_run_setup`; see §4.5).

### 4.3 `allow_signatures` is a validation gate, not a run parameter

Key finding that simplifies the surface: in DRY, a `PipeSignature` **always** mints its mock output (`PipeSignature._dry_run_pipe`), regardless of `allow_signatures`. The flag changes exactly one thing — whether the **batch pre-check raises**. The per-pipe *run* is identical either way. Therefore `allow_signatures` does **not** ride on `PipeRunParams` or `execute_pipeline`; it is a `BundleValidator` parameter that controls only the pre-pass (§4.2 step 3). This corrects the earlier assumption (old §6) that `allow_signatures` had to thread through the runner alongside `run_mode`.

`ValidateBundleError.signature_check_error` + `handle_signatures_not_allowed_error` (honoring `--traceback`) are preserved: the pre-pass raises `SignaturesNotAllowedError`, the translation boundary wraps it, the CLI renders it.

### 4.4 Tolerant result model (D3)

`DryRunStatus` (`SUCCESS / FAILURE / SKIPPED`) and `DryRunOutput` survive, but **relocate** out of `pipe_run/dry_run.py` into the `BundleValidator` module — they are validation-report types, not execution types. The CLI / builder JSON consumers (`builder/operations/validate_ops.py`, the agent CLI) keep reading the per-pipe status map.

`allowed_to_fail_pipes` stays in `DryRunConfig` + `pipelex.toml`, **migrated to namespaced refs** (`domain.pipe_code`). The current bare entries (`infinite_loop_1`, `pipe_builder`) must be re-expressed with their domains, and the matching in `BundleValidator` keys off `pipe.pipe_ref`, not `pipe.code`. This is a breaking config change (allowed — no backward-compat requirement) and closes the bare-code collision risk.

### 4.5 Mock inputs flow through the runner

The runner already generates mock inputs when `execution_config.is_mock_inputs` is true (`pipeline_run_setup`: `convert_to_working_memory_format` → `WorkingMemoryFactory.make_mock_inputs`, only for inputs the caller didn't provide). `BundleValidator` therefore stops building working memory itself and simply sets `is_mock_inputs=True`. The helper `convert_to_working_memory_format` **relocates** to `WorkingMemoryFactory` (or a `mock_inputs.py` beside it), since the runner — not the deleted `dry_run.py` — is its real owner. (Minor polish: `with_graph_config_overrides` already carries the `mock_inputs` override but is graph-named; consider a clearer `with_overrides`.)

### 4.6 Graph path

- `pipe_run/dry_run_pipeline.py` already routes through the runner (`execute_pipeline(generate_graph=True, mock_inputs=True, DRY)`) and is the sole path used by `graph/graph_rendering.py`. **Keep** it as a thin helper (or inline into `graph_rendering.py`); it is already north-star-compliant.
- `pipe_run/dry_run_with_graph.py` (`dry_run_pipe_with_graph`, single pre-loaded pipe + graph, direct `pipe.run_pipe()`) has **no consumers** within `pipelex/`. **Delete** it (verify `pipelex-api` and the test tree first).

### 4.7 `convert_stuff_spec_to_typed_named` relocation (unblocks the deletion)

`pipe_signature/pipe_signature.py` imports `convert_stuff_spec_to_typed_named` from `dry_run.py` — a hard dependency from the signature runtime into the module we want to delete. Relocate it alongside `convert_to_working_memory_format` (§4.5) into `WorkingMemoryFactory`, and rewire `pipe_signature.py` + `pipeline_run_setup.py`. This is **step 0** of the migration so `dry_run.py` becomes a deletable leaf.

## 5. What changes — delete / relocate / keep

**Delete**

- `pipe_run/dry_pipe_router.py` (`DryPipeRouter`) — confirmed dead code; mode is a pipe-level concern, not a router-level one.
- `pipe_run/dry_run_with_graph.py` — no consumers (§4.6).
- `pipe_run/dry_run.py`'s execution functions `dry_run_pipe` / `dry_run_pipes` — their semantics move into `BundleValidator`. Once the helpers and types relocate, `dry_run.py` is fully removed.

**Relocate**

- `convert_to_working_memory_format`, `convert_stuff_spec_to_typed_named` → `WorkingMemoryFactory` (runner + signature runtime are the real owners).
- `DryRunStatus`, `DryRunOutput` → `BundleValidator` module (validation-report types).

**Keep**

- `PipeRouterProtocol`, `PipeRunProtocol`, the Router/Run two-layer split (mirrors the Temporal parent/child workflow shape).
- Pipe-level `_dry_run_pipe` / `_dry_run_operator_pipe` / `_dry_run_controller_pipe` — the legitimate per-pipe-type override boundary; the only place `run_mode` should matter. `PipeSignature._dry_run_pipe` is a clean member of this set.
- `pipe_run/dry_run_pipeline.py` — already runner-based (§4.6).

## 6. Migration sequencing (phased)

Ordered to keep every intermediate state compiling and green, given `dry_run.py` is imported by `pipe_signature.py`.

**Phase 0 — Unblock the leaf.** Relocate `convert_to_working_memory_format` + `convert_stuff_spec_to_typed_named` to `WorkingMemoryFactory`; rewire `pipe_signature.py` and `pipeline_run_setup.py`. No behavior change. Run the suite.

**Phase 1 — Runner gains borrowed-library + validation-context suppression** (§4.1 / D2). Add the `borrowed_library` context manager and the externally-owned-library + telemetry-suppression signals; make `pipeline_run_setup`'s open and `execute_pipeline`'s teardown conditional. Self-contained path unchanged. Unit-test the borrowed scope (open-once / run-many / teardown-once; teardown-raise safety).

> **Checkpoint A (after Phase 1).** The execution primitive is ready and the signature runtime no longer depends on `dry_run.py`, but nothing consumes the new capability yet — clean handoff point. Update this doc with the final `borrowed_library` signature, the name chosen for the suppression flag, and any `pipeline_run_setup` shape changes.

**Phase 2 — Build `BundleValidator`** (§4.2, D1/D3). Implement the service (signature pre-pass, `validate_with_libraries` pass, runner loop with `SUCCESS/FAILURE/SKIPPED` classification, namespaced `allowed_to_fail`, single telemetry event) against the still-present `dry_run.py`, behind no callers yet. Relocate `DryRunStatus` / `DryRunOutput`. Port the existing `tests/unit/pipelex/pipe_run/test_dry_run.py` coverage onto the service.

**Phase 3 — Migrate the callers.** Point `validate_bundle` / `validate_bundles_from_directory`, both CLI `_validate_core.py` files, `builder/operations/validate_ops.py`, and `builder/operations/runner_code_ops.py` at `BundleValidator`. Migrate `allowed_to_fail_pipes` entries in `pipelex.toml` to namespaced refs. Verify the single-pipe `validate <pipe>` / `--pipe` slice and the friendly `SignaturesNotAllowedError` rendering still fire.

> **Checkpoint B (after Phase 3).** All validation traffic now goes through `BundleValidator → runner`; `dry_run.py`'s execution functions are unreferenced. Re-run the signature e2e + integration suites (`tests/e2e/test_signature_validation_mthds.py`, `tests/integration/pipelex/pipe_signature/*`) and the full `make agent-test`. This is the natural place to split into a fresh session if context has grown.

**Phase 4 — Delete dead code.** Remove `dry_pipe_router.py`, `dry_run_with_graph.py`, and the now-unreferenced `dry_run.py`. Settle `dry_run_pipeline.py` (keep thin or inline into `graph_rendering.py`). Final `make agent-check` + `make agent-test`.

## 7. Out of scope (follow-ups)

- API endpoint unification (`/validate` + `/execute` → `/run` in `pipelex-api`).
- CLI artifact dedup — `_run_core.py` now gates artifact writing via `save_main_stuff` / `save_working_memory` against an `output_path`, in two copies (main + agent CLI). Re-scope before touching.
- Renaming `WfPipeRouter` / `WfPipeRun` for clarity ([`A-taxonomy.md` §6 smell #1](./A-taxonomy.md#section-6-smells-and-inconsistencies)).

## 8. Invariants & risks

- **Parity gate holds** ([`E-parity-gate.md`](./E-parity-gate.md)): the API process and the Temporal worker register identical class registries (user concept classes are loaded per-request from the MTHDS payload, not at boot), so routing DRY to a local in-process run is safe even where the hub default is Temporal. Re-opens only if one side gains a boot-time library preload the other lacks.
- **Load profile is safe in-process** ([`B-load-profile.md`](./B-load-profile.md)): a dry run is CPU-cheap (Pydantic + Jinja2), no network, no disk — fine to loop in the validation sweep.
- **Risk — telemetry suppression.** If Phase 1's suppression flag is missed on any borrowed-scope path, `validate --all` would emit a flood of per-pipe pipeline-run events. Covered by an explicit test asserting one validation event per sweep.
- **Risk — `SKIPPED` classification.** Routing through the runner turns `PipeNotFoundError` into `PipelineExecutionError`; `BundleValidator` must inspect the cause to re-classify cross-package unresolved deps as `SKIPPED`, or partial-bundle validation regresses to hard failure. Covered by a cross-package partial-validation test.
