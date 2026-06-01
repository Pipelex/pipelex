# Dry-Run Refactor — Plan (clean base, re-grounded on current code)

> **Status: clean base, awaiting clarified requirements.** This is the original 8-point plan re-grounded on the live branch (`feature/Validate-with-signatures-4-fix-dry-run`), which now sits on top of the signature-validation feature. The north-star principle is unchanged; the design has not yet been finalized because (a) signature-validation moved the ground under it and (b) the clarified/completed requirements are still to be folded in — see [§9 Requirements to fold in](#9-requirements-to-fold-in-pending). Treat everything below §6 as provisional.

## 1. Context

Pipelex executes MTHDS pipelines — graphs of pipes (LLM calls, controllers like sequence/parallel/batch/condition, operators, and now `PipeSignature` contracts). DRY mode swaps real LLM/IO calls for mock outputs so a pipeline can be validated end-to-end without spending money or making network calls. The hosted deployment runs LIVE pipelines on Temporal (workflows on remote workers); DRY is meant to stay cheap and in-process.

Today DRY mode has accumulated parallel code paths that do not go through the same orchestration as LIVE. This plan consolidates them.

## 2. North-star principle (user-stated, unchanged)

> "A run is a run, whether it's dry or live or else, it's the SAME THING. The delivery, the preparation, should go through the SAME thing."
>
> "Everything should go through the PipelexRunner. Runner protocol. JUST FUCKIN DROP those dry-run functions."
>
> "The CLI should ONLY CALL THE PIPELEXRUNNER with the right configuration. There SHOULDN'T BE A dry-run CLI; it should be the RUN cli with a dry mode."

The goal is: one entry point (`PipelexRunner`), `pipe_run_mode=DRY` as the only switch, no bespoke dry-run functions, no router-level mode dispatch.

## 3. Current reality (verified on the live branch)

What's actually in the tree today — this is the starting point, not the abandoned `fix/dry-run` state described in [`archive/`](./archive/):

- **The four parallel modules all still exist:** `pipelex/pipe_run/dry_run.py`, `dry_run_pipeline.py`, `dry_run_with_graph.py`, `dry_pipe_router.py`.
- **`DryPipeRouter` is confirmed dead code** — never instantiated outside its own definition. Mode dispatch lives in `PipeAbstract._run_pipe_traced` (`match pipe_run_params.run_mode`), so the regular `PipeRouter` already routes DRY correctly. This finding from the original audit still holds.
- **`validate_bundle` already dry-runs on load.** The three `# TODO: wip - restore or refactor dry run` are gone; every load path calls `dry_run_pipes(...)`. The "silent regression" that motivated the original plan is **closed** — but it was closed through the old `dry_run.py`, not the consolidation.
- **`dry_run.py` is now load-bearing for signature-validation** (see [`A-taxonomy.md` §7](./A-taxonomy.md#section-7-signature-validation-deltas-added-since-this-doc)):
  - `dry_run_pipe` / `dry_run_pipes` thread `allow_signatures` and host the batch-level **strict signature pre-check** (`collect_signature_refs` / `collect_signature_paths` → single aggregated `SignaturesNotAllowedError`).
  - `convert_stuff_spec_to_typed_named` is exported from `dry_run.py` and **imported by `pipelex/pipe_signature/pipe_signature.py`** — a hard dependency from the signature runtime into the module the plan wants to delete.
  - `convert_to_working_memory_format` is still in `dry_run.py`, imported by `pipeline_run_setup.py` and `dry_run_with_graph.py`.
- **`allowed_to_fail_pipes`** is still present in `configs.py` and `pipelex.toml`, still consumed by `dry_run_pipes` (with a `# TODO` noting the bare-code multi-domain collision risk).
- **`validate_bundle` carries `allow_signatures` + `dry_run_pipe_codes`** (the `--pipe` single-slice selector via `_pipes_to_dry_run`), and `ValidateBundleError` carries `signature_check_error`.
- **`_run_core.py` has been reworked** (and split into main-CLI + agent-CLI copies): artifact writing is now gated by `save_main_stuff` / `save_working_memory` flags against an `output_path`, not the hand-rolled block the original plan described.

## 4. Current dry-run call graph (who to migrate)

The callsites the consolidation must move off the bespoke functions and onto `PipelexRunner`, by module (line numbers omitted on purpose — they drift):

- `pipelex/pipeline/validate_bundle.py` — calls `dry_run_pipes(...)` on every load path; threads `allow_signatures` + `dry_run_pipe_codes`.
- `pipelex/cli/commands/validate/_validate_core.py` — `dry_run_pipe` (single) + `dry_run_pipes` (batch).
- `pipelex/cli/agent_cli/commands/validate/_validate_core.py` — `dry_run_pipe` + `dry_run_pipes`, plus `--pipe` single-slice.
- `pipelex/builder/operations/validate_ops.py` — `dry_run_pipe` + `dry_run_pipes`.
- `pipelex/builder/operations/runner_code_ops.py` — `dry_run_pipes`.
- `pipelex/graph/graph_rendering.py` — the only consumer of `dry_run_pipeline` (graph-on-dry-run).
- `pipelex/pipeline/pipeline_run_setup.py` + `pipelex/pipe_run/dry_run_with_graph.py` — consume `convert_to_working_memory_format`.
- `pipelex/pipe_signature/pipe_signature.py` — consumes `convert_stuff_spec_to_typed_named` (NOT a dry-run caller, but a hard importer of `dry_run.py`).

Tests that import these modules and will move with them: `tests/unit/pipelex/pipe_run/test_dry_run.py`, `tests/integration/pipelex/pipe_signature/*`, `tests/e2e/test_signature_validation_mthds.py`, `tests/integration/pipelex/pipes/controller/pipe_sequence/test_pipe_sequence_list_output_bug.py`, `tests/integration/pipelex/temporal/library_crate/conftest.py`.

## 5. Decided design (carried over — re-validate before committing)

These decisions from the original plan still look right, but must be re-checked against the signature surface:

1. **Delete the bespoke dry-run functions; dry-runs return `PipeOutput` and raise `PipelineExecutionError` on failure** — symmetric with live runs. **Open against current code:** `DryRunStatus` / `DryRunOutput` are now woven into the validator JSON output and the `SKIPPED` path (cross-package unresolved deps); and `convert_stuff_spec_to_typed_named` must survive (move, not delete) because `pipe_signature.py` needs it. So "drop the types" is no longer a clean delete — it's a relocate-and-rewire.

2. **`PipelexRunner` enforces routing.** If `pipe_run_mode == DRY`, use a local `PipeRun(PipeRouter())` regardless of hub default (Temporal stays for LIVE). Per-request explicit `pipe_run` override beats both. Backed by the load profile (`B`) and the parity gate (`E`), both still valid.

3. **Delivery is mode-agnostic.** `PipeRun.run()` does not gate on mode; it honors whatever `DeliveryAssignment` the caller passes. "No S3/webhook for DRY in hosted API" is an endpoint-level policy (caller picks the target), not a runtime branch.

4. **Validators migrate to `PipelexRunner`.** Each becomes a loop over `runner.execute_pipeline(pipe_code=p, pipe_run_mode=DRY, mock_inputs=True, ...)`, aggregating failures. **Now also has to thread `allow_signatures` and the `--pipe` slice selection** (see §6).

5. **`convert_to_working_memory_format` + mock-input generation move into the runner / `WorkingMemoryFactory`** so validators stop building their own working memory.

6. **`graph_rendering.py` calls the runner directly** with `generate_graph=True`, reading `response.pipe_output.graph_spec`.

7. **`keep_library_loaded` ownership flag.** The abandoned attempt discovered that `PipelexRunner.execute_pipeline` tears down its library in `finally`, which breaks the validator pattern of "pre-load once, iterate N pipes through the runner." The opt-in `keep_library_loaded` flag (caller owns the library) was its fix. This problem is **still latent** in the current runner and any migration will rediscover it — keep the fix on the menu. See [`archive/fix-dry-run-implementation.md`](./archive/fix-dry-run-implementation.md) "Design addition not in the plan".

## 6. NEW constraints imposed by signature-validation

This is the part the original plan never saw. Any consolidation must satisfy all of these or it regresses signature-validation:

- **`allow_signatures` rides alongside `run_mode`.** Routing dry-run through `PipelexRunner` means `execute_pipeline` (or `PipeRunParams`) must carry strict-vs-lenient. Decide where it lives: a `PipelexRunner` parameter, a field on `PipeRunParams`, or part of an execution-config. Both CLIs are **strict by default**; lenient is opt-in via `--allow-signatures`.

- **The batch-level strict pre-check needs a home.** Today `dry_run_pipes` walks the *whole batch* and raises a **single** `SignaturesNotAllowedError` aggregating every offending pipe + dep-chain, *before* running any pipe. `PipelexRunner.execute_pipeline` is single-pipe per call. Options to resolve: (a) keep a thin batch orchestrator above the runner that does the pre-check then loops; (b) push the pre-check into a validate-only pre-pass; (c) accept per-pipe errors and lose the single-aggregated-error UX (probably unacceptable — it's a deliberate property). This is the central design question.

- **`dry_run_pipe_codes` / `--pipe` single-slice must survive.** "Load the whole bundle so deps resolve, but only dry-run the selected pipe" is a real feature with a typo-guard (`PipeNotFoundError` on an unknown `--pipe`). The runner-based design has to express "load these, run only that."

- **`PipeSignature` minting must keep working.** `PipeSignature._dry_run_pipe` mints its declared output via `WorkingMemoryFactory.make_mock_content`; `convert_stuff_spec_to_typed_named` is part of that path and lives in `dry_run.py`. Relocate it somewhere `pipe_signature.py` can import without a cycle (candidate: `WorkingMemoryFactory`, alongside `convert_input_specs_to_typed` from the abandoned attempt).

- **`ValidateBundleError.signature_check_error` + friendly CLI rendering** (`handle_signatures_not_allowed_error`, honoring `--traceback`) must still fire after migration.

## 7. Out of scope (carried over)

- API endpoint unification (`/validate` + `/execute` → `/run` in `pipelex-api`) — follow-up.
- CLI artifact dedup — note the target moved; `_run_core.py` now uses `save_main_stuff` / `save_working_memory` flags, and there are two copies (main + agent CLI). Re-scope before touching.
- Renaming `WfPipeRouter` / `WfPipeRun` for clarity (`A-taxonomy.md` §6 smell #1).

## 8. Kept as-is (carried over)

- `PipeRouterProtocol`, `PipeRunProtocol`, the Router/Run two-layer split (mirrors the Temporal parent/child workflow shape).
- Pipe-level `_dry_run_pipe` / `_dry_run_operator_pipe` / `_dry_run_controller_pipe` — the legitimate per-pipe-type override boundary; the only place `run_mode` should matter. `PipeSignature._dry_run_pipe` is a clean addition to this set.

## 9. Requirements to fold in (PENDING)

> The user has clarified/completed needs that have not yet been written here. When they arrive, fold them into §5–§6 and resolve the central design question in §6 (where the batch strict pre-check lives). Until then, this plan is a re-grounded base, not a commitment.

Likely decision points the requirements will need to settle:

- Where `allow_signatures` lives on the runner surface, and whether DRY/LIVE is the only mode or whether "validate-only" becomes a distinct mode.
- Whether the batch strict pre-check stays as a pre-pass or the per-pipe-aggregation UX is redesigned.
- The fate of `DryRunStatus` / `DryRunOutput` / `SKIPPED` / `allowed_to_fail_pipes` under the "dry-run failure is a real failure" model — especially the cross-package `SKIPPED` path, which exists for a reason (unresolved cross-package deps during partial validation).
- Sequencing: which deletion/migration order minimizes broken intermediate states, given `dry_run.py` is imported by `pipe_signature.py`.
