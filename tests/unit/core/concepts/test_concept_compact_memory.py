"""Unit tests for Concept compact memory generation methods."""

from __future__ import annotations

import pytest

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptCode


class TestConceptCompactMemory:
    """Test Concept methods for generating compact memory examples."""

    @pytest.mark.parametrize(
        ("concept_code", "domain", "structure_class_name", "var_name", "expected_value", "expected_type"),
        [
            # Text concept - simple string
            ("Text", "native", "TextContent", "message", "message_text", str),
            # Custom text-based concept - simple string
            ("CustomText", "test_domain", "TextContent", "raw_text", "raw_text_text", str),
            # Image concept - URL string
            ("Image", "native", "ImageContent", "photo", "photo_url", str),
            # PDF concept - URL string
            ("PDF", "native", "PDFContent", "document", "document_url", str),
            # Number concept
            ("Number", "native", "NumberContent", "count", 0, int),
        ],
    )
    def test_get_compact_memory_example_simple_types(
        self,
        concept_code: str,
        domain: str,
        structure_class_name: str,
        var_name: str,
        expected_value: str | int,
        expected_type: type,
    ) -> None:
        """Test that get_compact_memory_example generates correct simple values."""
        # Create concept using ConceptFactory
        concept = ConceptFactory.make(
            concept_code=concept_code,
            domain=domain,
            description=f"Test {concept_code}",
            structure_class_name=structure_class_name,
            refines=None,
        )

        # Test
        result = concept.get_compact_memory_example(var_name)
        assert isinstance(result, expected_type)
        assert result == expected_value

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
        # Create a concept that refines Text
        blueprint = ConceptBlueprint(
            description="A question",
            refines="native.Text",
        )

        concept = ConceptFactory.make_from_blueprint(
            domain="test_domain",
            concept_code="Question",
            blueprint=blueprint,
        )

        # Test - should return a simple string since it uses TextContent
        result = concept.get_compact_memory_example("question")
        assert isinstance(result, str)
        assert result == "question_text"
