"""Unit tests for output_renderer module.

Tests the render_output function to ensure it generates proper output representations
in JSON, Python, and Schema formats.
"""

import json

import pytest
from kajson.kajson_manager import KajsonManager
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_machinery.rendering.output_renderer import render_output


@pytest.fixture(autouse=True)
def register_image_content() -> None:
    """Register ImageContent with the class registry."""
    KajsonManager.get_class_registry().register_class(ImageContent)


def _make_image_concept() -> Concept:
    """Create an Image concept for testing."""
    return Concept(
        code="Image",
        domain_code="native",
        description="An image",
        structure_class_name="ImageContent",
    )


class TestRenderOutputPythonFormat:
    """Tests for render_output with PYTHON format.

    The Python format should return executable Python code, not JSON containing
    Python code strings.
    """

    def test_python_format_returns_python_code_not_json(self, mocker: MockerFixture) -> None:
        """Python format should return actual Python code, not JSON with Python strings."""
        # Create a mock pipe with Image output
        mock_pipe = mocker.MagicMock(spec=PipeAbstract)
        mock_pipe.type = "PipeLLM"

        # Create a real Concept for Image
        image_concept = _make_image_concept()

        # Create a StuffSpec for the output
        mock_output = StuffSpec(concept=image_concept, multiplicity=None)
        mock_pipe.output = mock_output

        # Render the output with Python format
        result = render_output(mock_pipe, output_format=ConceptRepresentationFormat.PYTHON)

        # The bug: render_output returns JSON even for Python format
        # The result should NOT be valid JSON when format is PYTHON
        is_json = False
        try:
            json.loads(result)
            is_json = True
        except json.JSONDecodeError:
            is_json = False

        # This assertion SHOULD PASS (result should not be JSON)
        # but currently FAILS due to the bug
        assert not is_json, f"Python format should return Python code, not JSON. Got: {result}"

    def test_python_format_contains_python_instantiation(self, mocker: MockerFixture) -> None:
        """Python format output should contain Python class instantiation syntax."""
        # Create a mock pipe with Image output
        mock_pipe = mocker.MagicMock(spec=PipeAbstract)
        mock_pipe.type = "PipeLLM"

        # Create a real Concept for Image
        image_concept = _make_image_concept()

        # Create a StuffSpec for the output
        mock_output = StuffSpec(concept=image_concept, multiplicity=None)
        mock_pipe.output = mock_output

        # Render the output with Python format
        result = render_output(mock_pipe, output_format=ConceptRepresentationFormat.PYTHON)

        # The output should contain "ImageContent(" as a Python instantiation
        # NOT as a JSON string value
        assert "ImageContent(" in result, f"Expected Python instantiation syntax. Got: {result}"

        # When the bug is fixed, the result should look like:
        # output = ImageContent(url="url_value")
        # not like:
        # {"concept": "native.Image", "content": "ImageContent(url=\"url_value\")"}


class TestRenderOutputJsonFormat:
    """Tests for render_output with JSON format."""

    def test_json_format_returns_valid_json(self, mocker: MockerFixture) -> None:
        """JSON format should return valid JSON."""
        # Create a mock pipe with Image output
        mock_pipe = mocker.MagicMock(spec=PipeAbstract)
        mock_pipe.type = "PipeLLM"

        # Create a real Concept for Image
        image_concept = _make_image_concept()

        # Create a StuffSpec for the output
        mock_output = StuffSpec(concept=image_concept, multiplicity=None)
        mock_pipe.output = mock_output

        # Render the output with JSON format
        result = render_output(mock_pipe, output_format=ConceptRepresentationFormat.JSON)

        # Should be valid JSON
        parsed = json.loads(result)
        assert "concept" in parsed
        assert "content" in parsed
        assert parsed["concept"] == "native.Image"
        assert "url" in parsed["content"]


class TestRenderOutputSchemaFormat:
    """Tests for render_output with SCHEMA format."""

    def test_schema_format_returns_json_schema(self, mocker: MockerFixture) -> None:
        """Schema format should return a JSON schema definition."""
        # Create a mock pipe with Image output
        mock_pipe = mocker.MagicMock(spec=PipeAbstract)
        mock_pipe.type = "PipeLLM"

        # Create a real Concept for Image
        image_concept = _make_image_concept()

        # Create a StuffSpec for the output
        mock_output = StuffSpec(concept=image_concept, multiplicity=None)
        mock_pipe.output = mock_output

        # Render the output with Schema format
        result = render_output(mock_pipe, output_format=ConceptRepresentationFormat.SCHEMA)

        # Should be valid JSON
        parsed = json.loads(result)
        assert "concept" in parsed
        assert "content" in parsed
        # Schema should contain JSON Schema keywords
        assert "type" in parsed["content"] or "properties" in parsed["content"]
