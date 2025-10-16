"""Unit tests for runner_generator module."""

from __future__ import annotations

from pipelex.builder.runner_code import generate_compact_memory_entry, value_to_python_code
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptCode


class TestValueToPythonCode:
    """Test value_to_python_code function."""

    def test_simple_string(self) -> None:
        """Test conversion of a simple string."""
        result = value_to_python_code("hello")
        assert result == '"hello"'

    def test_simple_number(self) -> None:
        """Test conversion of a number."""
        result = value_to_python_code(42)
        assert result == "42"

    def test_simple_boolean(self) -> None:
        """Test conversion of a boolean."""
        result = value_to_python_code(True)
        assert result == "True"

    def test_dict_with_class_image_content(self) -> None:
        """Test conversion of ImageContent dict."""
        value = {"_class": "ImageContent", "url": "test_url"}
        result = value_to_python_code(value)
        assert result == 'ImageContent(url="test_url")'

    def test_dict_with_class_pdf_content(self) -> None:
        """Test conversion of PDFContent dict."""
        value = {"_class": "PDFContent", "url": "test_url"}
        result = value_to_python_code(value)
        assert result == 'PDFContent(url="test_url")'

    def test_dict_with_concept_code_and_content_simple(self) -> None:
        """Test conversion of refined concept with simple content."""
        value = {
            "concept_code": "test_domain.Question",
            "content": "question_text",
        }
        result = value_to_python_code(value, indent_level=3)
        expected = '{\n                "concept": "test_domain.Question",\n                "content": "question_text",\n            }'
        assert result == expected

    def test_dict_with_concept_code_and_content_image(self) -> None:
        """Test conversion of refined Image concept."""
        value = {
            "concept_code": "tables.TableScreenshot",
            "content": {"_class": "ImageContent", "url": "table_screenshot_url"},
        }
        result = value_to_python_code(value, indent_level=3)
        expected = (
            "{\n"
            '                "concept": "tables.TableScreenshot",\n'
            '                "content": ImageContent(url="table_screenshot_url"),\n'
            "            }"
        )
        assert result == expected


class TestGenerateCompactMemoryEntry:
    """Test generate_compact_memory_entry function."""

    def test_generate_entry_for_native_text(self) -> None:
        """Test generating entry for native Text concept."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.TEXT)
        result = generate_compact_memory_entry("message", concept)
        assert result == '            "message": "message_text",'

    def test_generate_entry_for_native_image(self) -> None:
        """Test generating entry for native Image concept."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.IMAGE)
        result = generate_compact_memory_entry("photo", concept)
        assert result == '            "photo": ImageContent(url="photo_url"),'

    def test_generate_entry_for_refined_image(self) -> None:
        """Test generating entry for a concept that refines Image."""
        concept = ConceptFactory.make(
            domain="tables",
            concept_code="TableScreenshot",
            description="A screenshot of a table",
            structure_class_name="ImageContent",
            refines="native.Image",
        )
        result = generate_compact_memory_entry("table_screenshot", concept)

        # Should generate the full format with concept and content
        assert '"concept": "tables.TableScreenshot"' in result
        assert 'ImageContent(url="table_screenshot_url")' in result
        assert "table_screenshot" in result

    def test_generate_entry_for_refined_text(self) -> None:
        """Test generating entry for a concept that refines Text."""
        concept = ConceptFactory.make(
            domain="test_domain",
            concept_code="Question",
            description="A question",
            structure_class_name="TextContent",
            refines="native.Text",
        )
        result = generate_compact_memory_entry("question", concept)

        # Should generate the full format with concept and content
        assert '"concept": "test_domain.Question"' in result
        assert '"question_text"' in result
        assert "question" in result
