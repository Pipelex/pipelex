"""Unit tests for WorkingMemory get_typed_object_or_attribute() method."""

from typing import cast

import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.memory.exceptions import WorkingMemoryStuffAttributeNotFoundError, WorkingMemoryTypeError
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from tests.unit.core.memory.conftest import TestWorkingMemoryData


@pytest.fixture
def nested_content_memory() -> WorkingMemory:
    """Create WorkingMemory with nested content structure (PageContent)."""
    page_content = PageContent(
        text_and_images=TextAndImagesContent(
            text=TextContent(text="Sample page text"),
            images=[
                ImageContent(url="assets/image1.png"),
                ImageContent(url="assets/image2.png"),
            ],
        ),
        page_view=ImageContent(url="assets/page_view.png"),
    )

    stuff = StuffFactory.make_stuff(
        concept=ConceptFactory.make(
            concept_code="Page",
            domain=SpecialDomain.NATIVE,
            description="A page with text and images",
            structure_class_name="PageContent",
        ),
        name="sample_page",
        content=page_content,
    )

    return WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)


@pytest.fixture
def nested_content_with_none_memory() -> WorkingMemory:
    """Create WorkingMemory with nested content where some fields are None."""
    page_content = PageContent(
        text_and_images=TextAndImagesContent(
            text=None,  # Optional field set to None
            images=None,  # Optional field set to None
        ),
        page_view=None,  # Optional field set to None
    )

    stuff = StuffFactory.make_stuff(
        concept=ConceptFactory.make(
            concept_code="Page",
            domain=SpecialDomain.NATIVE,
            description="A page with minimal content",
            structure_class_name="PageContent",
        ),
        name="minimal_page",
        content=page_content,
    )

    return WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)


class TestWorkingMemoryTypedAccess:
    """Unit tests for WorkingMemory.get_typed_object_or_attribute() method."""

    def test_simple_access_without_type(self, single_text_memory: WorkingMemory):
        """Test retrieving content by simple name without type validation."""
        result = single_text_memory.get_typed_object_or_attribute("sample_text")

        assert isinstance(result, TextContent)
        assert result.text == TestWorkingMemoryData.SAMPLE_TEXT

    def test_simple_access_with_matching_type(self, single_text_memory: WorkingMemory):
        """Test retrieving content with matching type validation."""
        result = single_text_memory.get_typed_object_or_attribute("sample_text", wanted_type=TextContent)

        assert isinstance(result, TextContent)
        assert result.text == TestWorkingMemoryData.SAMPLE_TEXT

    def test_simple_access_with_wrong_type(self, single_text_memory: WorkingMemory):
        """Test that type mismatch raises WorkingMemoryTypeError."""
        with pytest.raises(WorkingMemoryTypeError) as exc_info:
            single_text_memory.get_typed_object_or_attribute("sample_text", wanted_type=ImageContent)

        assert "sample_text" in str(exc_info.value)
        assert "TextContent" in str(exc_info.value)
        assert "ImageContent" in str(exc_info.value)

    def test_nested_attribute_access_one_level(self, nested_content_memory: WorkingMemory):
        """Test retrieving nested attribute (one level deep)."""
        result = nested_content_memory.get_typed_object_or_attribute("sample_page.text_and_images")

        assert isinstance(result, TextAndImagesContent)
        assert result.text is not None
        assert result.text.text == "Sample page text"

    def test_nested_attribute_access_two_levels(self, nested_content_memory: WorkingMemory):
        """Test retrieving deeply nested attribute (two levels deep)."""
        result = nested_content_memory.get_typed_object_or_attribute("sample_page.text_and_images.text")

        assert isinstance(result, TextContent)
        assert result.text == "Sample page text"

    def test_nested_attribute_access_list_field(self, nested_content_memory: WorkingMemory):
        """Test retrieving nested list field."""
        result = nested_content_memory.get_typed_object_or_attribute("sample_page.text_and_images.images")

        # Type narrowing and validation
        assert isinstance(result, list)
        # Cast to help type checker - we validate the types with assertions
        images = cast("list[ImageContent]", result)
        assert len(images) == 2
        assert all(isinstance(img, ImageContent) for img in images)
        assert images[0].url == "assets/image1.png"
        assert images[1].url == "assets/image2.png"

    def test_nested_attribute_optional_field(self, nested_content_memory: WorkingMemory):
        """Test retrieving optional nested field."""
        result = nested_content_memory.get_typed_object_or_attribute("sample_page.page_view")

        assert isinstance(result, ImageContent)
        assert result.url == "assets/page_view.png"

    def test_nested_attribute_with_type_validation(self, nested_content_memory: WorkingMemory):
        """Test retrieving nested attribute with type validation."""
        result = nested_content_memory.get_typed_object_or_attribute(
            "sample_page.text_and_images.text",
            wanted_type=TextContent,
        )

        assert isinstance(result, TextContent)
        assert result.text == "Sample page text"

    def test_nested_attribute_with_wrong_type(self, nested_content_memory: WorkingMemory):
        """Test that type mismatch on nested attribute raises WorkingMemoryTypeError."""
        with pytest.raises(WorkingMemoryTypeError) as exc_info:
            nested_content_memory.get_typed_object_or_attribute(
                "sample_page.text_and_images.text",
                wanted_type=ImageContent,
            )

        assert "sample_page.text_and_images.text" in str(exc_info.value)
        assert "TextContent" in str(exc_info.value)
        assert "ImageContent" in str(exc_info.value)

    def test_nested_attribute_not_found(self, nested_content_memory: WorkingMemory):
        """Test that accessing non-existent nested attribute raises WorkingMemoryStuffAttributeNotFoundError."""
        with pytest.raises(WorkingMemoryStuffAttributeNotFoundError) as exc_info:
            nested_content_memory.get_typed_object_or_attribute("sample_page.nonexistent_field")

        assert "sample_page.nonexistent_field" in str(exc_info.value)

    def test_nested_attribute_deep_not_found(self, nested_content_memory: WorkingMemory):
        """Test that accessing non-existent deeply nested attribute raises error."""
        with pytest.raises(WorkingMemoryStuffAttributeNotFoundError) as exc_info:
            nested_content_memory.get_typed_object_or_attribute("sample_page.text_and_images.nonexistent")

        assert "sample_page.text_and_images.nonexistent" in str(exc_info.value)

    def test_none_content_without_type(self, nested_content_with_none_memory: WorkingMemory):
        """Test retrieving None content without type validation."""
        result = nested_content_with_none_memory.get_typed_object_or_attribute("minimal_page.text_and_images.text")

        assert result is None

    def test_none_content_with_type_validation(self, nested_content_with_none_memory: WorkingMemory):
        """Test that None content is allowed even when wanted_type is specified."""
        # This should not raise an error because None is explicitly allowed for optional fields
        result = nested_content_with_none_memory.get_typed_object_or_attribute(
            "minimal_page.text_and_images.text",
            wanted_type=TextContent,
        )

        assert result is None

    def test_none_optional_field(self, nested_content_with_none_memory: WorkingMemory):
        """Test retrieving None from optional field."""
        result = nested_content_with_none_memory.get_typed_object_or_attribute("minimal_page.page_view")

        assert result is None

    def test_multiple_stuffs_access(self, multiple_stuff_memory: WorkingMemory):
        """Test accessing different stuffs in memory with multiple items."""
        question_result = multiple_stuff_memory.get_typed_object_or_attribute("question")
        document_result = multiple_stuff_memory.get_typed_object_or_attribute("document")
        diagram_result = multiple_stuff_memory.get_typed_object_or_attribute("diagram")

        assert isinstance(question_result, TextContent)
        assert question_result.text == "What are the aerodynamic features?"

        assert isinstance(document_result, TextContent)
        assert document_result.text == TestWorkingMemoryData.SAMPLE_TEXT

        assert isinstance(diagram_result, ImageContent)
        assert diagram_result.url == TestWorkingMemoryData.SAMPLE_IMAGE_URL

    def test_alias_access(self, memory_with_aliases: WorkingMemory):
        """Test accessing content through alias."""
        result = memory_with_aliases.get_typed_object_or_attribute("main_text")

        assert isinstance(result, TextContent)
        assert result.text == "Primary content"

    def test_html_content_nested_access(self, html_content_memory: WorkingMemory):
        """Test accessing nested attributes of HtmlContent."""
        inner_html = html_content_memory.get_typed_object_or_attribute("test_report.inner_html")
        css_class = html_content_memory.get_typed_object_or_attribute("test_report.css_class")

        assert isinstance(inner_html, str)
        assert "<h1>Test Report</h1>" in inner_html

        assert isinstance(css_class, str)
        assert css_class == "report-content"
