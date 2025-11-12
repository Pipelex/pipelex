# from pipelex.libraries.library_manager_factory import LibraryManagerFactory
from rich import box
from rich.console import Console
from rich.table import Table

from pipelex.libraries.concept.concept_library import ConceptLibrary
from pipelex.libraries.pipe.pipe_library import PipeLibrary


def pretty_print_all_pipes(
    pipe_library: PipeLibrary,
    title: str | None = None,
):
    console = Console()
    table = Table(
        title=title,
        show_header=True,
        show_lines=True,
        header_style="bold cyan",
        box=box.SQUARE_DOUBLE_HEAD,
    )
    table.add_column("Domain")
    table.add_column("Code")
    table.add_column("Definition")
    table.add_column("Class")
    table.add_column("Input")
    table.add_column("Output")

    ordered_items = sorted(pipe_library.root.values(), key=lambda x: (x.domain, x.code))
    for pipe in ordered_items:
        table.add_row(
            pipe.domain,
            pipe.code,
            pipe.description,
            pipe.__class__.__name__,
            ", ".join([f"{name}: {concept_code}" for name, concept_code in pipe.inputs.items]),
            pipe.output.code,
        )

    console.print("\n")
    console.print(table)


def pretty_print_all_concepts(
    concept_library: ConceptLibrary,
    title: str | None = None,
):
    console = Console()
    table = Table(
        title=title,
        show_header=True,
        show_lines=True,
        header_style="bold cyan",
        box=box.SQUARE_DOUBLE_HEAD,
    )
    table.add_column("Domain")
    table.add_column("Code")
    table.add_column("Definition")
    table.add_column("Class")
    table.add_column("Inherits From")
    # make a list ordered by domain then code
    ordered_concepts = sorted(concept_library.root.values(), key=lambda x: (x.domain, x.code))
    for concept in ordered_concepts:
        table.add_row(
            concept.domain,
            concept.code,
            concept.description,
            concept.structure_class_name,
            concept.refines,
        )

    console.print("\n")
    console.print(table)
