import json
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.pipes.output.output_renderer import render_output

GET_REQUIRED_PIPE_TARGET = "pipelex.core.pipes.output.output_renderer.get_required_pipe"


def _make_anything_condition_pipe(mocker: MockerFixture, mapped_pipe_code: str) -> Any:
    condition_pipe = mocker.MagicMock()
    condition_pipe.type = "PipeCondition"
    condition_pipe.is_signature = False
    condition_pipe.output.concept.code = "Anything"
    condition_pipe.pipe_dependencies.return_value = {mapped_pipe_code}
    return condition_pipe


def _make_mapped_pipe(mocker: MockerFixture, concept_ref: str, rendered: dict[str, Any]) -> Any:
    mapped_pipe = mocker.MagicMock()
    mapped_pipe.is_signature = False
    mapped_pipe.output.concept.concept_ref = concept_ref
    mapped_pipe.output.render_stuff_spec.return_value = rendered
    return mapped_pipe


class TestRenderOutputAnythingFormats:
    @pytest.mark.parametrize(
        "output_format",
        [
            ConceptRepresentationFormat.JSON,
            ConceptRepresentationFormat.PYTHON,
            ConceptRepresentationFormat.SCHEMA,
        ],
    )
    def test_anything_without_possible_outputs_raises(self, mocker: MockerFixture, output_format: ConceptRepresentationFormat) -> None:
        """An Anything output with no determinable possible outputs raises a ValueError naming native.Anything."""
        anything_pipe = mocker.MagicMock()
        anything_pipe.type = "PipeLLM"
        anything_pipe.is_signature = False
        anything_pipe.output.concept.code = "Anything"

        with pytest.raises(ValueError, match=r"native\.Anything"):
            render_output(anything_pipe, output_format=output_format)

    def test_anything_json_renders_output_options(self, mocker: MockerFixture) -> None:
        """JSON format wraps each possible output under an output_option_N key with concept and content."""
        condition_pipe = _make_anything_condition_pipe(mocker, "make_summary")
        mapped_pipe = _make_mapped_pipe(
            mocker,
            "test.Summary",
            rendered={"concept": "test.Summary", "content": {"text": "summary text"}},
        )
        mocker.patch(GET_REQUIRED_PIPE_TARGET, return_value=mapped_pipe)

        result = render_output(condition_pipe, output_format=ConceptRepresentationFormat.JSON)

        parsed = json.loads(result)
        assert parsed == {
            "output_option_1": {
                "concept": "test.Summary",
                "content": {"text": "summary text"},
            }
        }
        mapped_pipe.output.render_stuff_spec.assert_called_once_with(ConceptRepresentationFormat.JSON)

    def test_anything_python_renders_option_lines(self, mocker: MockerFixture) -> None:
        """PYTHON format lists each possible output as a commented option with an output_N assignment."""
        condition_pipe = _make_anything_condition_pipe(mocker, "make_summary")
        mapped_pipe = _make_mapped_pipe(
            mocker,
            "test.Summary",
            rendered={"concept": "test.Summary", "content": 'SummaryContent(text="hello")'},
        )
        mocker.patch(GET_REQUIRED_PIPE_TARGET, return_value=mapped_pipe)

        result = render_output(condition_pipe, output_format=ConceptRepresentationFormat.PYTHON)

        result_lines = result.splitlines()
        assert result_lines[0] == "# Multiple possible output types"
        assert result_lines[1] == "# The actual output will be one of the following:"
        assert "# Option 1: test.Summary" in result_lines
        assert 'output_1 = SummaryContent(text="hello")' in result_lines
        mapped_pipe.output.render_stuff_spec.assert_called_once_with(ConceptRepresentationFormat.PYTHON)

    def test_anything_schema_renders_schema_options(self, mocker: MockerFixture) -> None:
        """SCHEMA format wraps each possible output under a schema_option_N key with concept and content."""
        condition_pipe = _make_anything_condition_pipe(mocker, "build_schema")
        schema_content = {"type": "object", "properties": {"text": {"type": "string"}}}
        mapped_pipe = _make_mapped_pipe(
            mocker,
            "test.Schema",
            rendered={"concept": "test.Schema", "content": schema_content},
        )
        mocker.patch(GET_REQUIRED_PIPE_TARGET, return_value=mapped_pipe)

        result = render_output(condition_pipe, output_format=ConceptRepresentationFormat.SCHEMA)

        parsed = json.loads(result)
        assert parsed == {
            "schema_option_1": {
                "concept": "test.Schema",
                "content": schema_content,
            }
        }
        mapped_pipe.output.render_stuff_spec.assert_called_once_with(ConceptRepresentationFormat.SCHEMA)
