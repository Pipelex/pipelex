"""Unit tests for runner_code module."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from pipelex.builder.runner_code import (
    generate_input_memory_json,
    generate_input_representation_json,
    generate_input_representation_python,
    generate_runner_code,
)
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.inputs.input_requirements import InputRequirement, InputRequirements


class TestGenerateInputRepresentationJson:
    """Test generate_input_representation_json function."""

    def test_native_text_json(self) -> None:
        """Test JSON representation for native Text concept."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.TEXT)
        result = generate_input_representation_json(concept)
        assert result["concept"] == "native.Text"
        assert "content" in result
        assert "text" in result["content"]

    def test_native_image_json(self) -> None:
        """Test JSON representation for native Image concept."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.IMAGE)
        result = generate_input_representation_json(concept)
        assert result["concept"] == "native.Image"
        assert "content" in result
        assert "url" in result["content"]

    def test_native_number_json(self) -> None:
        """Test JSON representation for native Number concept."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.NUMBER)
        result = generate_input_representation_json(concept)
        assert result["concept"] == "native.Number"
        assert "content" in result
        assert "number" in result["content"]

    def test_native_pdf_json_with_multiplicity(self) -> None:
        """Test JSON representation for PDF with multiplicity - content should be a list."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.PDF)
        result = generate_input_representation_json(concept, is_multiple=True)
        assert result["concept"] == "native.PDF"
        assert "content" in result
        # Content should be a list
        content = cast("list[dict[str, Any]]", result["content"])
        assert isinstance(content, list)
        assert len(content) == 1
        assert "url" in content[0]


class TestGenerateInputRepresentationPython:
    """Test generate_input_representation_python function."""

    def test_native_text_python(self) -> None:
        """Test Python representation for native Text concept."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.TEXT)
        python_code, imports = generate_input_representation_python(concept)
        assert '"concept":' in python_code
        assert "native.Text" in python_code
        assert "TextContent" in python_code
        assert "TextContent" in imports

    def test_native_image_python(self) -> None:
        """Test Python representation for native Image concept."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.IMAGE)
        python_code, imports = generate_input_representation_python(concept)
        assert '"concept":' in python_code
        assert "native.Image" in python_code
        assert "ImageContent" in python_code
        assert "ImageContent" in imports

    def test_refined_text_python(self) -> None:
        """Test Python representation for a concept that refines Text."""
        concept = ConceptFactory.make(
            domain="test_domain",
            concept_code="Question",
            description="A question",
            structure_class_name="TextContent",
            refines="native.Text",
        )
        python_code, imports = generate_input_representation_python(concept)
        assert '"concept":' in python_code
        assert "test_domain.Question" in python_code
        assert "TextContent" in python_code
        assert "TextContent" in imports

    def test_native_pdf_python_with_multiplicity(self) -> None:
        """Test Python representation for PDF with multiplicity - content should be wrapped in list."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.PDF)
        python_code, imports = generate_input_representation_python(concept, is_multiple=True)
        assert '"concept":' in python_code
        assert "native.PDF" in python_code
        # Content should be wrapped in list brackets
        assert "[PDFContent" in python_code
        assert "PDFContent" in imports


class TestGenerateInputMemoryJson:
    """Test generate_input_memory_json function."""

    def test_empty_inputs(self) -> None:
        """Test JSON generation with no inputs."""
        inputs = InputRequirements(root={})
        result = generate_input_memory_json(inputs)
        assert result == {}

    def test_single_input(self) -> None:
        """Test JSON generation with a single input."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.TEXT)
        inputs = InputRequirements(root={"message": InputRequirement(concept=concept)})
        result = generate_input_memory_json(inputs)
        assert "message" in result
        assert result["message"]["concept"] == "native.Text"

    def test_multiple_inputs(self) -> None:
        """Test JSON generation with multiple inputs."""
        text_concept = ConceptFactory.make_native_concept(NativeConceptCode.TEXT)
        image_concept = ConceptFactory.make_native_concept(NativeConceptCode.IMAGE)
        inputs = InputRequirements(
            root={
                "text_input": InputRequirement(concept=text_concept),
                "image_input": InputRequirement(concept=image_concept),
            }
        )
        result = generate_input_memory_json(inputs)
        assert "text_input" in result
        assert "image_input" in result
        assert result["text_input"]["concept"] == "native.Text"
        assert result["image_input"]["concept"] == "native.Image"


class TestGenerateInputMemoryJsonWithMultiplicity:
    """Test generate_input_memory_json with multiplicity - content is wrapped in list."""

    def test_single_item_no_multiplicity(self) -> None:
        """Test that single item (no multiplicity) has content as dict, not list."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.PDF)
        inputs = InputRequirements(root={"document": InputRequirement(concept=concept, multiplicity=None)})
        result = generate_input_memory_json(inputs)
        assert "document" in result
        # concept should be present
        assert result["document"]["concept"] == "native.PDF"
        # content should NOT be a list
        content = result["document"]["content"]
        assert isinstance(content, dict)
        assert "url" in content

    def test_multiple_items_true_multiplicity(self) -> None:
        """Test that multiplicity=True wraps content in list."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.PDF)
        inputs = InputRequirements(root={"documents": InputRequirement(concept=concept, multiplicity=True)})
        result = generate_input_memory_json(inputs)
        assert "documents" in result
        # concept should be at the top level
        assert result["documents"]["concept"] == "native.PDF"
        # content should be a list
        content = cast("list[dict[str, Any]]", result["documents"]["content"])
        assert isinstance(content, list)
        assert len(content) == 1
        assert "url" in content[0]

    def test_multiple_items_int_multiplicity(self) -> None:
        """Test that multiplicity=N (int > 1) wraps content in list."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.IMAGE)
        inputs = InputRequirements(root={"images": InputRequirement(concept=concept, multiplicity=3)})
        result = generate_input_memory_json(inputs)
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
        pdf_concept = ConceptFactory.make_native_concept(NativeConceptCode.PDF)
        inputs = InputRequirements(
            root={
                "single_pdf": InputRequirement(concept=pdf_concept, multiplicity=None),
                "multiple_pdfs": InputRequirement(concept=pdf_concept, multiplicity=True),
            }
        )
        result = generate_input_memory_json(inputs)
        # single_pdf content should be a dict
        assert isinstance(result["single_pdf"]["content"], dict)
        # multiple_pdfs content should be a list
        assert isinstance(result["multiple_pdfs"]["content"], list)


class TestGenerateRunnerCode:
    """Test generate_runner_code function."""

    @pytest.fixture
    def mock_pipe_single_output(self) -> MagicMock:
        """Create a mock pipe with a single output."""
        text_concept = ConceptFactory.make_native_concept(NativeConceptCode.TEXT)
        pdf_concept = ConceptFactory.make_native_concept(NativeConceptCode.PDF)

        mock_pipe = MagicMock()
        mock_pipe.code = "test_pipe"
        mock_pipe.output = text_concept
        mock_pipe.inputs = InputRequirements(root={"document": InputRequirement(concept=pdf_concept)})
        return mock_pipe

    @pytest.fixture
    def mock_pipe_list_output(self) -> MagicMock:
        """Create a mock pipe with a list output."""
        text_concept = ConceptFactory.make_native_concept(NativeConceptCode.TEXT)
        pdf_concept = ConceptFactory.make_native_concept(NativeConceptCode.PDF)

        mock_pipe = MagicMock()
        mock_pipe.code = "test_pipe_list"
        mock_pipe.output = text_concept
        mock_pipe.inputs = InputRequirements(root={"documents": InputRequirement(concept=pdf_concept, multiplicity=True)})
        return mock_pipe

    def test_runner_code_includes_imports(self, mock_pipe_single_output: MagicMock) -> None:
        """Test that generated runner code includes necessary imports."""
        runner_code = generate_runner_code(mock_pipe_single_output)
        assert "import asyncio" in runner_code
        assert "from pipelex.pipelex import Pipelex" in runner_code
        assert "from pipelex.pipeline.execute import execute_pipeline" in runner_code

    def test_runner_code_includes_structure_imports(self, mock_pipe_single_output: MagicMock) -> None:
        """Test that generated runner code includes structure class imports."""
        runner_code = generate_runner_code(mock_pipe_single_output)
        assert "from pipelex.core.stuffs.pdf_content import PDFContent" in runner_code
        assert "from pipelex.core.stuffs.text_content import TextContent" in runner_code

    def test_runner_code_single_output_return_type(self, mock_pipe_single_output: MagicMock) -> None:
        """Test that generated runner code has correct return type for single output."""
        runner_code = generate_runner_code(mock_pipe_single_output, output_multiplicity=False)
        assert "async def run_test_pipe() -> TextContent:" in runner_code
        assert "pipe_output.main_stuff_as(content_type=TextContent)" in runner_code

    def test_runner_code_list_output_return_type(self, mock_pipe_list_output: MagicMock) -> None:
        """Test that generated runner code has correct return type for list output."""
        runner_code = generate_runner_code(mock_pipe_list_output, output_multiplicity=True)
        assert "async def run_test_pipe_list() -> list[TextContent]:" in runner_code
        assert "pipe_output.main_stuff_as_items(item_type=TextContent)" in runner_code

    def test_runner_code_includes_inputs(self, mock_pipe_single_output: MagicMock) -> None:
        """Test that generated runner code includes input values."""
        runner_code = generate_runner_code(mock_pipe_single_output)
        assert '"document":' in runner_code
        assert '"concept": "native.PDF"' in runner_code
        assert "PDFContent(" in runner_code

    def test_runner_code_includes_main_block(self, mock_pipe_single_output: MagicMock) -> None:
        """Test that generated runner code includes main block."""
        runner_code = generate_runner_code(mock_pipe_single_output)
        assert 'if __name__ == "__main__":' in runner_code
        assert "Pipelex.make()" in runner_code
        assert "asyncio.run(run_test_pipe())" in runner_code

    def test_runner_code_multiplicity_input(self, mock_pipe_list_output: MagicMock) -> None:
        """Test that generated runner code handles input multiplicity correctly."""
        runner_code = generate_runner_code(mock_pipe_list_output)
        # Should have list-wrapped content for multiplicity input
        assert "[PDFContent(" in runner_code

    def test_runner_code_custom_class_import_format(self) -> None:
        """Test that custom class imports use domain_conceptCode format for standalone scripts."""
        # Create a custom concept (non-native)
        custom_concept = ConceptFactory.make(
            domain="test_domain",
            concept_code="CustomOutput",
            description="A custom output",
            structure_class_name="CustomOutput",
        )
        pdf_concept = ConceptFactory.make_native_concept(NativeConceptCode.PDF)

        mock_pipe = MagicMock()
        mock_pipe.code = "custom_pipe"
        mock_pipe.output = custom_concept
        mock_pipe.inputs = InputRequirements(root={"document": InputRequirement(concept=pdf_concept)})

        runner_code = generate_runner_code(mock_pipe)
        # Custom imports should NOT use relative import (no leading dot) for standalone scripts
        assert "from structures.test_domain_CustomOutput import CustomOutput" in runner_code
        assert "from .structures" not in runner_code
