from itertools import groupby

from pydantic import RootModel
from rich import box
from rich.table import Table
from typing_extensions import override

from pipelex import pretty_print
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.qualified_ref import QualifiedRef, QualifiedRefError
from pipelex.libraries.pipe.exceptions import PipeLibraryError, PipeNotFoundError
from pipelex.libraries.pipe.pipe_library_abstract import PipeLibraryAbstract
from pipelex.types import Self

PipeLibraryRoot = dict[str, PipeAbstract]


class PipeLibrary(RootModel[PipeLibraryRoot], PipeLibraryAbstract):
    @override
    def setup(self):
        pass

    @override
    def teardown(self):
        self.root = {}

    @override
    def reset(self):
        self.teardown()
        self.setup()

    @classmethod
    def make_empty(cls) -> Self:
        library = cls(root=PipeLibraryRoot())
        library.setup()
        return library

    @override
    def add_new_pipe(self, pipe: PipeAbstract):
        if pipe.code in self.root:
            msg = (
                f"Pipe '{pipe.code}' already exists in the library. "
                "It is likely declared in two different bundle files loaded into the same library. "
                "Check your library configuration: PIPELEXPATH environment variable, "
                "library_dirs passed to Pipelex.make(), or the --library-dir / -L CLI option."
            )
            raise PipeLibraryError(msg)
        self.root[pipe.code] = pipe

    @override
    def add_pipes(self, pipes: list[PipeAbstract]):
        for pipe in pipes:
            self.add_new_pipe(pipe=pipe)

    @override
    def get_optional_pipe(self, pipe_code: str) -> PipeAbstract | None:
        # Direct lookup first (bare code or exact match)
        pipe = self.root.get(pipe_code)
        if pipe is not None:
            return pipe
        # Cross-package: "alias->domain.pipe_code" -> lookup "alias->pipe_code"
        if QualifiedRef.has_cross_package_prefix(pipe_code):
            alias, remainder = QualifiedRef.split_cross_package_ref(pipe_code)
            try:
                ref = QualifiedRef.parse(remainder)
            except QualifiedRefError:
                return None
            pipe = self.root.get(f"{alias}->{ref.local_code}")
            if pipe is not None and ref.is_qualified and pipe.domain_code != ref.domain_path:
                return None
            return pipe
        # If it's a domain-qualified ref (e.g. "scoring.compute_score"), try the local code
        if "." in pipe_code:
            try:
                ref = QualifiedRef.parse(pipe_code)
            except QualifiedRefError:
                return None
            pipe = self.root.get(ref.local_code)
            if pipe is not None and ref.is_qualified and pipe.domain_code != ref.domain_path:
                return None
            return pipe
        return None

    def add_dependency_pipe(self, alias: str, pipe: PipeAbstract) -> None:
        """Add a pipe from a dependency package with an aliased key.

        Args:
            alias: The dependency alias
            pipe: The pipe to add
        """
        key = f"{alias}->{pipe.code}"
        if key in self.root:
            msg = f"Dependency pipe '{key}' already exists in the library"
            raise PipeLibraryError(msg)
        self.root[key] = pipe

    @override
    def get_required_pipe(self, pipe_code: str) -> PipeAbstract:
        the_pipe = self.get_optional_pipe(pipe_code=pipe_code)
        if not the_pipe:
            msg = f"Pipe '{pipe_code}' not found. Check for typos and make sure it is declared in MTHDS file in an imported package."
            raise PipeNotFoundError(msg)
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
        ordered_items = sorted(pipes, key=lambda pipe: (pipe.domain_code or "", pipe.code or ""))

        # Create dictionary for return value
        pipes_dict: dict[str, dict[str, dict[str, str]]] = {}

        # Group by domain and create separate tables
        for domain_code, domain_pipes in groupby(ordered_items, key=lambda pipe: pipe.domain_code):
            table = Table(
                title=f"[bold magenta]domain = {domain_code}[/]",
                show_header=True,
                show_lines=True,
                header_style="bold cyan",
                box=box.SQUARE_DOUBLE_HEAD,
                border_style="blue",
            )

            table.add_column("Code", style="green")
            table.add_column("Type", style="cyan")
            table.add_column("Definition", style="white")
            table.add_column("Input", style="yellow")
            table.add_column("Output", style="yellow")

            pipes_dict[domain_code] = {}

            for pipe in domain_pipes:
                inputs = pipe.inputs
                formatted_inputs = [f"{name}: {_format_concept_code(stuff_spec.concept.code, domain_code)}" for name, stuff_spec in inputs.items]
                formatted_inputs_str = ", ".join(formatted_inputs)
                output_code = _format_concept_code(pipe.output.concept.code, domain_code)

                table.add_row(
                    pipe.code,
                    pipe.type,
                    pipe.description or "",
                    formatted_inputs_str,
                    output_code,
                )

                pipes_dict[domain_code][pipe.code] = {
                    "description": pipe.description or "",
                    "inputs": formatted_inputs_str,
                    "output": pipe.output.concept.code,
                }

            pretty_print(table)
