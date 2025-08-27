import asyncio
import functools
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple

from pipelex import log
from pipelex.config import get_config
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_input_spec import PipeInputSpec, TypedNamedInputRequirement
from pipelex.core.pipes.pipe_run_params import PipeRunMode
from pipelex.core.pipes.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuffs.stuff_content import StuffContent, TextContent
from pipelex.hub import get_class_registry, get_pipe_provider
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.types import StrEnum


class DryRunStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


async def dry_run_pipe(pipe: PipeAbstract) -> None:
    """
    Dry run a single pipe directly without parallelization.
    """
    needed_inputs_for_factory = _convert_to_working_memory_format(needed_inputs_spec=pipe.needed_inputs())

    working_memory = WorkingMemoryFactory.make_for_dry_run(needed_inputs=needed_inputs_for_factory)

    await pipe.run_pipe(
        job_metadata=JobMetadata(job_name=f"dry_run_{pipe.code}"),
        working_memory=working_memory,
        pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
    )
    log.debug(f"✓ Pipe {pipe.code} dry run completed successfully")


async def dry_run_pipes(pipes: List[PipeAbstract], run_in_parallel: bool = True) -> Dict[str, str]:
    """
    Dry run pipes with optional parallelization.

    Args:
        pipes: List of pipes to dry run
        run_in_parallel: If True, run pipes in parallel using ThreadPoolExecutor. If False, run sequentially.

    For each pipe, this method:
    1. Gets the pipe's needed inputs
    2. Creates mock working memory using WorkingMemoryFactory.make_for_dry_run
    3. Runs the pipe in dry mode

    Returns:
        Dict mapping pipe codes to their dry run status ("SUCCESS" or error message)
    """

    start_time = time.time()
    results: Dict[str, str] = {}
    get_pipe_provider().validate_with_libraries()
    allowed_to_fail_pipes = get_config().pipelex.dry_run_config.allowed_to_fail_pipes

    if run_in_parallel:
        # Parallel execution using ThreadPoolExecutor
        def run_pipe_in_thread(pipe: PipeAbstract) -> Tuple[str, str]:
            """Execute dry_run_pipe in a thread and return its status."""
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(dry_run_pipe(pipe))
                return (pipe.code, DryRunStatus.SUCCESS)
            except Exception as exc:
                error_message = f"Dry run failed for pipe '{pipe.code}': {exc}"
                if pipe.code in allowed_to_fail_pipes:
                    warning_message = f"Allowed to fail dry run for pipe '{pipe.code}': {error_message}"
                    log.warning(warning_message)
                else:
                    log.error(error_message)
                return (pipe.code, error_message)

        with ThreadPoolExecutor() as executor:
            futures = [asyncio.get_running_loop().run_in_executor(executor, functools.partial(run_pipe_in_thread, pipe)) for pipe in pipes]

            for future in asyncio.as_completed(futures):
                pipe_code, status = await future
                results[pipe_code] = status
    else:
        for pipe in pipes:
            try:
                await dry_run_pipe(pipe)
                results[pipe.code] = DryRunStatus.SUCCESS
            except Exception as exc:
                error_message = f"Dry run failed for pipe '{pipe.code}': {exc}"
                if pipe.code in allowed_to_fail_pipes:
                    warning_message = f"Allowed to fail dry run for pipe '{pipe.code}': {error_message}"
                    log.warning(warning_message)
                else:
                    log.error(error_message)
                results[pipe.code] = error_message

    successful_pipes = [pipe_code for pipe_code, status in results.items() if status == DryRunStatus.SUCCESS]
    failed_pipes = [pipe_code for pipe_code, status in results.items() if status != DryRunStatus.SUCCESS]

    unexpected_failures = {pipe_code: results[pipe_code] for pipe_code in failed_pipes if pipe_code not in allowed_to_fail_pipes}

    log.info(
        f"Dry run completed: '{len(successful_pipes)}' successful, '{len(failed_pipes)}' failed, "
        f"'{len(allowed_to_fail_pipes)}' allowed to fail, in '{time.time() - start_time:.2f}' seconds"
    )
    if unexpected_failures:
        unexpected_failures_details = "\n".join([f"'{pipe_code}': {results[pipe_code]}" for pipe_code in unexpected_failures])
        raise Exception(f"Dry run failed with '{len(unexpected_failures)}' unexpected pipe failures:\n{unexpected_failures_details}")

    return results


def _convert_to_working_memory_format(needed_inputs_spec: PipeInputSpec) -> List[TypedNamedInputRequirement]:
    """
    Convert PipeInputSpec to the format needed by WorkingMemoryFactory.make_for_dry_run.

    Args:
        needed_inputs_spec: PipeInputSpec with detailed_requirements

    Returns:
        List of tuples (variable_name, concept_code, structure_class)
    """
    needed_inputs_for_factory: List[TypedNamedInputRequirement] = []
    class_registry = get_class_registry()

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
                    f"concept '{named_input_requirement.concept.code}', falling back to TextContent"
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
