from itertools import groupby
from typing import Dict, List, Optional

from pydantic import RootModel
from rich import box
from rich.table import Table
from typing_extensions import override

from pipelex import pretty_print
from pipelex.core.pipe_abstract import PipeAbstract
from pipelex.core.pipe_provider_abstract import PipeProviderAbstract
from pipelex.exceptions import ConceptError, ConceptLibraryConceptNotFoundError, PipeLibraryError, PipeLibraryPipeNotFoundError
from pipelex.hub import get_concept_provider

PipeLibraryRoot = Dict[str, PipeAbstract]


class PipeLibrary(RootModel[PipeLibraryRoot], PipeProviderAbstract):
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

    @classmethod
    def make_empty(cls):
        return cls(root={})

    def add_new_pipe(self, pipe: PipeAbstract):
        name = pipe.code
        pipe.inputs.set_default_domain(domain=pipe.domain)
        if pipe.output_concept_code and "." not in pipe.output_concept_code:
            pipe.output_concept_code = f"{pipe.domain}.{pipe.output_concept_code}"
        if name in self.root:
            raise PipeLibraryError(f"Pipe '{name}' already exists in the library")
        self.root[pipe.code] = pipe

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
