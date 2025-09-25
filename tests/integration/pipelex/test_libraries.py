"""make t TEST=TestLibraries
"""

from pathlib import Path

import pytest
from rich import box
from rich.console import Console
from rich.table import Table

from pipelex import pretty_print
from pipelex.config import get_config
from pipelex.core.concepts.concept_library import ConceptLibrary
from pipelex.core.pipes.pipe_library import PipeLibrary
from pipelex.libraries.library_manager_factory import LibraryManagerFactory
from tests.integration.pipelex.test_data import LibraryTestCases


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
            pipe.definition,
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
            concept.definition,
            concept.structure_class_name,
            concept.refines,
        )

    console.print("\n")
    console.print(table)


class TestLibraries:
    @pytest.mark.parametrize("known_concept, known_pipe", LibraryTestCases.KNOWN_CONCEPTS_AND_PIPES)
    def test_load_combo_libraries(
        self,
        known_concept: str,
        known_pipe: str,
    ):
        library_manager = LibraryManagerFactory.make_empty(config_dir_path="pipelex/libraries")
        test_pipelines_dir = [Path(get_config().pipelex.library_config.test_pipelines_dir_path)]
        library_manager.load_libraries(library_dirs=test_pipelines_dir)
        # Verify that libraries were loaded
        assert len(library_manager.concept_library.root) > 0, "No concepts were loaded"
        assert len(library_manager.pipe_library.root) > 0, "No pipes were loaded"

        # Test individual concepts and pipes
        assert library_manager.concept_library.get_required_concept(concept_string=known_concept) is not None
        pretty_print(
            f"Concept: {known_concept} is correctly loaded as {library_manager.concept_library.get_required_concept(concept_string=known_concept)}",
        )
        assert library_manager.pipe_library.get_optional_pipe(known_pipe) is not None
        pretty_print(f"Pipe: {known_pipe} is correctly loaded as {library_manager.pipe_library.get_optional_pipe(known_pipe)}")
