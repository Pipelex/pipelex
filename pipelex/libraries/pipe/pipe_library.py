from itertools import groupby
from typing import Self

from pydantic import RootModel
from rich import box
from rich.table import Table
from typing_extensions import override

from pipelex import pretty_print
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.libraries.pipe.exceptions import EntryPipeAmbiguousError, EntryPipeNotFoundError, PipeLibraryError, PipeNotFoundError
from pipelex.libraries.pipe.pipe_library_abstract import PipeLibraryAbstract
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract

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
        if pipe.pipe_ref in self.root:
            msg = (
                f"Pipe '{pipe.pipe_ref}' already exists in the library. "
                "It is likely declared in two different bundle files loaded into the same library. "
                "Check your library configuration: PIPELEXPATH environment variable, "
                "library_dirs passed to Pipelex.make(), or the --library-dir / -L CLI option."
            )
            raise PipeLibraryError(msg)
        self.root[pipe.pipe_ref] = pipe

    @override
    def add_pipes(self, pipes: list[PipeAbstract]):
        for pipe in pipes:
            self.add_new_pipe(pipe=pipe)

    @override
    def get_optional_pipe(self, pipe_code: str) -> PipeAbstract | None:
        """Resolve an **in-body** pipe reference: a ref names its own domain, or it names nothing.

        In-body refs arrive here already qualified — `crate_qualification.qualify_crate` runs on
        every crate-to-pipes path before pipes are built — so this is a key lookup. There is
        deliberately no bare-code search across domains: a reference that can find a pipe in a
        domain its author never named is a reference `[exports]` cannot constrain, and a visibility
        rule the resolver reaches around is not a visibility rule.

        A code a *human* typed is a different question and gets a different answer — see
        `get_optional_entry_pipe`.
        """
        # 1. Direct lookup — handles pipe_ref keys (domain.code) and cross-package keys (alias->domain.code)
        pipe = self.root.get(pipe_code)
        if pipe is not None:
            return pipe

        # 2. Cross-package refs. The bare-remainder search below survives the strictness change on
        # purpose (OQ3): the qualification pass leaves `alias->…` refs alone — it cannot know the
        # dependency's domain layout — so removing it would break every `alias->bare_code` ref with
        # no canonical spelling to migrate to. It is alias-scoped, so it cannot reach a host pipe;
        # revisit when the packaging design rules on cross-package reference forms.
        if QualifiedRef.has_cross_package_prefix(pipe_code):
            alias, remainder = QualifiedRef.split_cross_package_ref(pipe_code)
            # Try domain-qualified remainder as direct key
            aliased_key = f"{alias}->{remainder}"
            pipe = self.root.get(aliased_key)
            if pipe is not None:
                return pipe
            # Bare code remainder — search aliased entries matching the bare code
            if "." not in remainder:
                matches = [val for key, val in self.root.items() if key.startswith(f"{alias}->") and val.code == remainder]
                if len(matches) == 1:
                    return matches[0]
                if len(matches) > 1:
                    domains = [match.domain_code for match in matches]
                    msg = f"Ambiguous cross-package pipe code '{pipe_code}' found in domains: {domains}. Use domain-qualified ref."
                    raise PipeLibraryError(msg)
            return None

        return None

    @override
    def get_optional_entry_pipe(self, pipe_code: str) -> PipeAbstract | None:
        """Resolve a pipe code a **human** supplied — a CLI argument, an API request field.

        This is an entry-shaped lookup, not in-body reference resolution, and the two differ on
        purpose. `pipelex run summarize` should keep working without making the user recite a domain
        they can see in their own file, so a bare code here is matched across every domain the
        library holds. An ambiguous bare code raises rather than picking a winner.

        It deliberately does **not** consult `[exports]`. Package visibility governs what one method
        may reference from inside another; a pipe someone names by hand at an entry point is not an
        in-body reference, so the rule does not apply to it.

        Aliased dependency entries are excluded from the search. Without that, installing an
        unrelated package could make a host pipe's bare code ambiguous — reintroducing, through this
        door, exactly the contextual instability the strict in-body rule exists to remove.

        Every failure this door reports is the caller's own typo, so it is raised as an entry-shaped
        error carrying the INPUT domain — including the one detected one frame down, in the
        alias-scoped bare-remainder search inside `get_optional_pipe`, which is translated here. The
        in-body door keeps the unclassified errors: the same ambiguity read from inside a bundle is
        not a caller's input mistake.
        """
        try:
            pipe = self.get_optional_pipe(pipe_code=pipe_code)
        except PipeNotFoundError:
            # A miss is not an ambiguity. `get_optional_pipe` raises none today, but `PipeNotFoundError`
            # IS a `PipeLibraryError`, so without this arm a future one would be re-raised under a class
            # asserting the opposite — and handed a `user_action` naming candidates that never existed.
            raise
        except PipeLibraryError as exc:
            raise EntryPipeAmbiguousError(str(exc)) from exc
        if pipe is not None:
            return pipe

        # Anything dotted or aliased was fully specified and simply did not resolve; only a bare code
        # is a request to search.
        if "." in pipe_code or QualifiedRef.has_cross_package_prefix(pipe_code):
            return None

        matches = [val for key, val in self.root.items() if not QualifiedRef.has_cross_package_prefix(key) and val.code == pipe_code]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            candidates = sorted(match.pipe_ref for match in matches)
            msg = f"Pipe code '{pipe_code}' is ambiguous — it is declared by {candidates}. Name one of them explicitly, as 'domain.pipe_code'."
            raise EntryPipeAmbiguousError(msg)
        return None

    @override
    def get_required_entry_pipe(self, pipe_code: str) -> PipeAbstract:
        the_pipe = self.get_optional_entry_pipe(pipe_code=pipe_code)
        if not the_pipe:
            msg = (
                f"Pipe '{pipe_code}' could not be resolved. Check for typos and make sure its bundle is loaded. "
                "A bare code only matches this library's own domains — a pipe from a dependency package must be named 'alias->pipe_code'."
            )
            raise EntryPipeNotFoundError(msg)
        return the_pipe

    def add_dependency_pipe(self, *, alias: str, pipe: PipeAbstract) -> None:
        """Add a pipe from a dependency package with an aliased key.

        Args:
            alias: The dependency alias
            pipe: The pipe to add
        """
        key = f"{alias}->{pipe.pipe_ref}"
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
    def remove_pipes_by_refs(self, pipe_refs: list[str]) -> None:
        # TODO: We should create a separate library, that copies the original one, and then removes the pipes from it
        # Then run the dry run + validation to see if removing those pipe has not broken any other pipe.
        # If validated, it should update the real library.
        for pipe_ref in pipe_refs:
            if pipe_ref in self.root:
                del self.root[pipe_ref]

    @override
    def pretty_list_pipes(self) -> None:
        def _format_concept_code(concept_code: str | None, *, current_domain: str) -> str:
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
                formatted_inputs = [
                    f"{name}: {_format_concept_code(stuff_spec.concept.code, current_domain=domain_code)}" for name, stuff_spec in inputs.items
                ]
                formatted_inputs_str = ", ".join(formatted_inputs)
                output_code = _format_concept_code(pipe.output.concept.code, current_domain=domain_code)

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
