import inspect

import pytest

from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.structure_generation.generator import StructureGenerator
from tests.unit.pipelex.core.concepts.structure_generation.statement_probe import RUN_STATEMENT, STATEMENTS_RUN

_LONG_CLASS_DESCRIPTION = (
    "Specific output structure for this example's question — how many references in the report come from the "
    "report's own research center. Demonstrates how to output a typed structure tailored to the question rather "
    "than a free-form text answer."
)


@pytest.mark.usefixtures("clear_statements_run")
class TestStructureGeneratorLongDescriptions:
    def test_long_class_description_gains_no_line_break(self):
        """A long class description is the class's docstring and its schema description, with no break it never had."""
        blueprint = {"count": ConceptStructureBlueprint(description="Count", type=ConceptStructureBlueprintFieldType.INTEGER, required=True)}

        generated_class = StructureGenerator().generate_from_structure_blueprint(
            class_name="ReferenceCount", structure_blueprint=blueprint, description=_LONG_CLASS_DESCRIPTION
        )

        assert inspect.getdoc(generated_class) == _LONG_CLASS_DESCRIPTION
        assert generated_class.model_json_schema()["description"] == _LONG_CLASS_DESCRIPTION

    def test_long_class_description_with_triple_quotes_runs_no_statement(self):
        """A long description holding triple quotes and a statement is the docstring as written, and the statement never runs."""
        long_description = f'""";{RUN_STATEMENT};"""' + " padding" * 30

        generated_class = StructureGenerator().generate_from_structure_blueprint(
            class_name="Padded", structure_blueprint={}, description=long_description
        )

        assert STATEMENTS_RUN == []
        assert inspect.getdoc(generated_class) == long_description

    @pytest.mark.parametrize(
        "long_description",
        [
            pytest.param(
                "First paragraph of a long field description that runs past the wrapping width on its own line.\n\n"
                "Second paragraph:\n\t- a tabbed item   with a run of spaces\n  - an indented item\n" + "trailing words " * 12 + "  ",
                id="newlines-tabs-and-space-runs",
            ),
            pytest.param("x" * 200 + " " + "y" * 200, id="words-longer-than-a-line"),
            pytest.param(" " * 130 + "leading spaces then words " * 6, id="leading-spaces"),
            pytest.param('A "quoted" word, a \\ backslash and an apostrophe\'s mark. ' * 4, id="quotes-and-backslashes"),
            pytest.param(f'");{RUN_STATEMENT};("' * 3, id="a-statement-between-quotes"),
        ],
    )
    def test_long_field_description_reads_back_exactly(self, long_description: str):
        """A field description is the field's description and its schema description, character for character."""
        blueprint = {
            "notes": ConceptStructureBlueprint(description=long_description, type=ConceptStructureBlueprintFieldType.TEXT, required=True),
        }

        generated_class = StructureGenerator().generate_from_structure_blueprint(class_name="Annotated", structure_blueprint=blueprint)

        assert STATEMENTS_RUN == []
        assert generated_class.model_fields["notes"].description == long_description
        assert generated_class.model_json_schema()["properties"]["notes"]["description"] == long_description
