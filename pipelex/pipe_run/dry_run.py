import asyncio
import functools
import time
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel

from pipelex import log
from pipelex.config import get_config
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.input_requirements import InputRequirements, TypedNamedInputRequirement
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.exceptions import PipeStackOverflowError
from pipelex.hub import get_class_registry
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.types import StrEnum


class DryRunError(Exception):
    """Raised when a dry run fails due to missing inputs or other validation issues."""


class DryRunStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"

    @property
    def is_failure(self) -> bool:
        match self:
            case DryRunStatus.FAILURE:
                return True
            case DryRunStatus.SUCCESS:
                return False


class DryRunOutput(BaseModel):
    pipe_code: str
    status: DryRunStatus
    error_message: str | None = None


async def dry_run_pipe(pipe: PipeAbstract, raise_on_failure: bool = False) -> DryRunOutput:
    """Dry run a single pipe directly without parallelization."""
    allowed_to_fail_pipes = get_config().pipelex.dry_run_config.allowed_to_fail_pipes
    # TODO: fail and raise properly
    try:
        needed_inputs_for_factory = _convert_to_working_memory_format(needed_inputs_spec=pipe.needed_inputs())

        working_memory = WorkingMemoryFactory.make_for_dry_run(needed_inputs=needed_inputs_for_factory)
        pipe.validate_with_libraries()
        await pipe.run_pipe(
            job_metadata=JobMetadata(job_name=f"dry_run_{pipe.code}"),
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
        )
    except PipeStackOverflowError as exc:
        if pipe.code in allowed_to_fail_pipes:
            error_message = f"Allowed to fail dry run for pipe '{pipe.code}': {exc}"
            return DryRunOutput(pipe_code=pipe.code, status=DryRunStatus.FAILURE, error_message=error_message)
        elif raise_on_failure:
            raise

        error_message = f"Dry run failed for pipe '{pipe.code}': {exc}"
        return DryRunOutput(pipe_code=pipe.code, status=DryRunStatus.FAILURE, error_message=error_message)
    log.info(f"Pipe '{pipe.code}' dry run completed successfully")
    return DryRunOutput(pipe_code=pipe.code, status=DryRunStatus.SUCCESS)


async def dry_run_pipes(pipes: list[PipeAbstract], run_in_parallel: bool = True, raise_on_failure: bool = True) -> dict[str, DryRunOutput]:
    """Dry run pipes with optional parallelization.

    Args:
        pipes: List of pipes to dry run
        run_in_parallel: If True, run pipes in parallel using ThreadPoolExecutor. If False, run sequentially.
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

    if run_in_parallel:

        def run_pipe_in_thread(pipe: PipeAbstract) -> DryRunOutput:
            """Parallel execution using ThreadPoolExecutor"""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(dry_run_pipe(pipe, raise_on_failure=raise_on_failure))

        with ThreadPoolExecutor() as executor:
            futures = [asyncio.get_running_loop().run_in_executor(executor, functools.partial(run_pipe_in_thread, pipe)) for pipe in pipes]
            for future in asyncio.as_completed(futures):
                output = await future
                results[output.pipe_code] = output
    else:
        for pipe in pipes:
            results[pipe.code] = await dry_run_pipe(pipe, raise_on_failure=raise_on_failure)

    successful_pipes: list[str] = []
    failed_pipes: list[str] = []
    for pipe_code, dry_run_output in results.items():
        match dry_run_output.status:
            case DryRunStatus.SUCCESS:
                successful_pipes.append(pipe_code)
            case DryRunStatus.FAILURE:
                failed_pipes.append(pipe_code)

    unexpected_failures = {pipe_code: results[pipe_code] for pipe_code in failed_pipes if pipe_code not in allowed_to_fail_pipes}

    log.info(
        f"Dry run completed: '{len(successful_pipes)}' successful, '{len(failed_pipes)}' failed, "
        f"'{len(allowed_to_fail_pipes)}' allowed to fail, in '{time.time() - start_time:.2f}' seconds",
    )
    if unexpected_failures:
        unexpected_failures_details = "\n".join([f"'{pipe_code}': {results[pipe_code]}" for pipe_code in unexpected_failures])
        if raise_on_failure:
            msg = f"Dry run failed with '{len(unexpected_failures)}' unexpected pipe failures:\n{unexpected_failures_details}"
            raise DryRunError(msg)
        log.error(f"Dry run failed with '{len(unexpected_failures)}' unexpected pipe failures:\n{unexpected_failures_details}")
        return results

    return results


def _convert_to_working_memory_format(needed_inputs_spec: InputRequirements) -> list[TypedNamedInputRequirement]:
    """Convert PipeInput to the format needed by WorkingMemoryFactory.make_for_dry_run.

    Args:
        needed_inputs_spec: PipeInput with detailed_requirements

    Returns:
        List of tuples (variable_name, concept_code, structure_class)

    """
    needed_inputs_for_factory: list[TypedNamedInputRequirement] = []
    class_registry = get_class_registry()

    # TODO: fail and raise properly
    for named_input_requirement in needed_inputs_spec.named_input_requirements:
        try:
            # Get the concept and its structure class
            concept = named_input_requirement.concept
            structure_class_name = concept.structure_class_name

            # Get the actual class from the registry
            structure_class = class_registry.get_class(name=structure_class_name)

            if structure_class and issubclass(structure_class, StuffContent):
                typed_named_input_requirement = TypedNamedInputRequirement.make_from_named(
                    named=named_input_requirement,
                    structure_class=structure_class,
                )
                needed_inputs_for_factory.append(typed_named_input_requirement)
            else:
                # Fallback to TextContent if we can't get the proper class
                log.warning(
                    f"Could not get structure class '{structure_class_name}' for "
                    f"concept '{named_input_requirement.concept.code}', falling back to TextContent",
                )
                text_typed_named_input_requirement = TypedNamedInputRequirement.make_from_named(
                    named=named_input_requirement,
                    structure_class=TextContent,
                )
                needed_inputs_for_factory.append(text_typed_named_input_requirement)

        except Exception as exc:
            # Fallback to TextContent for any errors
            log.warning(f"Error getting structure class for concept '{named_input_requirement.concept.code}': {exc}, falling back to TextContent")
            text_typed_named_input_requirement = TypedNamedInputRequirement.make_from_named(
                named=named_input_requirement,
                structure_class=TextContent,
            )
            needed_inputs_for_factory.append(text_typed_named_input_requirement)

    return needed_inputs_for_factory
