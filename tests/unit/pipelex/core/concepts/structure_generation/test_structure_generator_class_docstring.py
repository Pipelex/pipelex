"""How a class description renders as the docstring of a generated structure class.

Whatever characters the description holds, the docstring reads back as authored and the generated module runs no
statement the description spells.
"""

import inspect

import pytest

from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.structure_generation.generator import StructureGenerator
from pipelex.tools.misc.python_literals import normalized_docstring_text
from tests.unit.pipelex.core.concepts.structure_generation.statement_probe import RUN_STATEMENT, STATEMENTS_RUN

# Padding that takes a description past the length at which the generator used to wrap its docstring.
_PADDING = " padding" * 30

# A long description of ordinary words, with a single space between each.
_LONG_DESCRIPTION = " ".join(["A long description that runs well past the old wrapping width."] * 5)


@pytest.mark.usefixtures("clear_statements_run")
class TestStructureGeneratorClassDocstringEscaping:
    """A class description renders as a docstring that reads back as authored, whatever characters it holds."""

    @pytest.mark.parametrize(
        ("description", "with_field"),
        [
            pytest.param(f'"""\n{RUN_STATEMENT}\n_ = """', False, id="triple-quotes-across-lines"),
            pytest.param(f'""";{RUN_STATEMENT};"""{_PADDING}', False, id="triple-quotes-in-a-long-description"),
            pytest.param(f'""";{RUN_STATEMENT};"""{_PADDING}', True, id="triple-quotes-in-a-long-description-with-a-field"),
            pytest.param(f"Both \"\"\" and ''' delimiters;{RUN_STATEMENT};'''", False, id="both-triple-quote-styles"),
            pytest.param('Ends with a double quote: "quoted"', False, id="trailing-double-quote"),
            pytest.param("Ends with a single quote: 'quoted'", False, id="trailing-single-quote"),
            pytest.param("Ends with a backslash \\", False, id="trailing-backslash"),
            pytest.param("A Windows path C:\\new\\table and a lone \\ in the middle", False, id="backslashes-mid-text"),
            pytest.param("A bell \x07 and a NUL \x00 inside", False, id="control-character-and-nul"),
            pytest.param("Summary line.\n\nSecond paragraph with a list:\n  - first item\n  - second item", False, id="multi-line"),
            pytest.param(_LONG_DESCRIPTION, True, id="longer-than-a-line"),
            pytest.param("\n    Indented first line after a blank one\n  and a shallower line", False, id="blank-first-line-then-indented"),
        ],
    )
    def test_class_description_renders_verbatim_and_runs_no_statement(self, description: str, with_field: bool):
        """A description containing triple quotes, backslashes or control characters renders verbatim and runs no statement."""
        blueprint = (
            {"value": ConceptStructureBlueprint(type=ConceptStructureBlueprintFieldType.TEXT, description="A value", required=True)}
            if with_field
            else {}
        )

        _, generated_class = StructureGenerator().generate_from_structure_blueprint(
            class_name="Described", structure_blueprint=blueprint, description=description
        )

        assert STATEMENTS_RUN == []
        assert inspect.getdoc(generated_class) == normalized_docstring_text(description)

    def test_indented_body_after_a_blank_first_line_keeps_its_relative_indentation(self):
        """A description that opens on a blank line and indents its whole body reads back as `inspect.cleandoc` leaves it."""
        description = "\n  Intro:\n    - item one\n    - item two"

        _, generated_class = StructureGenerator().generate_from_structure_blueprint(
            class_name="Described", structure_blueprint={}, description=description
        )

        assert inspect.getdoc(generated_class) == "Intro:\n  - item one\n  - item two"
        assert generated_class.model_json_schema()["description"] == "Intro:\n  - item one\n  - item two"  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    def test_long_class_description_gains_no_line_break(self):
        """A one-line description longer than any line limit stays one line: no newline the author did not write."""
        _, generated_class = StructureGenerator().generate_from_structure_blueprint(
            class_name="Described", structure_blueprint={}, description=_LONG_DESCRIPTION
        )

        assert inspect.getdoc(generated_class) == _LONG_DESCRIPTION
        assert generated_class.model_json_schema()["description"] == _LONG_DESCRIPTION  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
