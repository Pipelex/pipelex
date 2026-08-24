"""Unit tests for runner_code module."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

import pytest

from pipelex.builder.runner_code import generate_runner_code
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.libraries.concept.concept_library import ConceptLibrary

if TYPE_CHECKING:
    from pytest_mock import MockerFixture, MockType


class TestConceptGenerateInputRepresentationJson:
    """Test Concept.render_concept_representation for JSON format."""

    def test_native_text_json(self) -> None:
        """Test JSON representation for native Text concept."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.TEXT)
        result, _ = concept.render_concept_representation(
            structure_class=ConceptLibrary.make_empty().get_structure_class(concept=concept), output_format=ConceptRepresentationFormat.JSON
        )
        assert result["concept"] == "native.Text"
        assert "content" in result
        assert "text" in result["content"]

    def test_native_image_json(self) -> None:
        """Test JSON representation for native Image concept."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.IMAGE)
        result, _ = concept.render_concept_representation(
            structure_class=ConceptLibrary.make_empty().get_structure_class(concept=concept), output_format=ConceptRepresentationFormat.JSON
        )
        assert result["concept"] == "native.Image"
        assert "content" in result
        assert "url" in result["content"]

    def test_native_number_json(self) -> None:
        """Test JSON representation for native Number concept."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.NUMBER)
        result, _ = concept.render_concept_representation(
            structure_class=ConceptLibrary.make_empty().get_structure_class(concept=concept), output_format=ConceptRepresentationFormat.JSON
        )
        assert result["concept"] == "native.Number"
        assert "content" in result
        assert "number" in result["content"]

    def test_native_document_json_with_multiplicity(self) -> None:
        """Test JSON representation for Document with multiplicity - content should be a list."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.DOCUMENT)
        result, _ = concept.render_concept_representation(
            structure_class=ConceptLibrary.make_empty().get_structure_class(concept=concept),
            output_format=ConceptRepresentationFormat.JSON,
            multiplicity=True,
        )
        assert result["concept"] == "native.Document"
        assert "content" in result
        # Content should be a list
        content = cast("list[dict[str, Any]]", result["content"])
        assert isinstance(content, list)
        assert len(content) == 1
        assert "url" in content[0]


class TestConceptGenerateInputRepresentationPython:
    """Test Concept.render_concept_representation for Python format."""

    def test_native_text_python(self) -> None:
        """Test Python representation for native Text concept."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.TEXT)
        result, imports = concept.render_concept_representation(
            structure_class=ConceptLibrary.make_empty().get_structure_class(concept=concept), output_format=ConceptRepresentationFormat.PYTHON
        )
        assert result["concept"] == "native.Text"
        assert "TextContent" in result["content"]
        assert "TextContent" in imports

    def test_native_image_python(self) -> None:
        """Test Python representation for native Image concept."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.IMAGE)
        result, imports = concept.render_concept_representation(
            structure_class=ConceptLibrary.make_empty().get_structure_class(concept=concept), output_format=ConceptRepresentationFormat.PYTHON
        )
        assert result["concept"] == "native.Image"
        assert "ImageContent" in result["content"]
        assert "ImageContent" in imports

    def test_refined_text_python(self) -> None:
        """Test Python representation for a concept that refines Text."""
        concept = ConceptFactory.make(
            domain_code="test_domain",
            concept_code="Question",
            description="A question",
            structure_class_name="TextContent",
            refines="native.Text",
        )
        result, imports = concept.render_concept_representation(
            structure_class=ConceptLibrary.make_empty().get_structure_class(concept=concept), output_format=ConceptRepresentationFormat.PYTHON
        )
        assert result["concept"] == "test_domain.Question"
        assert "TextContent" in result["content"]
        assert "TextContent" in imports

    def test_native_document_python_with_multiplicity(self) -> None:
        """Test Python representation for Document with multiplicity - for Python format, wrapping is handled by caller."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.DOCUMENT)
        result, imports = concept.render_concept_representation(
            structure_class=ConceptLibrary.make_empty().get_structure_class(concept=concept),
            output_format=ConceptRepresentationFormat.PYTHON,
            multiplicity=True,
        )
        # For Python format, a multiple multiplicity doesn't wrap content (caller handles it)
        assert result["concept"] == "native.Document"
        assert "DocumentContent" in result["content"]
        assert "DocumentContent" in imports


class TestInputStuffSpecsRenderInputsRepresentation:
    """Test InputStuffSpecs.render_inputs method."""

    def test_empty_inputs(self) -> None:
        """Test JSON generation with no inputs."""
        inputs = InputStuffSpecs(root={})
        result = json.loads(inputs.render_inputs(concept_provider=ConceptLibrary.make_empty()))
        assert result == {}

    def test_single_input(self) -> None:
        """Test JSON generation with a single input."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.TEXT)
        inputs = InputStuffSpecs(root={"message": StuffSpec(concept=concept)})
        result = json.loads(inputs.render_inputs(concept_provider=ConceptLibrary.make_empty()))
        assert "message" in result
        assert result["message"]["concept"] == "native.Text"

    def test_multiple_inputs(self) -> None:
        """Test JSON generation with multiple inputs."""
        text_concept = ConceptFactory.make_native_concept(NativeConceptCode.TEXT)
        image_concept = ConceptFactory.make_native_concept(NativeConceptCode.IMAGE)
        inputs = InputStuffSpecs(
            root={
                "text_input": StuffSpec(concept=text_concept),
                "image_input": StuffSpec(concept=image_concept),
            }
        )
        result = json.loads(inputs.render_inputs(concept_provider=ConceptLibrary.make_empty()))
        assert "text_input" in result
        assert "image_input" in result
        assert result["text_input"]["concept"] == "native.Text"
        assert result["image_input"]["concept"] == "native.Image"


class TestInputStuffSpecsRenderWithMultiplicity:
    """Test InputStuffSpecs.render_inputs with multiplicity - content is wrapped in list."""

    def test_single_item_no_multiplicity(self) -> None:
        """Test that single item (no multiplicity) has content as dict, not list."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.DOCUMENT)
        inputs = InputStuffSpecs(root={"document": StuffSpec(concept=concept, multiplicity=None)})
        result = json.loads(inputs.render_inputs(concept_provider=ConceptLibrary.make_empty()))
        assert "document" in result
        # concept should be present
        assert result["document"]["concept"] == "native.Document"
        # content should NOT be a list
        content = result["document"]["content"]
        assert isinstance(content, dict)
        assert "url" in content

    def test_multiple_items_true_multiplicity(self) -> None:
        """Test that multiplicity=True wraps content in list."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.DOCUMENT)
        inputs = InputStuffSpecs(root={"documents": StuffSpec(concept=concept, multiplicity=True)})
        result = json.loads(inputs.render_inputs(concept_provider=ConceptLibrary.make_empty()))
        assert "documents" in result
        # concept should be at the top level
        assert result["documents"]["concept"] == "native.Document"
        # content should be a list
        content = cast("list[dict[str, Any]]", result["documents"]["content"])
        assert isinstance(content, list)
        assert len(content) == 1
        assert "url" in content[0]

    def test_multiple_items_int_multiplicity(self) -> None:
        """Test that multiplicity=N (int > 1) wraps content in list."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.IMAGE)
        inputs = InputStuffSpecs(root={"images": StuffSpec(concept=concept, multiplicity=3)})
        result = json.loads(inputs.render_inputs(concept_provider=ConceptLibrary.make_empty()))
        assert "images" in result
        # concept should be at the top level
        assert result["images"]["concept"] == "native.Image"
        # content should be a list
        content = cast("list[dict[str, Any]]", result["images"]["content"])
        assert isinstance(content, list)
        assert len(content) == 1
        assert "url" in content[0]

    def test_mixed_multiplicity(self) -> None:
        """Test mixed single and multiple inputs."""
        document_concept = ConceptFactory.make_native_concept(NativeConceptCode.DOCUMENT)
        inputs = InputStuffSpecs(
            root={
                "single_document": StuffSpec(concept=document_concept, multiplicity=None),
                "multiple_documents": StuffSpec(concept=document_concept, multiplicity=True),
            }
        )
        result = json.loads(inputs.render_inputs(concept_provider=ConceptLibrary.make_empty()))
        # single_document content should be a dict
        assert isinstance(result["single_document"]["content"], dict)
        # multiple_documents content should be a list
        assert isinstance(result["multiple_documents"]["content"], list)


class TestGenerateRunnerCode:
    """Test generate_runner_code function."""

    @pytest.fixture(autouse=True)
    def stub_concept_library(self, mocker: MockerFixture) -> None:
        """The generator resolves structure classes through the loaded method's library.

        These tests drive it with mock pipes rather than a loaded method, so an empty
        `ConceptLibrary` stands in: it holds no concepts but resolves any class the process
        registry already has, which is all the code generation needs.
        """
        mocker.patch("pipelex.builder.runner_code.get_concept_library", return_value=ConceptLibrary.make_empty())

    @pytest.fixture
    def mock_pipe_single_output(self, mocker: MockerFixture) -> MockType:
        """Create a mock pipe with a single output."""
        text_concept = ConceptFactory.make_native_concept(NativeConceptCode.TEXT)
        document_concept = ConceptFactory.make_native_concept(NativeConceptCode.DOCUMENT)

        mock_pipe: MockType = mocker.MagicMock()
        mock_pipe.code = "test_pipe"
        mock_pipe.output = StuffSpec(concept=text_concept)
        mock_pipe.inputs = InputStuffSpecs(root={"document": StuffSpec(concept=document_concept)})
        return mock_pipe

    @pytest.fixture
    def mock_pipe_list_output(self, mocker: MockerFixture) -> MockType:
        """Create a mock pipe with a list output."""
        text_concept = ConceptFactory.make_native_concept(NativeConceptCode.TEXT)
        document_concept = ConceptFactory.make_native_concept(NativeConceptCode.DOCUMENT)

        mock_pipe: MockType = mocker.MagicMock()
        mock_pipe.code = "test_pipe_list"
        mock_pipe.output = StuffSpec(concept=text_concept)
        mock_pipe.inputs = InputStuffSpecs(root={"documents": StuffSpec(concept=document_concept, multiplicity=True)})
        return mock_pipe

    def test_runner_code_includes_imports(self, mock_pipe_single_output: MockType) -> None:
        """Test that generated runner code includes necessary imports."""
        runner_code = generate_runner_code(mock_pipe_single_output)
        assert "import asyncio" in runner_code
        assert "from pipelex.pipelex import Pipelex" in runner_code
        assert "from pipelex.pipeline.runner import PipelexMTHDSProtocol" in runner_code

    def test_runner_code_includes_structure_imports(self, mock_pipe_single_output: MockType) -> None:
        """Test that generated runner code includes structure class imports."""
        runner_code = generate_runner_code(mock_pipe_single_output)
        assert "from pipelex.core.stuffs.document_content import DocumentContent" in runner_code
        assert "from pipelex.core.stuffs.text_content import TextContent" in runner_code

    def test_runner_code_single_output_return_type(self, mock_pipe_single_output: MockType) -> None:
        """Test that generated runner code has correct return type for single output."""
        runner_code = generate_runner_code(mock_pipe_single_output, output_multiplicity=False)
        assert "async def run_test_pipe() -> TextContent:" in runner_code
        assert "pipe_output.main_stuff_as(content_type=TextContent)" in runner_code

    def test_runner_code_list_output_return_type(self, mock_pipe_list_output: MockType) -> None:
        """Test that generated runner code has correct return type for list output."""
        runner_code = generate_runner_code(mock_pipe_list_output, output_multiplicity=True)
        assert "async def run_test_pipe_list() -> list[TextContent]:" in runner_code
        assert "pipe_output.main_stuff_as_items(item_type=TextContent)" in runner_code

    def test_runner_code_includes_inputs(self, mock_pipe_single_output: MockType) -> None:
        """Test that generated runner code includes input values."""
        runner_code = generate_runner_code(mock_pipe_single_output)
        assert '"document":' in runner_code
        assert '"concept": "native.Document"' in runner_code
        assert "DocumentContent(" in runner_code

    def test_runner_code_includes_main_block(self, mock_pipe_single_output: MockType) -> None:
        """Test that generated runner code includes main block."""
        runner_code = generate_runner_code(mock_pipe_single_output)
        assert 'if __name__ == "__main__":' in runner_code
        assert "Pipelex.make()" in runner_code
        assert "asyncio.run(run_test_pipe())" in runner_code

    def test_runner_code_multiplicity_input(self, mock_pipe_list_output: MockType) -> None:
        """Test that generated runner code handles input multiplicity correctly."""
        runner_code = generate_runner_code(mock_pipe_list_output)
        # Should have list-wrapped content for multiplicity input
        assert "[DocumentContent(" in runner_code

    def test_runner_code_custom_class_import_format(self, mocker: MockerFixture) -> None:
        """Custom classes import from the single-module types projection (structures/structures.py)."""
        # Create a custom concept (non-native)
        custom_concept = ConceptFactory.make(
            domain_code="test_domain",
            concept_code="CustomOutput",
            description="A custom output",
            structure_class_name="CustomOutput",
        )
        document_concept = ConceptFactory.make_native_concept(NativeConceptCode.DOCUMENT)

        mock_pipe = mocker.MagicMock()
        mock_pipe.code = "custom_pipe"
        mock_pipe.output = StuffSpec(concept=custom_concept)
        mock_pipe.inputs = InputStuffSpecs(root={"document": StuffSpec(concept=document_concept)})

        runner_code = generate_runner_code(mock_pipe)
        # Custom imports come from the emitted single module; NOT a relative import (standalone script)
        assert "from structures.structures import CustomOutput" in runner_code
        assert "from .structures" not in runner_code

    def test_runner_code_class_name_overrides_spell_emitted_names(self, mocker: MockerFixture) -> None:
        """The overrides map re-spells runtime-qualified class names to the emitted (bare) names."""
        custom_concept = ConceptFactory.make(
            domain_code="test_domain",
            concept_code="CustomOutput",
            description="A custom output",
            structure_class_name="test_domain__CustomOutput",
        )
        text_concept = ConceptFactory.make_native_concept(NativeConceptCode.TEXT)

        mock_pipe = mocker.MagicMock()
        mock_pipe.code = "custom_pipe"
        mock_pipe.output = StuffSpec(concept=custom_concept)
        mock_pipe.inputs = InputStuffSpecs(root={"message": StuffSpec(concept=text_concept)})

        runner_code = generate_runner_code(mock_pipe, class_name_overrides={"test_domain__CustomOutput": "CustomOutput"})
        assert "from structures.structures import CustomOutput" in runner_code
        assert "async def run_custom_pipe() -> CustomOutput:" in runner_code
        assert "pipe_output.main_stuff_as(content_type=CustomOutput)" in runner_code
        assert "test_domain__CustomOutput" not in runner_code

    def test_runner_code_anything_output_uses_any_return_type(self, mocker: MockerFixture) -> None:
        """Test that Anything output concept uses Any return type and main_stuff instead of main_stuff_as."""
        anything_concept = ConceptFactory.make_native_concept(NativeConceptCode.ANYTHING)
        text_concept = ConceptFactory.make_native_concept(NativeConceptCode.TEXT)

        mock_pipe = mocker.MagicMock()
        mock_pipe.code = "anything_output_pipe"
        mock_pipe.output = StuffSpec(concept=anything_concept)
        mock_pipe.inputs = InputStuffSpecs(root={"message": StuffSpec(concept=text_concept)})

        runner_code = generate_runner_code(mock_pipe)
        # Should use Any as return type, not AnythingContent
        assert "async def run_anything_output_pipe() -> Any:" in runner_code
        # Should use main_stuff, not main_stuff_as
        assert "pipe_output.main_stuff" in runner_code
        assert "main_stuff_as(content_type=" not in runner_code
        # Should NOT import AnythingContent (it doesn't exist)
        assert "AnythingContent" not in runner_code
        # Should import Any from typing
        assert "from typing import Any" in runner_code
