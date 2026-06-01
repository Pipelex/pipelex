import time

from polyfactory.exceptions import FactoryException
from pydantic import ValidationError

from pipelex import log
from pipelex.config import get_config
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.pipe_operators.compose.exceptions import PipeComposeError
from pipelex.pipe_run.exceptions import DryRunError, PipeRunError
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipe_signature.exceptions import SignaturesNotAllowedError
from pipelex.pipe_signature.signature_walk import collect_signature_paths, collect_signature_refs

# DryRunStatus / DryRunOutput now live in bundle_validator (their real owner — they are
# validation-report types, not execution types). Re-imported here so the still-wired callers and
# tests keep importing them from this module until Phase 3/4 migrates them; this module is deleted
# in Phase 4 (no permanent re-export).
from pipelex.pipeline.bundle_validator import DryRunOutput, DryRunStatus
from pipelex.pipeline.exceptions import PipeStackOverflowError
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.pipeline.pipeline_models import SpecialPipelineId
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


async def dry_run_pipe(pipe: PipeAbstract, *, allow_signatures: bool = False, raise_on_failure: bool = False) -> DryRunOutput:
    if not allow_signatures:
        signature_refs = collect_signature_refs(pipe=pipe)
        if signature_refs:
            # A signature is the placeholder itself, not a pipe that "depends on" one —
            # only a non-signature caller belongs in the offender list.
            offending_pipe_refs: set[str] = set() if pipe.is_signature else {pipe.pipe_ref}
            raise SignaturesNotAllowedError(
                offending_pipe_refs=offending_pipe_refs,
                signature_refs=signature_refs,
                dep_paths=collect_signature_paths(pipe=pipe),
            )
    try:
        needed_inputs_for_factory = WorkingMemoryFactory.convert_to_working_memory_format(needed_inputs_spec=pipe.needed_inputs())
        working_memory = WorkingMemoryFactory.make_mock_inputs(needed_inputs=needed_inputs_for_factory)
        pipe.validate_with_libraries()
        await pipe.run_pipe(
            job_metadata=JobMetadata(user_id=OTelConstants.DEFAULT_USER_ID, pipeline_run_id=SpecialPipelineId.DRY_RUN_UNTITLED),
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
        )
    except PipeNotFoundError as not_found_error:
        # Cross-package pipe dependencies may not be loaded; skip gracefully during dry-run
        error_message = f"Skipped dry run for pipe '{pipe.code}': unresolved dependency: {not_found_error}"
        log.verbose(error_message)
        return DryRunOutput(pipe_code=pipe.code, pipe_ref=pipe.pipe_ref, status=DryRunStatus.SKIPPED, error_message=error_message)
    except (PipeStackOverflowError, ValidationError, PipeComposeError, FactoryException) as exc:
        # FactoryException covers a PipeSignature minting its declared mock output via
        # make_mock_stuff (the one content-minting path without the make_mock_inputs fallback):
        # surface it as a clean dry-run failure instead of letting it escape as a raw CLI traceback.
        formatted_error = format_pydantic_validation_error(exc) if isinstance(exc, ValidationError) else str(exc)
        if pipe.code in get_config().pipelex.dry_run_config.allowed_to_fail_pipes:
            error_message = f"Allowed to fail dry run for pipe '{pipe.code}': {formatted_error}"
            return DryRunOutput(pipe_code=pipe.code, pipe_ref=pipe.pipe_ref, status=DryRunStatus.FAILURE, error_message=error_message)
        elif raise_on_failure:
            msg = f"Dry run failed for pipe '{pipe.code}': {formatted_error}"
            raise PipeRunError(message=msg, run_mode=PipeRunMode.DRY, pipe_code=pipe.code) from exc
        else:
            error_message = f"Dry run failed for pipe '{pipe.code}': {formatted_error}"
            return DryRunOutput(pipe_code=pipe.code, pipe_ref=pipe.pipe_ref, status=DryRunStatus.FAILURE, error_message=error_message)
    log.verbose(f"✅ Pipe '{pipe.code}' dry run completed successfully")
    return DryRunOutput(pipe_code=pipe.code, pipe_ref=pipe.pipe_ref, status=DryRunStatus.SUCCESS)


async def dry_run_pipes(
    pipes: list[PipeAbstract],
    *,
    allow_signatures: bool = False,
    raise_on_failure: bool = True,
) -> dict[str, DryRunOutput]:
    """Dry run pipes with optional parallelization.

    Args:
        pipes: List of pipes to dry run
        allow_signatures: If False (default), the whole batch is rejected when any pipe in it
            *is* a `PipeSignature` or *reaches* one through its dependency graph (a signature
            reaches itself). This is why whole-bundle strict validation rejects a bundle that
            merely *contains* a signature, reached or not — the signature is itself in the batch.
            Callers that want to tolerate unreached signatures must keep them out of the batch:
            the `validate --all` paths filter signatures, and `--pipe <code>` passes only the
            requested pipe. If True, signatures dry-run trivially by minting a mock output.
        raise_on_failure: If True, raise an exception if any pipe fails.

    For each pipe, this method:
    1. Gets the pipe's needed inputs
    2. Creates mock working memory using WorkingMemoryFactory.make_for_dry_run
    3. Runs the pipe in dry mode

    Returns:
        Dict mapping pipe codes to their dry run status ("SUCCESS" or error message)

    Raises:
        DryRunError: If raise_on_failure is True and any pipe fails.

    """
    start_time = time.time()
    results: dict[str, DryRunOutput] = {}
    allowed_to_fail_pipes = get_config().pipelex.dry_run_config.allowed_to_fail_pipes

    # Strict-mode signature pre-check: aggregate across all pipes so the user sees every offender
    # in a single error, rather than only the first one to fail (`dry_run_pipe` would otherwise raise).
    if not allow_signatures:
        all_signature_refs: set[str] = set()
        all_dep_paths: dict[str, list[str]] = {}
        offending_pipe_refs: set[str] = set()
        for pipe in pipes:
            sig_refs = collect_signature_refs(pipe=pipe)
            if not sig_refs:
                continue
            # A signature is the placeholder itself, not an offender that "depends on" one.
            if not pipe.is_signature:
                offending_pipe_refs.add(pipe.pipe_ref)
            all_signature_refs.update(sig_refs)
            for sig_ref, path in collect_signature_paths(pipe=pipe).items():
                # Prefer the longest known dep chain so the error message shows the most informative
                # path (a chain rooted at a controller is more useful than an empty chain rooted at
                # the signature itself, which can happen when the signature pipe is iterated first).
                existing = all_dep_paths.get(sig_ref)
                if existing is None or len(path) > len(existing):
                    all_dep_paths[sig_ref] = path
        if all_signature_refs:
            raise SignaturesNotAllowedError(
                offending_pipe_refs=offending_pipe_refs,
                signature_refs=all_signature_refs,
                dep_paths=all_dep_paths,
            )

    for pipe in pipes:
        results[pipe.pipe_ref] = await dry_run_pipe(
            pipe,
            allow_signatures=allow_signatures,
            raise_on_failure=raise_on_failure,
        )

    successful_pipes: list[str] = []
    failed_pipes: list[str] = []
    skipped_pipes: list[str] = []
    for pipe_ref, dry_run_output in results.items():
        match dry_run_output.status:
            case DryRunStatus.SUCCESS:
                successful_pipes.append(pipe_ref)
            case DryRunStatus.FAILURE:
                failed_pipes.append(pipe_ref)
            case DryRunStatus.SKIPPED:
                skipped_pipes.append(pipe_ref)

    # TODO: allowed_to_fail_pipes uses bare codes, so one allowed code can silently match pipes from multiple domains.
    #  Consider supporting namespaced pipe_refs (e.g. "domain.pipe_code") in the config to allow precise targeting.
    unexpected_failures = {pipe_ref: results[pipe_ref] for pipe_ref in failed_pipes if results[pipe_ref].pipe_code not in allowed_to_fail_pipes}

    log.verbose(
        f"Dry run completed: {len(successful_pipes)} successful, {len(failed_pipes)} failed, "
        f"{len(skipped_pipes)} skipped, {len(allowed_to_fail_pipes)} allowed to fail, in {time.time() - start_time:.2f} seconds",
    )
    if unexpected_failures:
        unexpected_failures_details = "\n".join([f"'{pipe_ref}': {results[pipe_ref]}" for pipe_ref in unexpected_failures])
        if raise_on_failure:
            msg = f"Dry run failed with '{len(unexpected_failures)}' unexpected pipe failures:\n{unexpected_failures_details}"
            raise DryRunError(msg)
        log.error(f"Dry run failed with '{len(unexpected_failures)}' unexpected pipe failures:\n{unexpected_failures_details}")
        return results

    return results
