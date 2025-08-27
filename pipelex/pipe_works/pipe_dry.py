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


async def dry_run_all_pipes():
    all_pipes = get_pipe_provider().get_pipes()
    await dry_run_pipes(pipes=all_pipes)


async def dry_run_single_pipe(pipe_code: str):
    """
    Dry run a single pipe by its code.

    Args:
        pipe_code: The code of the pipe to dry run

    Returns:
        Status string: "SUCCESS" or error message
    """

    # Get the pipe using the hub function
    pipe = get_pipe_provider().get_required_pipe(pipe_code=pipe_code)
    # Run the single pipe
    await dry_run_pipes(pipes=[pipe])


async def dry_run_pipe_codes(pipe_codes: List[str]) -> Dict[str, str]:
    """
    Dry run a list of pipe codes.
    """
    pipe_provider = get_pipe_provider()
    pipes = [pipe_provider.get_required_pipe(pipe_code=pipe_code) for pipe_code in pipe_codes]
    return await dry_run_pipes(pipes=pipes)


async def dry_run_pipe(pipe: PipeAbstract):
    """
    Dry run a pipe.
    """
    return await dry_run_pipes(pipes=[pipe])


async def dry_run_pipes(pipes: List[PipeAbstract]) -> Dict[str, str]:
    """
    Dry run all pipes in the library using ThreadPoolExecutor for true parallelism.

    For each pipe, this method:
    1. Gets the pipe's needed inputs
    2. Creates mock working memory using WorkingMemoryFactory.make_for_dry_run
    3. Runs the pipe in dry mode

    Returns:
        Dict mapping pipe codes to their dry run status ("SUCCESS" or error message)
    """

    start_time = time.time()
    results: Dict[str, str] = {}
    pipe_provider = get_pipe_provider()
    pipe_provider.validate_with_libraries()
    # Get the list of pipes that are allowed to fail from config
    allowed_to_fail_pipes = get_config().pipelex.dry_run_config.allowed_to_fail_pipes

    log.info(f"Starting dry run for {len(pipes)} pipes...")

    # Define a function that will run in a thread
    def run_pipe_in_thread(pipe: PipeAbstract) -> Tuple[str, str]:
        """Execute pipe.run_pipe in a thread and return its status."""
        # try:
        # This function runs in a separate thread
        try:
            needed_inputs = pipe.needed_inputs()
            log.debug(f"Needed inputs for {pipe.code}: {needed_inputs}")
            needed_inputs_for_factory = _convert_to_working_memory_format(needed_inputs_spec=needed_inputs)

            log.debug(f"Needed inputs for {pipe.code} converted to working memory format: {needed_inputs_for_factory}")
            working_memory = WorkingMemoryFactory.make_for_dry_run(needed_inputs=needed_inputs_for_factory)

            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                # Run the pipe in this thread's event loop
                loop.run_until_complete(
                    pipe.run_pipe(
                        job_metadata=JobMetadata(job_name=f"dry_run_{pipe.code}"),
                        working_memory=working_memory,
                        pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
                    )
                )
                result = (pipe.code, "SUCCESS")
                log.debug(f"✓ Pipe {pipe.code} dry run completed successfully")
                return result
            finally:
                loop.close()

        except Exception as exc:
            error_msg = f"FAILED: {str(exc)}"

            # Check if this pipe is allowed to fail
            if pipe.code in allowed_to_fail_pipes:
                log.debug(f"✗ Pipe '{pipe.code}' dry run failed: {exc} (this is normal, allowed by config)")
            else:
                log.error(f"✗ Pipe '{pipe.code}' dry run failed: {exc}")

            return (pipe.code, error_msg)

    # Get the event loop for the main thread
    loop = asyncio.get_running_loop()

    # Execute pipes in thread pool
    with ThreadPoolExecutor() as executor:
        # Schedule all pipe executions to the thread pool
        futures = [loop.run_in_executor(executor, functools.partial(run_pipe_in_thread, pipe)) for pipe in pipes]

        # Wait for all executions to complete
        for future in asyncio.as_completed(futures):
            pipe_code, status = await future
            results[pipe_code] = status

    successful_pipes = [pipe_code for pipe_code, status in results.items() if status == "SUCCESS"]
    failed_pipes = [pipe_code for pipe_code, status in results.items() if status != "SUCCESS"]

    # Filter out pipes that are allowed to fail
    unexpected_failures = {pipe_code: results[pipe_code] for pipe_code in failed_pipes if pipe_code not in allowed_to_fail_pipes}

    log.info(f"Dry run completed: '{len(successful_pipes)}' successful, '{len(failed_pipes)}' failed, in '{time.time() - start_time:.2f}' seconds")

    if unexpected_failures:
        unexpected_failures_details = "\n".join([f"'{pipe_code}': {results[pipe_code]}" for pipe_code in unexpected_failures])
        raise Exception(f"Dry run failed with '{len(unexpected_failures)}' unexpected pipe failures:\n{unexpected_failures_details}")

    if failed_pipes and not unexpected_failures:
        log.info("All failures were expected (allowed by config)")

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
