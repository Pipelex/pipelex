import time

from pydantic import BaseModel, ValidationError

from pipelex import log
from pipelex.config import get_config
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs, NamedStuffSpec, TypedNamedStuffSpec
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_class_registry
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.pipe_operators.compose.exceptions import PipeComposeError
from pipelex.pipe_run.exceptions import DryRunError, PipeRunError
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipe_signature.exceptions import SignaturesNotAllowedError
from pipelex.pipe_signature.signature_walk import collect_signature_paths, collect_signature_refs
from pipelex.pipeline.exceptions import PipeStackOverflowError
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.pipeline.pipeline_models import SpecialPipelineId
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error
from pipelex.types import StrEnum


class DryRunStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    SKIPPED = "SKIPPED"

    @property
    def is_failure(self) -> bool:
        match self:
            case DryRunStatus.FAILURE:
                return True
            case DryRunStatus.SUCCESS | DryRunStatus.SKIPPED:
                return False

    @property
    def is_success(self) -> bool:
        match self:
            case DryRunStatus.SUCCESS:
                return True
            case DryRunStatus.FAILURE | DryRunStatus.SKIPPED:
                return False


class DryRunOutput(BaseModel):
    pipe_code: str
    status: DryRunStatus
    error_message: str | None = None


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
        needed_inputs_for_factory = convert_to_working_memory_format(needed_inputs_spec=pipe.needed_inputs())
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
        return DryRunOutput(pipe_code=pipe.code, status=DryRunStatus.SKIPPED, error_message=error_message)
    except (PipeStackOverflowError, ValidationError, PipeComposeError) as exc:
        formatted_error = format_pydantic_validation_error(exc) if isinstance(exc, ValidationError) else str(exc)
        if pipe.code in get_config().pipelex.dry_run_config.allowed_to_fail_pipes:
            error_message = f"Allowed to fail dry run for pipe '{pipe.code}': {formatted_error}"
            return DryRunOutput(pipe_code=pipe.code, status=DryRunStatus.FAILURE, error_message=error_message)
        elif raise_on_failure:
            msg = f"Dry run failed for pipe '{pipe.code}': {formatted_error}"
            raise PipeRunError(message=msg, run_mode=PipeRunMode.DRY, pipe_code=pipe.code) from exc
        else:
            error_message = f"Dry run failed for pipe '{pipe.code}': {formatted_error}"
            return DryRunOutput(pipe_code=pipe.code, status=DryRunStatus.FAILURE, error_message=error_message)
    log.verbose(f"✅ Pipe '{pipe.code}' dry run completed successfully")
    return DryRunOutput(pipe_code=pipe.code, status=DryRunStatus.SUCCESS)


async def dry_run_pipes(
    pipes: list[PipeAbstract],
    *,
    allow_signatures: bool = False,
    raise_on_failure: bool = True,
) -> dict[str, DryRunOutput]:
    """Dry run pipes with optional parallelization.

    Args:
        pipes: List of pipes to dry run
        allow_signatures: If False (default), reject any pipe whose dependency graph reaches a
            `PipeSignature`. If True, signatures dry-run trivially by minting a mock output.
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


def convert_to_working_memory_format(needed_inputs_spec: InputStuffSpecs) -> list[TypedNamedStuffSpec]:
    """Convert PipeInput to the format needed by WorkingMemoryFactory.make_for_dry_run.

    Args:
        needed_inputs_spec: PipeInput with detailed_requirements

    Returns:
        List of tuples (variable_name, concept_code, structure_class)

    """
    needed_inputs_for_factory: list[TypedNamedStuffSpec] = []
    class_registry = get_class_registry()

    # TODO: fail and raise properly
    for named_stuff_spec in needed_inputs_spec.named_stuff_specs:
        try:
            # Get the concept and its structure class
            concept = named_stuff_spec.concept
            structure_class_name = concept.structure_class_name

            # Get the actual class from the registry
            structure_class = class_registry.get_class(name=structure_class_name)

            if structure_class and issubclass(structure_class, StuffContent):
                typed_named_stuff_spec = TypedNamedStuffSpec.make_from_named(
                    named=named_stuff_spec,
                    structure_class=structure_class,
                )
                needed_inputs_for_factory.append(typed_named_stuff_spec)
            else:
                # Fallback to TextContent if we can't get the proper class
                log.verbose(
                    f"Could not get structure class '{structure_class_name}' for "
                    f"concept '{named_stuff_spec.concept.code}', falling back to TextContent",
                )
                text_typed_named_stuff_spec = TypedNamedStuffSpec.make_from_named(
                    named=named_stuff_spec,
                    structure_class=TextContent,
                )
                needed_inputs_for_factory.append(text_typed_named_stuff_spec)

        except ValidationError as exc:
            # Fallback to TextContent when the typed stuff spec fails pydantic validation
            log.warning(f"Error getting structure class for concept '{named_stuff_spec.concept.code}': {exc}, falling back to TextContent")
            text_typed_named_stuff_spec = TypedNamedStuffSpec.make_from_named(
                named=named_stuff_spec,
                structure_class=TextContent,
            )
            needed_inputs_for_factory.append(text_typed_named_stuff_spec)

    return needed_inputs_for_factory


def convert_stuff_spec_to_typed_named(stuff_spec: StuffSpec, name: str) -> TypedNamedStuffSpec:
    """Resolve a single output `StuffSpec` to a `TypedNamedStuffSpec`.

    Mirrors the class-registry lookup behavior used inside `convert_to_working_memory_format`:
    looks up the concept's `structure_class_name`, and falls back to `TextContent` when the
    class is missing from the registry (matching the existing fallback for inputs).
    """
    class_registry = get_class_registry()
    concept = stuff_spec.concept
    structure_class_name = concept.structure_class_name
    named = NamedStuffSpec(
        variable_name=name,
        concept=concept,
        multiplicity=stuff_spec.multiplicity,
    )
    structure_class = class_registry.get_class(name=structure_class_name)
    if structure_class and issubclass(structure_class, StuffContent):
        return TypedNamedStuffSpec.make_from_named(named=named, structure_class=structure_class)
    log.verbose(
        f"Could not get structure class '{structure_class_name}' for concept '{concept.code}', falling back to TextContent",
    )
    return TypedNamedStuffSpec.make_from_named(named=named, structure_class=TextContent)
