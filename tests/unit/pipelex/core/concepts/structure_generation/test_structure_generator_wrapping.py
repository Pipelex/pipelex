"""Unit tests for line-length handling in StructureGenerator.

Generated structure files keep their code lines under the project's ruff line-length
limit (150 chars), with one deliberate exception:

- **Class docstrings** are never wrapped. A docstring is the class description that
  pydantic hands to the JSON schema, so a line break the generator added would become
  part of the text every consumer reads. A long description stays on one line.
- **Field `description=` arguments**: emitted as a parenthesized
  implicit-string-concatenation block when the inline `description="..."` would
  exceed the limit; the concatenation leaves the string's value untouched.

For short descriptions, both use the compact single-line form.
"""

import inspect
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from pathlib import Path

import pytest

from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.structure_generation.generator import StructureGenerator

_LINE_LIMIT = 150

# A rendering that let a statement run would append to this list, which the statement reaches through `sys.modules`.
STATEMENTS_RUN: list[str] = []


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

    def test_long_class_docstring_stays_one_line(self):
        """A long class description is emitted on one line, so the class reads it back without a break it never had."""
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
        code, generated_class = StructureGenerator().generate_from_structure_blueprint(
            class_name="ReferenceCount",
            structure_blueprint=blueprint,
            description=long_description,
        )

        assert f'    """{long_description}"""' in code
        assert inspect.getdoc(generated_class) == long_description
        assert generated_class.model_json_schema()["description"] == long_description  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    def test_long_class_docstring_with_triple_quotes_runs_no_statement(self):
        """A long description containing triple quotes and no space to break at renders verbatim and runs no statement."""
        statement = f'__import__("sys").modules["{__name__}"].STATEMENTS_RUN.append("ran")'
        long_description = f'""";{statement};"""' + " padding" * 30
        STATEMENTS_RUN.clear()

        _, generated_class = StructureGenerator().generate_from_structure_blueprint(
            class_name="Padded",
            structure_blueprint={},
            description=long_description,
        )

        assert STATEMENTS_RUN == []
        assert inspect.getdoc(generated_class) == long_description

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

    @pytest.mark.parametrize(
        "long_description",
        [
            pytest.param(
                "First paragraph of a long field description that runs past the wrapping width on its own line.\n\n"
                "Second paragraph:\n\t- a tabbed item   with a run of spaces\n  - an indented item\n" + "trailing words " * 12 + "  ",
                id="newlines-tabs-and-space-runs",
            ),
            pytest.param("x" * 200 + " " + "y" * 200, id="words-longer-than-the-width"),
            pytest.param(" " * 130 + "leading spaces then words " * 6, id="leading-spaces"),
            pytest.param('A "quoted" word, a \\ backslash and an apostrophe\'s mark. ' * 4, id="quotes-and-backslashes"),
        ],
    )
    def test_long_field_description_reads_back_exactly(self, long_description: str):
        """However the generator splits a long field description into literals, their concatenation is the authored text."""
        blueprint = {
            "notes": ConceptStructureBlueprint(description=long_description, type=ConceptStructureBlueprintFieldType.TEXT, required=True),
        }
        code, generated_class = StructureGenerator().generate_from_structure_blueprint(class_name="Annotated", structure_blueprint=blueprint)

        assert generated_class.model_fields["notes"].description == long_description  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
        assert generated_class.model_json_schema()["properties"]["notes"]["description"] == long_description  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
        assert _max_line_length(code.replace("x" * 200, "").replace("y" * 200, "")) <= _LINE_LIMIT

    def test_long_field_description_survives_ruff_format(self, tmp_path: Path):
        """Generated multi-line description blocks must survive `ruff format` without
        the chunks being collapsed back into a single line. Un-indented chunks under a
        hanging-indent paren block get joined by ruff format, defeating the wrap.
        """
        try:
            subprocess.run([sys.executable, "-m", "ruff", "--version"], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            pytest.skip("ruff not available in current interpreter")

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

        target = tmp_path / "generated.py"
        target.write_text(code)
        # Use --isolated so ruff ignores any pyproject.toml in the path above tmp_path,
        # and run via the current interpreter to ensure we use the project's pinned ruff.
        subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            [sys.executable, "-m", "ruff", "format", "--isolated", str(target)],
            check=True,
            capture_output=True,
        )
        formatted = target.read_text()

        # The implicit-string-concat must still be present after formatting — i.e. ruff
        # didn't merge the chunks. We check by counting string literal lines inside the
        # description block.
        assert "description=(" in formatted
        # At least two string-literal lines remain inside the description block.
        in_block = False
        literal_lines = 0
        for line in formatted.splitlines():
            stripped = line.strip()
            if "description=(" in stripped:
                in_block = True
                continue
            if in_block:
                if stripped.startswith((")", "),")):
                    break
                if stripped.startswith('"'):
                    literal_lines += 1
        assert literal_lines >= 2, f"ruff format collapsed the description chunks; got {literal_lines} literal line(s)"
        assert _max_line_length(formatted) <= _LINE_LIMIT

    def test_long_descriptions_in_long_class_produce_clean_output(self):
        """End-to-end: a class with a long docstring AND multiple long field descriptions
        keeps every code line under the limit, the one-line docstring aside.
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
        code, generated_class = StructureGenerator().generate_from_structure_blueprint(
            class_name="QuestionAnalysis",
            structure_blueprint=blueprint,
            description=long_class_doc,
        )
        # The class docstring is the one line allowed past the limit, and it reads back as authored.
        docstring_line = f'    """{long_class_doc}"""'
        assert docstring_line in code.splitlines()
        assert _max_line_length(code.replace(docstring_line, "")) <= _LINE_LIMIT
        assert inspect.getdoc(generated_class) == long_class_doc
