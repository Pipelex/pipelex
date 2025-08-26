from itertools import groupby
from typing import Dict, List, Optional

from pydantic import RootModel
from rich import box
from rich.table import Table
from typing_extensions import override

from pipelex import pretty_print
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_provider_abstract import PipeProviderAbstract
from pipelex.exceptions import ConceptError, ConceptLibraryConceptNotFoundError, PipeLibraryError, PipeLibraryPipeNotFoundError
from pipelex.hub import get_concept_provider

PipeLibraryRoot = Dict[str, PipeAbstract]


class PipeLibrary(RootModel[PipeLibraryRoot], PipeProviderAbstract):
    @override
    def validate_with_libraries(self):
        concept_provider = get_concept_provider()
        for pipe in self.root.values():
            pipe.validate_output()
            try:
                for concept in pipe.concept_dependencies():
                    try:
                        concept_provider.get_required_concept(concept_string=concept.concept_string)
                    except ConceptError as concept_error:
                        raise PipeLibraryError(
                            f"Error validating pipe '{pipe.code}' dependency concept '{concept.concept_string}' because of: {concept_error}"
                        ) from concept_error
                for pipe_code in pipe.pipe_dependencies():
                    self.get_required_pipe(pipe_code=pipe_code)
                pipe.validate_with_libraries()
            except (ConceptLibraryConceptNotFoundError, PipeLibraryPipeNotFoundError) as not_found_error:
                raise PipeLibraryError(f"Missing dependency for pipe '{pipe.code}': {not_found_error}") from not_found_error

    @classmethod
    def make_empty(cls):
        return cls(root={})

    @override
    def add_new_pipe(self, pipe: PipeAbstract):
        if pipe.code in self.root:
            raise PipeLibraryError(f"Pipe '{pipe.code}' already exists in the library")
        self.root[pipe.code] = pipe

    @override
    def add_pipes(self, pipes: List[PipeAbstract]):
        for pipe in pipes:
            self.add_new_pipe(pipe=pipe)

    def add_or_update_pipe(self, pipe: PipeAbstract):
        name = pipe.code
        pipe.inputs.set_default_domain(domain=pipe.domain)
        if pipe.output.code and "." not in pipe.output.code:
            pipe.output.code = f"{pipe.domain}.{pipe.output.code}"
        self.root[name] = pipe

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
        ordered_items = sorted(pipes, key=lambda pipe: (pipe.domain or "", pipe.code or ""))

        # Create dictionary for return value
        pipes_dict: Dict[str, Dict[str, Dict[str, str]]] = {}

        # Group by domain and create separate tables
        for domain, domain_pipes in groupby(ordered_items, key=lambda pipe: pipe.domain):
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
                formatted_inputs = [f"{name}: {_format_concept_code(requirement.concept.code, domain)}" for name, requirement in inputs.items]
                formatted_inputs_str = ", ".join(formatted_inputs)
                output_code = _format_concept_code(pipe.output.code, domain)

                table.add_row(
                    pipe.code,
                    pipe.definition or "",
                    formatted_inputs_str,
                    output_code,
                )

                pipes_dict[domain][pipe.code] = {
                    "definition": pipe.definition or "",
                    "inputs": formatted_inputs_str,
                    "output": pipe.output.code,
                }

            pretty_print(table)
