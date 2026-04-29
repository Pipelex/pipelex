"""Unit tests for line-length wrapping in StructureGenerator.

Generated structure files must stay under the project's ruff line-length limit
(150 chars). The generator handles this in two places:

- **Class docstrings**: emitted as a multi-line triple-quoted block when the
  single-line form would exceed the limit.
- **Field `description=` arguments**: emitted as a parenthesized
  implicit-string-concatenation block when the inline `description="..."` would
  exceed the limit.

For short descriptions, both fall back to the compact single-line form.
"""

from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.structure_generation.generator import StructureGenerator

_LINE_LIMIT = 150


def _max_line_length(code: str) -> int:
    return max((len(line) for line in code.splitlines()), default=0)


class TestStructureGeneratorWrapping:
    def test_short_class_docstring_stays_single_line(self):
        """A short class description fits on one line and is emitted compactly."""
        blueprint = {
            "name": ConceptStructureBlueprint(
                description="Name",
                type=ConceptStructureBlueprintFieldType.TEXT,
                required=True,
            ),
        }
        code, _ = StructureGenerator().generate_from_structure_blueprint(
            class_name="Person",
            structure_blueprint=blueprint,
            description="A person.",
        )
        assert '"""A person."""' in code
        assert _max_line_length(code) <= _LINE_LIMIT

    def test_long_class_docstring_wraps_to_multiline(self):
        """A long class description is split across multiple lines, each under the limit."""
        long_description = (
            "Specific output structure for this example's question — how many references in the report come from the "
            "report's own research center. Demonstrates how to output a typed structure tailored to the question rather "
            "than a free-form text answer."
        )
        blueprint = {
            "count": ConceptStructureBlueprint(
                description="Count",
                type=ConceptStructureBlueprintFieldType.INTEGER,
                required=True,
            ),
        }
        code, _ = StructureGenerator().generate_from_structure_blueprint(
            class_name="ReferenceCount",
            structure_blueprint=blueprint,
            description=long_description,
        )

        # Multi-line docstring form: opening """, body lines, closing """ on its own line.
        assert '    """\n' in code
        assert '\n    """' in code
        # Every emitted line stays under the limit.
        assert _max_line_length(code) <= _LINE_LIMIT
        # The full description content is preserved across the wrapped lines.
        # Fragments must fit within a single wrapped line (textwrap inserts \n at word boundaries).
        for fragment in ["Specific output structure", "research center", "free-form text"]:
            assert fragment in code

    def test_short_field_description_stays_single_line(self):
        """A short Field description uses the compact `description="..."` form."""
        blueprint = {
            "count": ConceptStructureBlueprint(
                description="The number of references coming from the report's own research center.",
                type=ConceptStructureBlueprintFieldType.INTEGER,
                required=True,
            ),
        }
        code, _ = StructureGenerator().generate_from_structure_blueprint(
            class_name="ReferenceCount",
            structure_blueprint=blueprint,
        )
        assert 'description="The number of references coming from the report\'s own research center."' in code
        assert "description=(" not in code
        assert _max_line_length(code) <= _LINE_LIMIT

    def test_long_field_description_wraps_to_implicit_concat(self):
        """A long Field description becomes a parenthesized implicit-string-concatenation block."""
        long_description = (
            "Whether a factual answer could in principle be derived from documents. False for counterfactual, opinion, "
            "and out_of_scope questions. This field is the central gate that prevents synthesis from forcing a question "
            "into an answerable type just to be helpful."
        )
        blueprint = {
            "is_answerable_from_documents": ConceptStructureBlueprint(
                description=long_description,
                type=ConceptStructureBlueprintFieldType.BOOLEAN,
                required=True,
            ),
        }
        code, _ = StructureGenerator().generate_from_structure_blueprint(
            class_name="QuestionAnalysis",
            structure_blueprint=blueprint,
        )

        # Parenthesized implicit-concat form was used.
        assert "description=(" in code
        # Every emitted line stays under the limit.
        assert _max_line_length(code) <= _LINE_LIMIT
        # Each fragment of the original description appears in the generated code
        # (each within a single chunk — fragments that span chunk boundaries would
        # be interrupted by the literal `" "` between adjacent string literals).
        for fragment in [
            "Whether a factual answer",
            "out_of_scope questions",
            "answerable type just to be helpful",
        ]:
            assert fragment in code

    def test_long_descriptions_in_long_class_produce_clean_output(self):
        """End-to-end: a class with a long docstring AND multiple long field descriptions
        still stays under the line limit on every emitted line.
        """
        long_class_doc = (
            "Structured understanding of the user's question: its type, whether it is answerable from documents at all, "
            "its decomposition into sub-questions, key entities to search for, alternative phrasings to boost retrieval "
            "recall, and any ambiguities that may block a confident answer."
        )
        blueprint = {
            "sub_questions": ConceptStructureBlueprint(
                description=(
                    "Decomposition of a compound question into independently-answerable sub-questions. For simple "
                    "questions, a single-item list containing the original question."
                ),
                type=ConceptStructureBlueprintFieldType.LIST,
                required=True,
            ),
            "reformulations": ConceptStructureBlueprint(
                description=(
                    "Alternative phrasings and synonyms for the question's key terms. Improves retrieval recall when "
                    "documents use different vocabulary."
                ),
                type=ConceptStructureBlueprintFieldType.LIST,
                required=True,
            ),
            "ambiguities": ConceptStructureBlueprint(
                description=(
                    "Aspects of the question that are ambiguous and may require clarification from the user. Empty "
                    "list if the question is fully specified."
                ),
                type=ConceptStructureBlueprintFieldType.LIST,
                required=False,
            ),
        }
        code, _ = StructureGenerator().generate_from_structure_blueprint(
            class_name="QuestionAnalysis",
            structure_blueprint=blueprint,
            description=long_class_doc,
        )
        assert _max_line_length(code) <= _LINE_LIMIT
