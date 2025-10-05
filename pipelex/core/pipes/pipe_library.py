from itertools import groupby

from pydantic import RootModel
from rich import box
from rich.table import Table
from typing_extensions import override

from pipelex import pretty_print
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_library_abstract import PipeLibraryAbstract
from pipelex.exceptions import ConceptError, ConceptLibraryConceptNotFoundError, PipeLibraryError, PipeLibraryPipeNotFoundError
from pipelex.hub import get_concept_library
from pipelex.types import Self

PipeLibraryRoot = dict[str, PipeAbstract]


class PipeLibrary(RootModel[PipeLibraryRoot], PipeLibraryAbstract):
    @override
    def validate_with_libraries(self):
        concept_library = get_concept_library()
        for pipe in self.root.values():
            pipe.validate_output()
            try:
                for concept in pipe.concept_dependencies():
                    try:
                        concept_library.get_required_concept(concept_string=concept.concept_string)
                    except ConceptError as concept_error:
                        msg = f"Error validating pipe '{pipe.code}' dependency concept '{concept.concept_string}' because of: {concept_error}"
                        raise PipeLibraryError(msg) from concept_error
                for pipe_code in pipe.pipe_dependencies():
                    self.get_required_pipe(pipe_code=pipe_code)
                pipe.validate_with_libraries()
            except (ConceptLibraryConceptNotFoundError, PipeLibraryPipeNotFoundError) as not_found_error:
                msg = f"Missing dependency for pipe '{pipe.code}': {not_found_error}"
                raise PipeLibraryError(msg) from not_found_error

    @classmethod
    def make_empty(cls) -> Self:
        return cls(root={})

    @override
    def add_new_pipe(self, pipe: PipeAbstract):
        if pipe.code in self.root:
            msg = f"Pipe '{pipe.code}' already exists in the library"
            raise PipeLibraryError(msg)
        self.root[pipe.code] = pipe

    @override
    def add_pipes(self, pipes: list[PipeAbstract]):
        for pipe in pipes:
            self.add_new_pipe(pipe=pipe)

    @override
    def get_optional_pipe(self, pipe_code: str) -> PipeAbstract | None:
        return self.root.get(pipe_code)

    @override
    def get_required_pipe(self, pipe_code: str) -> PipeAbstract:
        the_pipe = self.get_optional_pipe(pipe_code=pipe_code)
        if not the_pipe:
            msg = f"Pipe '{pipe_code}' not found. Check for typos and make sure it is declared in a library listed in the config."
            raise PipeLibraryPipeNotFoundError(msg)
        return the_pipe

    @override
    def get_pipes(self) -> list[PipeAbstract]:
        return list(self.root.values())

    @override
    def get_pipes_dict(self) -> dict[str, PipeAbstract]:
        return self.root

    @override
    def remove_pipes_by_codes(self, pipe_codes: list[str]) -> None:
        # TODO: We should create a separate library, that copies the original one, and then removes the pipes from it
        # Then run the dry run + validation to see if removing those pipe has not broken any other pipe.
        # If validated, it should update the real library.
        for pipe_code in pipe_codes:
            if pipe_code in self.root:
                del self.root[pipe_code]

    @override
    def teardown(self) -> None:
        self.root = {}

    @override
    def pretty_list_pipes(self) -> None:
        def _format_concept_code(concept_code: str | None, current_domain: str) -> str:
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
        pipes_dict: dict[str, dict[str, dict[str, str]]] = {}

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
                    pipe.description or "",
                    formatted_inputs_str,
                    output_code,
                )

                pipes_dict[domain][pipe.code] = {
                    "description": pipe.description or "",
                    "inputs": formatted_inputs_str,
                    "output": pipe.output.code,
                }

            pretty_print(table)
