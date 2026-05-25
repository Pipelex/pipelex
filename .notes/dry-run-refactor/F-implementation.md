# F. Implementation — What Actually Shipped

Maps the plan in `D-plan-for-codex.md` to the actual diff (commit `7a01854f` on `fix/dry-run`). Calls out divergences and one design addition (`keep_library_loaded`) that wasn't in the plan.

## File-by-file map

### Deleted

| File | Why |
|---|---|
| `pipelex/pipe_run/dry_run.py` | `dry_run_pipe`, `dry_run_pipes`, `DryRunStatus`, `DryRunOutput`, `DryRunError`, `convert_to_working_memory_format`. All replaced by `PipelexRunner` + new helpers in `validate_bundle.py`. `convert_to_working_memory_format` moved to `WorkingMemoryFactory.convert_input_specs_to_typed`. |
| `pipelex/pipe_run/dry_run_pipeline.py` | Single consumer was `graph_rendering.py:_dry_run_bundle`; inlined as a direct `PipelexRunner(pipe_run_mode=DRY, generate_graph=True)` call. |
| `pipelex/pipe_run/dry_run_with_graph.py` | Same — its caller is gone, its mock-input helper moved. |
| `pipelex/pipe_run/dry_pipe_router.py` | Confirmed dead code (`A-taxonomy.md` §4). Mode dispatch is a pipe-level concern (`PipeAbstract._run_pipe_traced` line 514), not a router-level one. No production instantiation ever existed. |
| `tests/unit/pipelex/pipe_run/test_dry_run.py` | Targeted the deleted helpers; equivalent coverage now sits in the new regression test and the migrated `test_pipe_sequence_list_output_bug.py`. |

### Config removed

| Symbol | Location | Why |
|---|---|---|
| `DryRunConfig.allowed_to_fail_pipes` | `pipelex/system/configuration/configs.py:69` | Its only consumer was `dry_run.py`, which is gone. Aggregating "allowed failures" runs counter to the new model where dry-run failures are real failures and raise `PipeRunError`. |
| Same key | `pipelex/pipelex.toml:364-367` | Removed `infinite_loop_1` / `pipe_builder` entries. |

### `pipelex/pipeline/runner.py` — DRY-routes-local + `keep_library_loaded`

Two additions:

1. **`_resolve_pipe_run()`** (new method). Decides which `PipeRun` to use per call:
   - Explicit per-request `self._pipe_run` wins
   - DRY mode → local `PipeRun(PipeRouter(observer=ObserverNoOp()))`, even when hub default is Temporal
   - LIVE mode → hub default (Temporal or local depending on config)
2. **`keep_library_loaded: bool = False`** constructor flag, threaded into `pipeline_run_setup` and gating the `finally`-block teardown. Default `False` preserves existing behavior (runner owns the library). Validators opt in (`True`) so they can pre-load once and iterate per-pipe through the runner without the runner destroying their library between iterations.

### `pipelex/pipeline/pipeline_run_setup.py`

- Removed `from pipelex.pipe_run.dry_run import convert_to_working_memory_format`.
- Mock-input branch now calls `WorkingMemoryFactory.convert_input_specs_to_typed(...)` instead.
- Added `keep_library_loaded: bool = False` parameter; gates the error-path library teardown.

### `pipelex/core/memory/working_memory_factory.py`

- Imported `InputStuffSpecs` and `get_class_registry`.
- Added classmethod `convert_input_specs_to_typed(needed_inputs_spec)` — bridge from `InputStuffSpecs` to `list[TypedNamedStuffSpec]`. Same body as the deleted `convert_to_working_memory_format`, just colocated with the factory that consumes its output (`make_mock_inputs`). TextContent fallback preserved for missing/non-StuffContent structure classes and ValidationError cases.

### `pipelex/pipeline/validate_bundle.py`

Two new helpers + `validate_bundle()` restored to dry-on-load.

- `dry_run_loaded_pipes(pipe_refs, library_id) -> dict[str, str]`. Runs each pipe in DRY mode via `PipelexRunner(library_id=..., keep_library_loaded=True, pipe_run_mode=DRY, execution_config=...with mock_inputs=True...)`. Returns `pipe_ref -> error message` for failures only. Successful pipes are absent from the dict.
- `dry_run_loaded_pipes_or_raise(pipe_refs, library_id)`. Wraps above; if any failures, raises an aggregated `PipeRunError` (the first failed ref is used to satisfy the constructor; the message lists every failure).
- `validate_bundle()` now invokes `dry_run_loaded_pipes(...)` after loading. If any pipe fails, raises `ValidateBundleError(message=..., dry_run_error_message=...)`. This restores the three `# TODO: wip - restore or refactor dry run` lines.
- `ValidateBundleResult.dry_run_result: dict[str, DryRunOutput]` → `dry_run_failures: dict[str, str]`. Caller-visible breaking change in the result schema; intentional per plan §1 "no relocation — these types should not exist".

### `pipelex/graph/graph_rendering.py`

`_dry_run_bundle()` rewritten to call `PipelexRunner.execute_pipeline()` directly with `pipe_run_mode=DRY`, `generate_graph=True`, `mock_inputs=True`. Reads `response.pipe_output.graph_spec`. No behavior change; one less indirection.

### Validators (six callsites migrated)

| File | Behavior change |
|---|---|
| `pipelex/cli/commands/validate/_validate_core.py` | `do_validate_all_libraries_and_dry_run` and `_validate_pipe_or_bundle` now call `dry_run_loaded_pipes_or_raise(...)` after `library_manager.load_libraries(...)`. |
| `pipelex/cli/agent_cli/commands/validate/_validate_core.py` | `validate_all_core`, `validate_pipe_core`, `validate_pipe_in_bundle_core` migrated. `validate_pipe_in_bundle_core` simplified: `validate_bundle()` now dry-runs everything, so it just confirms the requested pipe is in the loaded set. JSON output still reports `status: "SUCCESS"` per pipe (no longer per-pipe `DryRunOutput.status` since that type is gone). |
| `pipelex/builder/operations/validate_ops.py` | Same five-function shape as the agent CLI variant. |
| `pipelex/builder/operations/runner_code_ops.py` | `build_runner_code_for_pipe` swaps `dry_run_pipes(...)` for `dry_run_loaded_pipes_or_raise(...)`. |

### Tests

- **NEW** `tests/integration/pipelex/pipeline/test_validate_bundle_dry_run.py`. The MUST-add regression from plan §8. Bundle: a top-level `PipeSequence` recurses into a sub-`PipeSequence` that calls back into the top-level — passes static validation, blows the pipe_stack limit at dry-run. Asserts `validate_bundle` raises `ValidateBundleError` with `dry_run_error_message` populated and the message mentions `broken_sub_pipe` or `missing_input`.
- **EDITED** `tests/integration/pipelex/pipes/controller/pipe_sequence/test_pipe_sequence_list_output_bug.py`. Four `dry_run_pipe(...)` calls swapped for `dry_run_loaded_pipes_or_raise([...], library_id=get_current_library())`. Tests now succeed-on-no-exception instead of asserting `DryRunOutput.status.name == "SUCCESS"`.
- **EDITED** `tests/integration/pipelex/temporal/library_crate/conftest.py`. Replaced `convert_to_working_memory_format` import with `WorkingMemoryFactory.convert_input_specs_to_typed`.
- **DELETED** `tests/unit/pipelex/pipe_run/test_dry_run.py`.

## Design addition not in the plan: `keep_library_loaded`

**Why the plan didn't anticipate it.** Plan §4 said: "Six callsites become `try/except` loops over `runner.execute_pipeline(pipe_code=p, pipe_run_mode=DRY, mock_inputs=True)`." The plan glossed over an issue: `PipelexRunner.execute_pipeline()` tears down its library in `finally`:

```python
if library_id_resolved is not None:
    get_library_manager().teardown(library_id=library_id_resolved)
    teardown_current_library()
```

That's correct for one-shot calls (`one runner = one library = one run`). It's wrong for the validator pattern, which pre-loads a library once and iterates N pipes through the runner. Without intervention, the first iteration's teardown would destroy the library; iteration #2 would fail with "library does not exist."

**The fix.** Add `keep_library_loaded: bool = False` to `PipelexRunner.__init__` and thread it through `pipeline_run_setup`. Two sites become conditional:

```python
# runner.py finally
if library_id_resolved is not None and not self.keep_library_loaded:
    get_library_manager().teardown(library_id=library_id_resolved)
    teardown_current_library()

# pipeline_run_setup.py error-path cleanup
if not keep_library_loaded:
    library_manager.teardown(library_id=library_id)
    teardown_current_library()
```

**Ownership rule (encoded by the flag).**

- Flag omitted / `False`: runner owns the library. Original behavior.
- Flag `True`: caller owns the library. Caller is responsible for pre-loading and for tearing down. Used by `dry_run_loaded_pipes` and every validator that pre-loads.

This is the only behavioral addition beyond the plan. It's local to two files and a single boolean — minimal, opt-in, no impact on existing callers.

## Behavioral changes worth flagging in the PR

1. **`DryRunStatus.SKIPPED` is gone.** The old `dry_run_pipe` used to catch `PipeNotFoundError` for unresolved cross-package dependencies and return `SKIPPED`. After the refactor, an unresolved pipe is a hard `PipelineExecutionError`. Rationale: silent skipping masks real validation issues; if you want a dependency to be optional, declare it as such.

2. **`allowed_to_fail_pipes` is gone.** The historical `infinite_loop_1` / `pipe_builder` allowances were brittle (bare codes, multi-domain collision) and conflicted with the new "dry-run failure is a real failure" model. The `infinite_loop_1` fixture in `tests/integration/pipelex/pipes/pipelines/failing_pipelines.mthds` is now only loaded by tests that explicitly intend to assert the failure mode; `make agent-test` still passes.

3. **`ValidateBundleResult` schema change.** `dry_run_result: dict[str, DryRunOutput]` → `dry_run_failures: dict[str, str]`. Anything consuming `result.dry_run_result.get(...).status` will break — there is no such field anymore. Successful pipes are not in the dict. Agent CLI / builder JSON output schemas updated to hardcode `"status": "SUCCESS"` per pipe (no per-pipe status surfacing since failures raise).

4. **Validator performance.** Each runner invocation pays `pipeline_run_setup` overhead (~10–15 ms vs ~5 ms for the old direct `pipe.run_pipe(...)`). Multiplied by the number of pipes in a bundle. Plan §"Performance impact" accepts this: validators are not a hot path, and recursively dry-running a controller covers its children, so a 50-pipe bundle is typically 5–10 top-level invocations, not 50. Measured overhead ~50–150 ms per bundle.

## What was NOT changed

Kept as-is per plan §"Kept as-is":

- `PipeRouterProtocol`, `PipeRunProtocol` — both still earn their keep as the Router/Run seam that `TemporalPipeRouter` and `TemporalPipeRun` extend.
- Two-layer Router/Run split — mirrors Temporal parent/child workflow shape.
- Pipe-level `_dry_run_pipe` / `_dry_run_operator_pipe` / `_dry_run_controller_pipe` — legitimate per-pipe-type override points; this is the only place `run_mode` should matter.

Explicitly out of scope (deferred to follow-up PRs):

- API endpoint unification (`/validate` + `/execute` → `/run` in `pipelex-api`)
- CLI artifact dedup (`_run_core.py:178-203` manual file writes) — depends on a `LocalStorageProvider` per-request-root design
- Renaming `WfPipeRouter` / `WfPipeRun` for clarity (`A-taxonomy.md` §6 smell #1)
