import asyncio
from itertools import groupby
from typing import Dict, List, Optional, Tuple, Type

from pydantic import Field, RootModel
from rich import box
from rich.table import Table
from typing_extensions import override

from pipelex import log, pretty_print
from pipelex.config import get_config
from pipelex.core.pipe_abstract import PipeAbstract
from pipelex.core.pipe_input_spec import PipeInputSpec
from pipelex.core.pipe_provider_abstract import PipeProviderAbstract
from pipelex.core.pipe_run_params import PipeRunMode
from pipelex.core.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuff_content import StuffContent, TextContent
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.exceptions import ConceptError, ConceptLibraryConceptNotFoundError, PipeLibraryError, PipeLibraryPipeNotFoundError
from pipelex.hub import get_class_registry, get_concept_provider
from pipelex.pipeline.job_metadata import JobMetadata

PipeLibraryRoot = Dict[str, PipeAbstract]


class PipeLibrary(RootModel[PipeLibraryRoot], PipeProviderAbstract):
    root: PipeLibraryRoot = Field(default_factory=dict)

    def validate_with_libraries(self):
        concept_provider = get_concept_provider()
        for pipe in self.root.values():
            try:
                for concept_code in pipe.concept_dependencies():
                    try:
                        concept_provider.get_required_concept(concept_code=concept_code)
                    except ConceptError as concept_error:
                        raise PipeLibraryError(
                            f"Error validating pipe '{pipe.code}' dependency concept '{concept_code}' because of: {concept_error}"
                        ) from concept_error
                for pipe_code in pipe.pipe_dependencies():
                    self.get_required_pipe(pipe_code=pipe_code)
                pipe.validate_with_libraries()
            except (ConceptLibraryConceptNotFoundError, PipeLibraryPipeNotFoundError) as not_found_error:
                raise PipeLibraryError(f"Missing dependency for pipe '{pipe.code}': {not_found_error}") from not_found_error
        asyncio.run(self.dry_run_all_pipes())

    def add_new_pipe(self, pipe: PipeAbstract):
        name = pipe.code
        pipe.inputs.set_default_domain(domain=pipe.domain)
        if pipe.output_concept_code and "." not in pipe.output_concept_code:
            pipe.output_concept_code = f"{pipe.domain}.{pipe.output_concept_code}"
        if name in self.root:
            raise PipeLibraryError(f"Pipe '{name}' already exists in the library")
        self.root[pipe.code] = pipe

    async def dry_run_all_pipes(self) -> Dict[str, str]:
        """
        Dry run all pipes in the library.

        For each pipe, this method:
        1. Gets the pipe's needed inputs
        2. Creates mock working memory using WorkingMemoryFactory.make_for_dry_run
        3. Runs the pipe in dry mode

        Returns:
            Dict mapping pipe codes to their dry run status ("SUCCESS" or error message)
        """
        results: Dict[str, str] = {}
        pipes = self.get_pipes()

        # Get the list of pipes that are allowed to fail from config
        allowed_to_fail_pipes = get_config().pipelex.dry_run_config.allowed_to_fail_pipes

        log.info(f"Starting dry run for {len(pipes)} pipes...")

        for pipe in pipes:
            if pipe.code != "write_markdown_from_page_content_dpe":
                continue
            try:
                needed_inputs_for_factory = self._convert_to_working_memory_format(pipe.needed_inputs())
                working_memory = WorkingMemoryFactory.make_for_dry_run(needed_inputs=needed_inputs_for_factory)
                await pipe.run_pipe(
                    job_metadata=JobMetadata(job_name=f"dry_run_{pipe.code}"),
                    working_memory=working_memory,
                    pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
                )

                results[pipe.code] = "SUCCESS"
                log.debug(f"✓ Pipe {pipe.code} dry run completed successfully")

            except Exception as e:
                error_msg = f"FAILED: {str(e)}"
                results[pipe.code] = error_msg

                # Check if this pipe is allowed to fail
                if pipe.code in allowed_to_fail_pipes:
                    log.debug(f"✗ Pipe {pipe.code} dry run failed: {e} (this is normal, allowed by config)")
                else:
                    log.error(f"✗ Pipe {pipe.code} dry run failed: {e}")

        successful_pipes = [code for code, status in results.items() if status == "SUCCESS"]
        failed_pipes = [code for code, status in results.items() if status != "SUCCESS"]

        # Filter out pipes that are allowed to fail
        unexpected_failures = [pipe for pipe in failed_pipes if pipe not in allowed_to_fail_pipes]

        log.info(f"Dry run completed: {len(successful_pipes)} successful, {len(failed_pipes)} failed")

        if unexpected_failures:
            raise Exception(f"Dry run failed with {len(unexpected_failures)} unexpected pipe failures: {', '.join(unexpected_failures)}")

        if failed_pipes and not unexpected_failures:
            log.info("All failures were expected (allowed by config)")

        return results

    def _convert_to_working_memory_format(self, needed_inputs_spec: PipeInputSpec) -> List[Tuple[str, str, Type[StuffContent]]]:
        """
        Convert PipeInputSpec to the format needed by WorkingMemoryFactory.make_for_dry_run.

        Args:
            needed_inputs_spec: PipeInputSpec with detailed_requirements

        Returns:
            List of tuples (variable_name, concept_code, structure_class)
        """
        needed_inputs_for_factory: List[Tuple[str, str, Type[StuffContent]]] = []
        concept_provider = get_concept_provider()
        class_registry = get_class_registry()

        for required_variable_name, _, concept_code in needed_inputs_spec.detailed_requirements:
            try:
                # Get the concept and its structure class
                concept = concept_provider.get_required_concept(concept_code=concept_code)
                structure_class_name = concept.structure_class_name

                # Get the actual class from the registry
                structure_class = class_registry.get_class(name=structure_class_name)

                if structure_class and issubclass(structure_class, StuffContent):
                    needed_inputs_for_factory.append((required_variable_name, concept_code, structure_class))
                else:
                    # Fallback to TextContent if we can't get the proper class
                    log.warning(f"Could not get structure class '{structure_class_name}' for concept '{concept_code}', falling back to TextContent")
                    needed_inputs_for_factory.append((required_variable_name, concept_code, TextContent))

            except Exception as e:
                # Fallback to TextContent for any errors
                log.warning(f"Error getting structure class for concept '{concept_code}': {e}, falling back to TextContent")
                needed_inputs_for_factory.append((required_variable_name, concept_code, TextContent))

        return needed_inputs_for_factory

    @override
    def get_optional_pipe(self, pipe_code: str) -> Optional[PipeAbstract]:
        return self.root.get(pipe_code)

    @override
    def get_required_pipe(self, pipe_code: str) -> PipeAbstract:
        the_pipe = self.get_optional_pipe(pipe_code=pipe_code)
        if not the_pipe:
            raise PipeLibraryPipeNotFoundError(
                f"Pipe '{pipe_code}' not found. Check for typos and make sure it is declared in a library listed in the config."
            )
        return the_pipe

    @override
    def get_pipes(self) -> List[PipeAbstract]:
        return list(self.root.values())

    @override
    def get_pipes_dict(self) -> Dict[str, PipeAbstract]:
        return self.root

    @override
    def teardown(self) -> None:
        self.root = {}

    @override
    def pretty_list_pipes(self) -> None:
        def _format_concept_code(concept_code: Optional[str], current_domain: str) -> str:
            """Format concept code by removing domain prefix if it matches current domain."""
            if not concept_code:
                return ""
            parts = concept_code.split(".")
            if len(parts) == 2 and parts[0] == current_domain:
                return parts[1]
            return concept_code

        pipes = self.get_pipes()

        # Sort pipes by domain and code
        ordered_items = sorted(pipes, key=lambda x: (x.domain or "", x.code or ""))

        # Create dictionary for return value
        pipes_dict: Dict[str, Dict[str, Dict[str, str]]] = {}

        # Group by domain and create separate tables
        for domain, domain_pipes in groupby(ordered_items, key=lambda x: x.domain):
            table = Table(
                title=f"[bold magenta]domain = {domain}[/]",
                show_header=True,
                show_lines=True,
                header_style="bold cyan",
                box=box.SQUARE_DOUBLE_HEAD,
                border_style="blue",
            )

            table.add_column("Code", style="green")
            table.add_column("Definition", style="white")
            table.add_column("Input", style="yellow")
            table.add_column("Output", style="yellow")

            pipes_dict[domain] = {}

            for pipe in domain_pipes:
                inputs = pipe.inputs
                formatted_inputs = [f"{name}: {_format_concept_code(concept_code, domain)}" for name, concept_code in inputs.items]
                formatted_inputs_str = ", ".join(formatted_inputs)
                output_code = _format_concept_code(pipe.output_concept_code, domain)

                table.add_row(
                    pipe.code,
                    pipe.definition or "",
                    formatted_inputs_str,
                    output_code,
                )

                pipes_dict[domain][pipe.code] = {
                    "definition": pipe.definition or "",
                    "inputs": formatted_inputs_str,
                    "output": pipe.output_concept_code,
                }

            pretty_print(table)
