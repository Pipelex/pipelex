# Validate Graphs With an Explicit Pipe Target

## Problem

Validation can only attach a `graph_spec` when the submitted batch declares a `main_pipe`. The current path is deliberate:

- `select_primary_blueprint()` picks the first blueprint declaring `main_pipe`; if none does, it returns the first blueprint with `main_pipe_ref=None`.
- `validate_bundles_in_process()` passes that `main_pipe_ref` to `best_effort_graph_spec()`.
- `best_effort_graph_spec()` returns `None` when `pipe_ref` is `None`.
- The CLI graph helpers use `dry_run_pipeline()`, which is stricter: no `main_pipe` raises `PipelexInterpreterError("Bundle does not declare a main_pipe, cannot generate graph")`.

This makes sense for the default report because `GraphSpec` is currently an execution trace for one root pipe, not a static diagram of every declared pipe in the bundle. But it blocks a useful case: a valid bundle with no declared `main_pipe`, or a partially built bundle where the caller wants to validate and graph one specific pipe.

## Proposed Lift

Support an explicit graph target pipe for validation graph generation.

The rule becomes:

- If the caller provides a graph target pipe, dry-run that pipe for `graph_spec`.
- Otherwise keep today's default: use the batch's selected `main_pipe`.
- If neither exists, keep returning `graph_spec=None` on protocol/API validation and keep the CLI graph command's explicit "cannot generate graph" error when a graph was requested.

This is intentionally not "graph the whole bundle." Whole-bundle static graphing is a different artifact with different semantics. This lift stays inside the existing execution-trace model by choosing one pipe to execute.

## Existing Machinery To Reuse

Most of the lower-level plumbing already supports this:

- `best_effort_graph_spec(pipe_ref=...)` can dry-run any resolved pipe ref against the already-open validation library.
- `act_dry_validate.DryValidateArg.pipe_code` already exists and is used as an override before falling back to `select_primary_blueprint(...).main_pipe_ref`.
- `pipeline_run_setup()` already supports `pipe_code` overriding `main_pipe` when executing MTHDS contents.
- `validate_bundle(..., dry_run_pipe_codes=[pipe_code])` already validates a single selected pipe within a bundle.

The missing work is making the direct/public validation surfaces carry the graph target consistently, and making CLI graph/view generation use it.

## Implementation Shape

1. Add an optional graph target parameter to the shared in-process validate orchestrator.

   Suggested signature:

   ```python
   async def validate_bundles_in_process(
       *,
       mthds_contents: list[str],
       mthds_sources: list[str] | None = None,
       library_dirs: Sequence[Path] | None = None,
       allow_signatures: bool = False,
       graph_pipe_code: str | None = None,
       log_context: str = "validate",
   ) -> PipelexValidationReport:
   ```

   The graph arm should call:

   ```python
   graph_target_ref = graph_pipe_code or select_primary_blueprint(result.blueprints).main_pipe_ref
   graph_spec = await best_effort_graph_spec(
       pipe_ref=graph_target_ref,
       library_id=validation_library_id,
       log_context=log_context,
   )
   ```

   This preserves today's `None` behavior when no target exists. Unknown `graph_pipe_code` should degrade to `graph_spec=None` on the best-effort report path, because `best_effort_graph_spec()` intentionally catches pipe-resolution domain failures.

2. Thread the same option through `PipelexMTHDSProtocol.validate()` if the protocol layer has an extension argument for it.

   Today local protocol `validate()` rejects every `extra` key. Two reasonable choices:

   - accept `extra={"graph_pipe_code": "..."}` for Pipelex-specific local runtime usage;
   - leave protocol `validate()` unchanged and expose the option only on API/CLI surfaces that already have concrete request fields.

   If the hosted MTHDS Protocol surface needs this, prefer a typed request field in the API schema and map it into the shared orchestrator rather than relying on untyped `extra`.

3. Wire the Temporal path using the field that already exists.

   `DryValidateArg.pipe_code` already chooses:

   ```python
   arg.pipe_code or select_primary_blueprint(validate_result.blueprints).main_pipe_ref
   ```

   Check the API dispatch layer and ensure the request's graph target field is passed into `DryValidateArg.pipe_code`. Rename to `graph_pipe_code` later if clarity is worth the wire break; no compatibility constraint blocks that, but avoid churn unless the surrounding API field also uses that name.

4. Update agent CLI `validate bundle --pipe X --graph/--view`.

   Today `--pipe` narrows validation, but `--graph` and `--view` still call `generate_graph_for_bundle()` / `generate_view_for_bundle()`, which eventually call `dry_run_pipeline()` with no pipe override and therefore require `main_pipe`.

   Add a pipe override to the graph rendering helpers:

   ```python
   async def _dry_run_bundle(
       bundle_path: Path,
       *,
       library_dirs: list[str] | None = None,
       pipe_code: str | None = None,
   ) -> tuple[GraphSpec, str]:
   ```

   Then either:

   - extend `dry_run_pipeline(..., pipe_code: str | None = None)` and let it pass the override into `runner.execute(pipe_code=pipe_code or main_pipe_ref, ...)`; or
   - bypass the pre-parse `main_pipe` requirement in `_dry_run_bundle()` when `pipe_code` is supplied.

   The first option is cleaner because it keeps one graph-producing bundle execution helper.

5. Decide bare vs qualified pipe target rules.

   Current pipe library lookup accepts either a unique bare code or a qualified `domain.code` ref. For multi-domain batches, qualified refs are safer. Recommended behavior:

   - accept both bare and qualified targets;
   - document that bare targets must be unique in the loaded library;
   - let existing `PipeLibrary.get_required_pipe()` ambiguity errors flow through the best-effort degradation path for report graph generation and through explicit CLI graph errors when the user requested graph output.

## Tests

Add tests at the existing pin points:

- `tests/integration/pipelex/pipeline/test_protocol_validate.py`
  - no `main_pipe` plus explicit graph target produces a non-null `graph_spec`;
  - explicit graph target overrides declared `main_pipe`;
  - unknown explicit graph target degrades to `graph_spec=None` on the validation report path.

- Agent CLI validate bundle tests
  - `validate bundle no_main.mthds --pipe some_pipe --view` succeeds and includes a `graphspec`;
  - `validate bundle no_main.mthds --view` still errors because graph was explicitly requested and no target exists;
  - `validate bundle bundle_with_main.mthds --pipe other_pipe --view` graphs `other_pipe`, not the declared `main_pipe`.

- Temporal dry-validate/API path
  - request with explicit graph target maps to `DryValidateArg.pipe_code`;
  - direct and Temporal modes produce the same `graph_spec` target behavior.

## Non-Goals

- Do not infer a root from "the only pipe in the bundle" unless product explicitly wants that policy. It sounds convenient but creates a hidden second default alongside `main_pipe`.
- Do not create a static all-pipes `GraphSpec` under the same field. That would overload an execution-trace artifact with non-execution semantics.
- Do not require `main_pipe` to validate a bundle. Current validation correctly supports concept-only files, membership-only files, and top-down partial bundles.

## Files To Touch

- `pipelex/pipeline/validate_in_process.py`
- `pipelex/pipeline/runner.py` if protocol `extra` or a typed protocol extension should expose it
- hosted API validate request/dispatch mapping in `pipelex-api`
- `pipelex/temporal/tprl_pipe/act_dry_validate.py` only if renaming or tightening `pipe_code`
- `pipelex/pipeline/dry_run_pipeline.py`
- `pipelex/graph/graph_rendering.py`
- `pipelex/cli/agent_cli/commands/validate/bundle_cmd.py`
- tests under `tests/integration/pipelex/pipeline/` and agent CLI validate coverage
