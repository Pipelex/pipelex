"""Unit tests for Concept compact memory generation methods."""

from __future__ import annotations

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptCode


class TestConceptCompactMemory:
    """Test Concept methods for generating compact memory examples."""

    def test_get_compact_memory_example_text(self) -> None:
        """Test compact memory example for Text concept."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.TEXT)
        result = concept.get_compact_memory_example("message")
        assert isinstance(result, str)
        assert result == "message_text"

    def test_get_compact_memory_example_number(self) -> None:
        """Test compact memory example for Number concept."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.NUMBER)
        result = concept.get_compact_memory_example("count")
        assert isinstance(result, int)
        assert result == 0

    def test_get_compact_memory_example_image(self) -> None:
        """Test compact memory example for Image concept."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.IMAGE)
        result = concept.get_compact_memory_example("photo")
        assert isinstance(result, dict)
        assert result["_class"] == "ImageContent"
        assert result["url"] == "photo_url"

    def test_get_compact_memory_example_pdf(self) -> None:
        """Test compact memory example for PDF concept."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.PDF)
        result = concept.get_compact_memory_example("document")
        assert isinstance(result, dict)
        assert result["_class"] == "PDFContent"
        assert result["url"] == "document_url"

    def test_get_compact_memory_example_text_and_images(self) -> None:
        """Test compact memory example for TextAndImages concept."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.TEXT_AND_IMAGES)

        result = concept.get_compact_memory_example("content")

        # Should return a dict with concept_code and content
        assert isinstance(result, dict)
        assert result["concept_code"] == "native.TextAndImages"
        assert "content" in result
        assert "text" in result["content"]
        assert result["content"]["text"] == "text_text"  # Generated from field name "text"
        assert "images" in result["content"]
        assert isinstance(result["content"]["images"], list)

    def test_get_compact_memory_example_page(self) -> None:
        """Test compact memory example for Page concept."""
        concept = ConceptFactory.make_native_concept(NativeConceptCode.PAGE)

        result = concept.get_compact_memory_example("page")

        # Should return a dict with concept_code and content
        assert isinstance(result, dict)
        assert result["concept_code"] == "native.Page"
        assert "content" in result
        assert "text_and_images" in result["content"]
        assert isinstance(result["content"]["text_and_images"], dict)

    def test_get_compact_memory_example_custom_structured(self) -> None:
        """Test compact memory example for a custom structured concept."""
        concept = ConceptFactory.make(
            concept_code="Invoice",
            domain="accounting",
            description="Invoice data",
            structure_class_name="Invoice",
            refines=None,
        )

        result = concept.get_compact_memory_example("invoice")

        # Should return a dict with concept_code and content
        assert isinstance(result, dict)
        assert result["concept_code"] == "accounting.Invoice"
        assert "content" in result

    def test_get_compact_memory_example_for_refined_text_concept(self) -> None:
        """Test compact memory example for a concept that refines Text."""
        # Create a concept that refines Text using direct make() to control domain
        concept = ConceptFactory.make(
            domain="test_domain",
            concept_code="Question",
            description="A question",
            structure_class_name="TextContent",
            refines="native.Text",
        )

        # Test - should return full format with concept_code since it's a refined (non-native) concept
        # Even though it refines Text, it's not the native Text concept itself
        result = concept.get_compact_memory_example("question")
        assert isinstance(result, dict)
        assert "concept_code" in result
        assert result["concept_code"] == "test_domain.Question"
        assert "content" in result
        assert result["content"] == "question_text"  # Content is still the simple text string

    def test_get_compact_memory_example_for_refined_image_concept(self) -> None:
        """Test compact memory example for a concept that refines Image (non-native)."""
        # Create a concept that refines Image using direct make() to control domain
        concept = ConceptFactory.make(
            domain="tables",
            concept_code="TableScreenshot",
            description="A screenshot of a table",
            structure_class_name="ImageContent",
            refines="native.Image",
        )

        # Test - should return full format with concept_code since it's a refined (non-native) concept
        result = concept.get_compact_memory_example("table_screenshot")
        assert isinstance(result, dict)
        assert "concept_code" in result
        assert result["concept_code"] == "tables.TableScreenshot"
        assert "content" in result
        # Content should be wrapped in ImageContent format
        assert isinstance(result["content"], dict)
        assert result["content"]["_class"] == "ImageContent"
        assert result["content"]["url"] == "table_screenshot_url"
